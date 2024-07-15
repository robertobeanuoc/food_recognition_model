from food_recognition.db import insert_food_type

def test_insert_food_type():
    insert_food_type("banana", 51, 120)