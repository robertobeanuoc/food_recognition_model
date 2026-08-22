import datetime
import uuid as uuid_lib

from food_recognition.db import (
    delete_food_register,
    get_food_registers,
    insert_food_type,
    update_food_register,
    utcnow,
)

_OWNER_A = "test-owner-a"
_OWNER_B = "test-owner-b"


def _unique_file_uid() -> str:
    return str(uuid_lib.uuid4())


def test_insert_food_type_creates_row():
    file_uid = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid,
        food_type="banana",
        glycemic_index=51,
        weight_grams=120,
        owner_user_id=_OWNER_A,
    )

    rows = get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)

    assert len(rows) == 1
    assert rows[0]["food_type"] == "banana"
    assert rows[0]["glycemic_index"] == 51
    assert rows[0]["weight_grams"] == 120


def test_update_food_register_updates_fields():
    file_uid = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid,
        food_type="apple",
        glycemic_index=36,
        weight_grams=100,
        owner_user_id=_OWNER_A,
    )
    row = get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)[0]

    update_food_register(
        uuid=row["uuid"],
        owner_user_id=_OWNER_A,
        food_type="green apple",
        glycemic_index=40,
        weight_grams=150,
        verified=1,
    )

    updated_row = get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)[0]
    assert updated_row["food_type"] == "green apple"
    assert updated_row["glycemic_index"] == 40
    assert updated_row["weight_grams"] == 150
    assert updated_row["verified"] == 1


def test_delete_food_register_removes_row():
    file_uid = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid,
        food_type="rice",
        glycemic_index=73,
        weight_grams=200,
        owner_user_id=_OWNER_A,
    )
    row = get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)[0]

    delete_food_register(uuid=row["uuid"], owner_user_id=_OWNER_A)

    assert get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid) == []


def test_get_food_registers_only_returns_the_requesting_owners_rows():
    file_uid = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid,
        food_type="banana",
        glycemic_index=51,
        weight_grams=120,
        owner_user_id=_OWNER_A,
    )

    assert len(get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)) == 1
    assert get_food_registers(owner_user_id=_OWNER_B, file_uid=file_uid) == []


def test_update_food_register_cannot_touch_another_owners_row():
    file_uid = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid,
        food_type="apple",
        glycemic_index=36,
        weight_grams=100,
        owner_user_id=_OWNER_A,
    )
    row = get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)[0]

    # Attempting the update as a different owner must be a no-op — it should
    # not raise, but it must not change the row either (the WHERE clause
    # simply matches nothing).
    update_food_register(
        uuid=row["uuid"],
        owner_user_id=_OWNER_B,
        food_type="tampered",
    )

    unchanged_row = get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)[0]
    assert unchanged_row["food_type"] == "apple"


def test_two_owners_logging_food_today_each_only_see_their_own():
    """End-to-end version of the other isolation tests above: two different
    owners each log a meal *today* (the exact scenario a real /meals page
    load exercises — `start_date` filtering included, not just `file_uid`),
    and each owner's get_food_registers() call must return only their own
    row. Nothing here is cleaned up manually — conftest.py's db_transaction
    fixture wraps every test in a savepoint that's rolled back at teardown,
    so both rows (and every other table's rows this test touches) are gone
    the instant the test ends, the same way for food_register as for any
    other per-owner table.
    """
    today = utcnow()
    day_start = today.replace(hour=0, minute=0, second=0, microsecond=0)

    file_uid_a = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid_a,
        food_type="test-two-owners-pizza",
        glycemic_index=60,
        weight_grams=250,
        owner_user_id=_OWNER_A,
        created_at=today,
    )
    file_uid_b = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid_b,
        food_type="test-two-owners-salad",
        glycemic_index=20,
        weight_grams=180,
        owner_user_id=_OWNER_B,
        created_at=today,
    )

    owner_a_today = get_food_registers(owner_user_id=_OWNER_A, start_date=day_start)
    owner_b_today = get_food_registers(owner_user_id=_OWNER_B, start_date=day_start)

    assert [row["food_type"] for row in owner_a_today] == ["test-two-owners-pizza"]
    assert [row["food_type"] for row in owner_b_today] == ["test-two-owners-salad"]


def test_delete_food_register_cannot_touch_another_owners_row():
    file_uid = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid,
        food_type="rice",
        glycemic_index=73,
        weight_grams=200,
        owner_user_id=_OWNER_A,
    )
    row = get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)[0]

    delete_food_register(uuid=row["uuid"], owner_user_id=_OWNER_B)

    assert len(get_food_registers(owner_user_id=_OWNER_A, file_uid=file_uid)) == 1
