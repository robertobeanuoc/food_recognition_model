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
    now_utc: datetime.datetime, local_today: datetime.date, is_weekend: bool
) -> str | None:
    """meal_type of the most recent meal_schedule window that has already
    started today — used so a still-unresolved earlier meal only gets
    re-nudged once per later meal window entered (see
    check_and_send_meal_reminders()).
    """
    started = [
        row
        for row in db.get_meal_schedule()
        if row["is_weekend"] == is_weekend
        and _meal_window_utc_datetime(local_today, row["start_time"]) <= now_utc
    ]
    if not started:
        return None
    return max(started, key=lambda row: row["start_time"])["meal_type"]


def check_and_send_meal_reminders(
    now_utc: datetime.datetime = None,
    local_today: datetime.date = None,
    is_weekend: bool = None,
) -> None:
    """Scheduled job: for every meal_schedule window that has ended today
    without a matching food_register row, send (or escalate) a Slack
    reminder. Runs every REMINDER_CHECK_INTERVAL_MINUTES via start_scheduler().

    now_utc/local_today/is_weekend default to the real current time (resolved
    via APP_TIMEZONE) — the parameters exist so tests can drive this with a
    controlled "now" instead of depending on wall-clock time.
    """
    if now_utc is None or local_today is None or is_weekend is None:
        tz = _app_timezone()
        local_today, is_weekend = _local_today_and_weekend(tz)
        now_utc = datetime.datetime.now(tz=pytz.utc).replace(tzinfo=None)
    current_meal_context = _current_meal_context(now_utc, local_today, is_weekend)

    for row in db.get_meal_schedule():
        if row["is_weekend"] != is_weekend:
            continue

        window_end = _meal_window_utc_datetime(local_today, row["end_time"])
        if now_utc < window_end:
            continue

        meal_type = row["meal_type"]
        if db.has_food_register_for_meal(meal_type, local_today):
            db.mark_meal_reminder_resolved(meal_type, local_today)
            continue

        log = db.get_or_create_meal_reminder_log(meal_type, local_today)
        if log["notified_at"] is None:
            slack_bot.send_reminder(meal_type, local_today, escalation=False)
            db.mark_meal_reminder_notified(log["uuid"], current_meal_context or meal_type)
            app_logger.info(f"Sent meal reminder for {meal_type} on {local_today}")
        elif current_meal_context is not None and log["last_nudge_meal_context"] != current_meal_context:
            slack_bot.send_reminder(meal_type, local_today, escalation=True)
            db.mark_meal_reminder_nudged(log["uuid"], current_meal_context)
            app_logger.info(f"Nudged still-unregistered {meal_type} on {local_today}")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    interval_minutes = int(os.getenv("REMINDER_CHECK_INTERVAL_MINUTES", 10))
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(check_and_send_meal_reminders, "interval", minutes=interval_minutes)
    _scheduler.start()
    app_logger.info(f"Meal reminder scheduler started (every {interval_minutes} min)")
