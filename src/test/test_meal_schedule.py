import datetime

from food_recognition.db import get_meal_schedule, update_meal_schedule

_OWNER_A = "test-owner-a"
_OWNER_B = "test-owner-b"


def test_meal_schedule_has_all_meal_type_and_weekend_combinations():
    rows = get_meal_schedule(owner_user_id=_OWNER_A)

    combinations = {(row["meal_type"], row["is_weekend"]) for row in rows}
    assert combinations == {
        ("breakfast", False),
        ("breakfast", True),
        ("lunch", False),
        ("lunch", True),
        ("dinner", False),
        ("dinner", True),
    }


def test_meal_schedule_ranges_start_before_they_end():
    rows = get_meal_schedule(owner_user_id=_OWNER_A)

    assert len(rows) > 0
    for row in rows:
        assert row["start_time"] < row["end_time"]


def test_meal_schedule_is_seeded_independently_per_owner():
    """Each owner gets their own copy of the default schedule the first time
    it's requested (see db.py:_seed_meal_schedule()), not a single shared
    set of rows everyone reads — so one person's habitual times don't force
    themselves on someone else."""
    rows_a = get_meal_schedule(owner_user_id=_OWNER_A)
    rows_b = get_meal_schedule(owner_user_id=_OWNER_B)

    assert len(rows_a) == len(rows_b) == 6
    assert {row["uuid"] for row in rows_a}.isdisjoint({row["uuid"] for row in rows_b})


def test_update_meal_schedule_cannot_touch_another_owners_row():
    row = next(
        r for r in get_meal_schedule(owner_user_id=_OWNER_A) if r["meal_type"] == "breakfast" and not r["is_weekend"]
    )

    # Attempting the update as a different owner must be a no-op — it should
    # not raise, but it must not change the row either (the WHERE clause
    # simply matches nothing).
    update_meal_schedule(
        uuid=row["uuid"],
        owner_user_id=_OWNER_B,
        start_time=datetime.time(0, 0),
        end_time=datetime.time(1, 0),
    )

    unchanged_row = next(r for r in get_meal_schedule(owner_user_id=_OWNER_A) if r["uuid"] == row["uuid"])
    assert unchanged_row["start_time"] == row["start_time"]
    assert unchanged_row["end_time"] == row["end_time"]
