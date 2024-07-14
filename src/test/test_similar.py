
from food_recognition.similar_food import find_similar_food
from food_recognition.db import get_food_register


def test_get_food_types():
    find_similar_food(food_type="chocolate-coated ice cream bar")

def test_get_food_register():
    get_food_register(start_date="2024-07-04")
    

test_get_food_register()



