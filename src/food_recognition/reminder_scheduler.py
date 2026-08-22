import datetime
import os

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from food_recognition import db, slack_bot
from food_recognition.utils import app_logger

_scheduler: BackgroundScheduler | None = None


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
    """For every meal_schedule window of `owner_user_id`'s that has ended
    today without a matching food_register row, send (or escalate) a Slack
    reminder. Called once per linked owner by run_reminders_for_all_linked_owners(),
    which is what start_scheduler() actually schedules.

    now_utc/local_today/is_weekend default to the real current time (resolved
    via APP_TIMEZONE) — the parameters exist so tests can drive this with a
    controlled "now" instead of depending on wall-clock time.
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
            if slack_bot.send_reminder(owner_user_id, meal_type, local_today, escalation=False):
                db.mark_meal_reminder_notified(log["uuid"], current_meal_context or meal_type)
                app_logger.info(f"Sent meal reminder for {meal_type} on {local_today} to {owner_user_id}")
        elif current_meal_context is not None and log["last_nudge_meal_context"] != current_meal_context:
            if slack_bot.send_reminder(owner_user_id, meal_type, local_today, escalation=True):
                db.mark_meal_reminder_nudged(log["uuid"], current_meal_context)
                app_logger.info(f"Nudged still-unregistered {meal_type} on {local_today} for {owner_user_id}")


def run_reminders_for_all_linked_owners() -> None:
    """The actual scheduled job (see start_scheduler()): runs
    check_and_send_meal_reminders() once per owner with a verified Slack
    link. One owner's failure is logged and skipped rather than aborting
    the run for everyone else linked.
    """
    for link in db.get_all_verified_chat_links("slack"):
        owner_user_id = link["owner_user_id"]
        try:
            check_and_send_meal_reminders(owner_user_id=owner_user_id)
        except Exception as e:
            app_logger.error(f"check_and_send_meal_reminders failed for {owner_user_id}: {e}", exc_info=e)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    interval_minutes = int(os.getenv("REMINDER_CHECK_INTERVAL_MINUTES", 10))
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(run_reminders_for_all_linked_owners, "interval", minutes=interval_minutes)
    _scheduler.start()
    app_logger.info(f"Meal reminder scheduler started (every {interval_minutes} min)")
