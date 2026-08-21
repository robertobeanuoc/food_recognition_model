import datetime

import pytest

from food_recognition import db, reminder_scheduler
from food_recognition.constants import DEFAULT_OWNER_USER_ID


@pytest.fixture
def sent_reminders(monkeypatch):
    """Stub out slack_bot.send_reminder — tests never hit real Slack — and
    record every call so escalation timing can be asserted on.
    """
    calls = []

    def _fake_send_reminder(meal_type, meal_date, escalation=False):
        calls.append((meal_type, meal_date, escalation))

    monkeypatch.setattr(reminder_scheduler.slack_bot, "send_reminder", _fake_send_reminder)
    return calls


def _schedule_row(meal_type: str, is_weekend: bool = False) -> dict:
    return next(
        row
        for row in db.get_meal_schedule(DEFAULT_OWNER_USER_ID)
        if row["meal_type"] == meal_type and row["is_weekend"] == is_weekend
    )


def test_no_reminder_when_meal_already_registered(sent_reminders):
    local_today = datetime.date(2026, 3, 2)
    breakfast = _schedule_row("breakfast")
    db.insert_food_type(
        file_uid="test-reminder-registered",
        food_type="omelette",
        glycemic_index=40,
        weight_grams=150,
        owner_user_id=DEFAULT_OWNER_USER_ID,
        meal_type="breakfast",
        created_at=datetime.datetime.combine(local_today, breakfast["start_time"]),
    )

    reminder_scheduler.check_and_send_meal_reminders(
        now_utc=datetime.datetime.combine(local_today, breakfast["end_time"]) + datetime.timedelta(minutes=30),
        local_today=local_today,
        is_weekend=False,
    )

    assert sent_reminders == []


def test_no_reminder_before_meal_window_ends(sent_reminders):
    local_today = datetime.date(2026, 3, 2)
    breakfast = _schedule_row("breakfast")

    reminder_scheduler.check_and_send_meal_reminders(
        now_utc=datetime.datetime.combine(local_today, breakfast["start_time"]),
        local_today=local_today,
        is_weekend=False,
    )

    assert sent_reminders == []


def test_initial_reminder_then_escalation_at_next_meal_window(sent_reminders):
    local_today = datetime.date(2026, 3, 3)
    breakfast = _schedule_row("breakfast")
    lunch = _schedule_row("lunch")
    assert breakfast["end_time"] < lunch["start_time"]

    just_after_breakfast = datetime.datetime.combine(local_today, breakfast["end_time"]) + datetime.timedelta(minutes=5)
    still_before_lunch = datetime.datetime.combine(local_today, lunch["start_time"]) - datetime.timedelta(minutes=5)
    just_after_lunch_starts = datetime.datetime.combine(local_today, lunch["start_time"]) + datetime.timedelta(minutes=5)

    # Breakfast window just ended, nothing logged -> initial reminder.
    reminder_scheduler.check_and_send_meal_reminders(
        now_utc=just_after_breakfast, local_today=local_today, is_weekend=False
    )
    assert sent_reminders == [("breakfast", local_today, False)]

    # Still within the same meal period (lunch hasn't started) -> no repeat.
    reminder_scheduler.check_and_send_meal_reminders(
        now_utc=still_before_lunch, local_today=local_today, is_weekend=False
    )
    assert sent_reminders == [("breakfast", local_today, False)]

    # Lunch's window has now started -> breakfast (still unregistered) gets
    # escalated; lunch's own window hasn't ended yet, so it isn't reminded.
    reminder_scheduler.check_and_send_meal_reminders(
        now_utc=just_after_lunch_starts, local_today=local_today, is_weekend=False
    )
    assert sent_reminders == [
        ("breakfast", local_today, False),
        ("breakfast", local_today, True),
    ]

    log = db.get_or_create_meal_reminder_log("breakfast", local_today, DEFAULT_OWNER_USER_ID)
    assert log["notified_at"] is not None
    assert log["last_nudge_meal_context"] == "lunch"


def test_reminder_log_is_scoped_to_default_owner(sent_reminders):
    """get_or_create_meal_reminder_log must not collide across owners now
    that meal_reminder_log's uniqueness includes owner_user_id — a log
    entry for the same (meal_type, meal_date) but a different owner is a
    distinct row, not the same one reused."""
    local_today = datetime.date(2026, 3, 4)

    default_owner_log = db.get_or_create_meal_reminder_log("dinner", local_today, DEFAULT_OWNER_USER_ID)
    other_owner_log = db.get_or_create_meal_reminder_log("dinner", local_today, "some-other-owner")

    assert default_owner_log["uuid"] != other_owner_log["uuid"]

    db.mark_meal_reminder_notified(default_owner_log["uuid"], "dinner")
    refreshed_other_owner_log = db.get_or_create_meal_reminder_log("dinner", local_today, "some-other-owner")
    assert refreshed_other_owner_log["notified_at"] is None
