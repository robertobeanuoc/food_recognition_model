import datetime
import uuid as uuid_lib

from food_recognition.db import (
    add_meal_default_item,
    delete_meal_default_item,
    get_meal_default_items,
    get_next_default_preset,
    insert_food_type,
    update_meal_default_item,
)


def _unique_file_uid() -> str:
    return str(uuid_lib.uuid4())


def test_add_update_delete_meal_default_item():
    item_uuid = add_meal_default_item(
        meal_type="lunch",
        day_of_week=0,
        preset_order=1,
        item_order=1,
        food_type="rice",
        weight_grams=150,
    )

    row = next(item for item in get_meal_default_items() if item["uuid"] == item_uuid)
    assert row["food_type"] == "rice"
    assert row["weight_grams"] == 150
    assert row["meal_type"] == "lunch"
    assert row["day_of_week"] == 0
    assert row["preset_order"] == 1

    update_meal_default_item(uuid=item_uuid, food_type="brown rice", weight_grams=180)
    row = next(item for item in get_meal_default_items() if item["uuid"] == item_uuid)
    assert row["food_type"] == "brown rice"
    assert row["weight_grams"] == 180

    delete_meal_default_item(uuid=item_uuid)
    assert not any(item["uuid"] == item_uuid for item in get_meal_default_items())


def test_get_next_default_preset_returns_empty_when_not_configured():
    # 'dinner' has no seeded presets by default (only breakfast is seeded by
    # db.sync_schema(); this test's transaction never adds one to 'dinner').
    assert get_next_default_preset("dinner", datetime.date(2026, 3, 2)) == []


def test_seeded_breakfast_preset_is_milk_and_banana():
    target_date = datetime.date(2026, 3, 2)
    assert get_next_default_preset("breakfast", target_date) == [
        {"food_type": "milk", "weight_grams": 200},
        {"food_type": "banana", "weight_grams": 120},
    ]


def test_get_next_default_preset_rotates_after_a_logged_meal_this_week():
    target_date = datetime.date(2026, 3, 2)
    day_of_week = target_date.weekday()

    add_meal_default_item(
        meal_type="lunch",
        day_of_week=day_of_week,
        preset_order=1,
        item_order=1,
        food_type="pasta",
        weight_grams=200,
    )
    add_meal_default_item(
        meal_type="lunch",
        day_of_week=day_of_week,
        preset_order=2,
        item_order=1,
        food_type="salad",
        weight_grams=150,
    )

    assert get_next_default_preset("lunch", target_date) == [
        {"food_type": "pasta", "weight_grams": 200}
    ]

    insert_food_type(
        file_uid=_unique_file_uid(),
        food_type="pasta",
        glycemic_index=50,
        weight_grams=200,
        meal_type="lunch",
        created_at=datetime.datetime.combine(target_date, datetime.time(12, 0)),
    )

    assert get_next_default_preset("lunch", target_date) == [
        {"food_type": "salad", "weight_grams": 150}
    ]
