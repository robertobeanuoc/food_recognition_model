from food_recognition.db import get_meal_schedule


def test_meal_schedule_has_all_meal_type_and_weekend_combinations():
    rows = get_meal_schedule()

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
    rows = get_meal_schedule()

    assert len(rows) > 0
    for row in rows:
        assert row["start_time"] < row["end_time"]
