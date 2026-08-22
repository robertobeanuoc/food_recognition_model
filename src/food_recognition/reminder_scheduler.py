import datetime
import os

import pytz

from food_recognition import db, slack_bot
from food_recognition.utils import app_logger


def _app_timezone() -> datetime.tzinfo:
    tz_name = os.getenv("APP_TIMEZONE", "UTC")
    try:
        return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        app_logger.warning(f"Unknown APP_TIMEZONE '{tz_name}', falling back to UTC")
        return pytz.utc


def _local_today_and_weekend(tz: datetime.tzinfo) -> tuple[datetime.date, bool]:
    local_now = datetime.datetime.now(tz=pytz.utc).astimezone(tz)
    local_today = local_now.date()
    return local_today, local_today.weekday() >= 5


def _meal_window_utc_datetime(
    local_today: datetime.date, time_of_day: datetime.time
) -> datetime.datetime:
    """Combine a meal_schedule UTC time-of-day with `local_today` and treat the
    result as naive UTC — the same date/time-of-day approximation
    `_utc_time_to_local`/`_local_time_to_utc` already use in main.py (see
    CLAUDE.md "Timezones" DST caveat: acceptable, not a bug).
    """
    return datetime.datetime.combine(local_today, time_of_day)


def _current_meal_context(
    now_utc: datetime.datetime, local_today: datetime.date, is_weekend: bool, owner_user_id: str
) -> str | None:
    """meal_type of the most recent meal_schedule window that has already
    started today — used so a still-unresolved earlier meal only gets
    re-nudged once per later meal window entered (see
    check_and_send_meal_reminders()).
    """
    started = [
        row
        for row in db.get_meal_schedule(owner_user_id)
        if row["is_weekend"] == is_weekend
        and _meal_window_utc_datetime(local_today, row["start_time"]) <= now_utc
    ]
    if not started:
        return None
    return max(started, key=lambda row: row["start_time"])["meal_type"]


def check_and_send_meal_reminders(
    owner_user_id: str,
    now_utc: datetime.datetime = None,
    local_today: datetime.date = None,
    is_weekend: bool = None,
) -> None:
    """Scheduled job: for every meal_schedule window that has ended today
    without a matching food_register row, send (or escalate) a Slack
    reminder. Would run every REMINDER_CHECK_INTERVAL_MINUTES via
    start_scheduler() — currently not scheduled at all, see start_scheduler().

    now_utc/local_today/is_weekend default to the real current time (resolved
    via APP_TIMEZONE) — the parameters exist so tests can drive this with a
    controlled "now" instead of depending on wall-clock time.

    `owner_user_id` has no default — the caller must supply a real one. This
    used to fall back to a DEFAULT_OWNER_USER_ID constant; that was removed
    on purpose (see TODO(chat-identity) in slack_bot.py) — there is no
    logged-in session in a background job, and no other identity source
    currently exists either, so this function simply can't run for real
    until a caller has one to pass in.
    """
    if now_utc is None or local_today is None or is_weekend is None:
        tz = _app_timezone()
        local_today, is_weekend = _local_today_and_weekend(tz)
        now_utc = datetime.datetime.now(tz=pytz.utc).replace(tzinfo=None)
    current_meal_context = _current_meal_context(now_utc, local_today, is_weekend, owner_user_id)

    for row in db.get_meal_schedule(owner_user_id):
        if row["is_weekend"] != is_weekend:
            continue

        window_end = _meal_window_utc_datetime(local_today, row["end_time"])
        if now_utc < window_end:
            continue

        meal_type = row["meal_type"]
        if db.has_food_register_for_meal(meal_type, local_today, owner_user_id):
            db.mark_meal_reminder_resolved(meal_type, local_today, owner_user_id)
            continue

        log = db.get_or_create_meal_reminder_log(meal_type, local_today, owner_user_id)
        if log["notified_at"] is None:
            slack_bot.send_reminder(meal_type, local_today, escalation=False)
            db.mark_meal_reminder_notified(log["uuid"], current_meal_context or meal_type)
            app_logger.info(f"Sent meal reminder for {meal_type} on {local_today}")
        elif current_meal_context is not None and log["last_nudge_meal_context"] != current_meal_context:
            slack_bot.send_reminder(meal_type, local_today, escalation=True)
            db.mark_meal_reminder_nudged(log["uuid"], current_meal_context)
            app_logger.info(f"Nudged still-unregistered {meal_type} on {local_today}")


def start_scheduler() -> None:
    """Disabled for now: see TODO(chat-identity) in slack_bot.py. There is no
    owner to run check_and_send_meal_reminders() for — it now requires an
    explicit owner_user_id and there is no per-user chat identity to source
    one from. Re-enable once that's resolved; this would then likely
    schedule one job per linked owner rather than a single global one.
    """
    app_logger.warning(
        "Reminder scheduler not started — no owner to check reminders for "
        "without chat-identity linking (see TODO(chat-identity) in slack_bot.py)."
    )
