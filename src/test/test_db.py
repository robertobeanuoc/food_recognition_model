import uuid as uuid_lib

from food_recognition.db import (
    delete_food_register,
    get_food_registers,
    insert_food_type,
    update_food_register,
)


def _unique_file_uid() -> str:
    return str(uuid_lib.uuid4())


def test_insert_food_type_creates_row():
    file_uid = _unique_file_uid()
    insert_food_type(
        file_uid=file_uid,
        food_type="banana",
        glycemic_index=51,
        weight_grams=120,
    )

    rows = get_food_registers(file_uid=file_uid)

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
    )
    row = get_food_registers(file_uid=file_uid)[0]

    update_food_register(
        uuid=row["uuid"],
        food_type="green apple",
        glycemic_index=40,
        weight_grams=150,
        verified=1,
    )

    updated_row = get_food_registers(file_uid=file_uid)[0]
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
    )
    row = get_food_registers(file_uid=file_uid)[0]

    delete_food_register(uuid=row["uuid"])

    assert get_food_registers(file_uid=file_uid) == []
