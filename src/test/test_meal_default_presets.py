import datetime
import uuid as uuid_lib

from food_recognition.db import (
    _seed_meal_default_items,
    add_meal_default_item,
    delete_meal_default_item,
    get_meal_default_items,
    get_next_default_preset,
    insert_food_type,
    update_meal_default_item,
)

_OWNER_A = "test-owner-a"
_OWNER_B = "test-owner-b"


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
        owner_user_id=_OWNER_A,
    )

    row = next(item for item in get_meal_default_items(owner_user_id=_OWNER_A) if item["uuid"] == item_uuid)
    assert row["food_type"] == "rice"
    assert row["weight_grams"] == 150
    assert row["meal_type"] == "lunch"
    assert row["day_of_week"] == 0
    assert row["preset_order"] == 1

    update_meal_default_item(uuid=item_uuid, owner_user_id=_OWNER_A, food_type="brown rice", weight_grams=180)
    row = next(item for item in get_meal_default_items(owner_user_id=_OWNER_A) if item["uuid"] == item_uuid)
    assert row["food_type"] == "brown rice"
    assert row["weight_grams"] == 180

    delete_meal_default_item(uuid=item_uuid, owner_user_id=_OWNER_A)
    assert not any(item["uuid"] == item_uuid for item in get_meal_default_items(owner_user_id=_OWNER_A))


def test_get_next_default_preset_returns_empty_when_not_configured():
    # 'dinner' has no seeded presets by default (only breakfast is seeded
    # lazily by get_meal_default_items()/_seed_meal_default_items(); this
    # test's transaction never adds one to 'dinner').
    assert get_next_default_preset("dinner", datetime.date(2026, 3, 2), _OWNER_A) == []


def test_seed_meal_default_items_seeds_milk_and_banana_breakfast_preset():
    """_seed_meal_default_items() seeds a default breakfast preset (milk
    200g, banana 120g) for an owner the first time their presets are
    requested (see db.py:get_meal_default_items()). _OWNER_A is a synthetic
    test owner that only ever exists inside this test's own rolled-back
    transaction, so this exercises the seeding logic in isolation instead of
    asserting against shared, editable production data.
    """
    _seed_meal_default_items(_OWNER_A)

    target_date = datetime.date(2026, 3, 2)
    assert get_next_default_preset("breakfast", target_date, _OWNER_A) == [
        {"food_type": "milk", "weight_grams": 200},
        {"food_type": "banana", "weight_grams": 120},
    ]


def test_meal_default_items_are_scoped_per_owner():
    """Presets are per-owner, not shared — a preset one owner configures must
    not appear for another owner who hasn't configured anything for that
    meal_type/day (each person eats different default items)."""
    target_date = datetime.date(2026, 3, 5)
    day_of_week = target_date.weekday()

    add_meal_default_item(
        meal_type="lunch",
        day_of_week=day_of_week,
        preset_order=1,
        item_order=1,
        food_type="couscous",
        weight_grams=200,
        owner_user_id=_OWNER_A,
    )

    assert get_next_default_preset("lunch", target_date, _OWNER_A) == [
        {"food_type": "couscous", "weight_grams": 200}
    ]
    assert get_next_default_preset("lunch", target_date, _OWNER_B) == []


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
        owner_user_id=_OWNER_A,
    )
    add_meal_default_item(
        meal_type="lunch",
        day_of_week=day_of_week,
        preset_order=2,
        item_order=1,
        food_type="salad",
        weight_grams=150,
        owner_user_id=_OWNER_A,
    )

    assert get_next_default_preset("lunch", target_date, _OWNER_A) == [
        {"food_type": "pasta", "weight_grams": 200}
    ]

    insert_food_type(
        file_uid=_unique_file_uid(),
        food_type="pasta",
        glycemic_index=50,
        weight_grams=200,
        owner_user_id=_OWNER_A,
        meal_type="lunch",
        created_at=datetime.datetime.combine(target_date, datetime.time(12, 0)),
    )

    assert get_next_default_preset("lunch", target_date, _OWNER_A) == [
        {"food_type": "salad", "weight_grams": 150}
    ]


def test_get_next_default_preset_rotation_is_scoped_per_owner():
    """Both the presets and the usage tracking that rotates them are
    per-owner: two owners each configure the same dinner preset, and only
    the owner who actually logged dinner this week sees their own rotation
    advance — the other owner's identical preset stays on the first
    option."""
    target_date = datetime.date(2026, 3, 2)
    day_of_week = target_date.weekday()

    for owner_user_id in (_OWNER_A, _OWNER_B):
        add_meal_default_item(
            meal_type="dinner",
            day_of_week=day_of_week,
            preset_order=1,
            item_order=1,
            food_type="soup",
            weight_grams=250,
            owner_user_id=owner_user_id,
        )
        add_meal_default_item(
            meal_type="dinner",
            day_of_week=day_of_week,
            preset_order=2,
            item_order=1,
            food_type="stew",
            weight_grams=250,
            owner_user_id=owner_user_id,
        )

    insert_food_type(
        file_uid=_unique_file_uid(),
        food_type="soup",
        glycemic_index=30,
        weight_grams=250,
        owner_user_id=_OWNER_A,
        meal_type="dinner",
        created_at=datetime.datetime.combine(target_date, datetime.time(20, 0)),
    )

    # Owner A already logged dinner this week -> rotates to the 2nd preset.
    assert get_next_default_preset("dinner", target_date, _OWNER_A) == [
        {"food_type": "stew", "weight_grams": 250}
    ]
    # Owner B hasn't logged anything -> still on the 1st preset, even though
    # they have their own identical preset configured.
    assert get_next_default_preset("dinner", target_date, _OWNER_B) == [
        {"food_type": "soup", "weight_grams": 250}
    ]
