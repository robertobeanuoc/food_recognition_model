import re


def test_regular_expression():
    example_string:str = '\n[\n  {\n    "food_type": "banana",\n    "glycemic_index": 51,\n    "weight_grams": 120\n  },\n  {\n    "food_type": "apple",\n    "glycemic_index": 39,\n    "weight_grams": 150\n  }\n]\n'
    assert re.search('\[(.|\s)*\]', example_string) is not None
    




