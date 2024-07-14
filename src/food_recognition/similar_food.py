
from time import sleep
from openai import OpenAI
from food_recognition.utils import app_logger, extract_json_from_openai
import os
from food_recognition.db import get_food_types, get_food_types_list, get_glycemic_index
from jinja2 import Template
from food_recognition.constants import SIMILAR_JINJA2_TEMPLATE, WAIT_TIME_OPEANAI_API



def render_template(food_type: str, food_types: dict) -> str:
    app_logger.info(f"{os.getcwd()}")
    template: str = open(SIMILAR_JINJA2_TEMPLATE).read()
    template = Template(template)
    rendered_template = template.render(food_type=food_type, food_types=food_types)
    return rendered_template


def find_similar_food(food_type:str) -> str:
    food_types: dict = get_food_types()
    ret_similar_food: str = ""

        
    csv_string = "food_type,food_type_es\n"
    
    for food in food_types:
        if food['glycemic_index'] and food['glycemic_index'] >0:
            csv_string += f"{food['food_type']},{food['food_type_es']}\n"

    openai_api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {
        "role": "user",
        "content": [
            {
            "type": "text",
            "text": f"{render_template(food_type=food_type, food_types=csv_string)}",
            },
        ],
        }
    ],
    max_tokens=4096,
    )

    similar_food: dict = extract_json_from_openai(response=response)

    ret_similar_food: str = similar_food['food_type']

    sleep(WAIT_TIME_OPEANAI_API)

    return ret_similar_food


def add_similar_food_info_to_food(food_types: list[dict]) -> dict:
    ret_food_types: list[dict] = []
    for food_type in food_types:
        food_type['similar_food'] = find_similar_food(food_type['food_type'])
        food_type['similar_glycemic_index'] = get_glycemic_index(food_type['similar_food'])
        food_type['all_food_types'] = get_food_types_list(food_type=food_type['food_type'])
        ret_food_types.append(food_type)
    return ret_food_types

    