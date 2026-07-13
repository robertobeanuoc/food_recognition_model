
from time import sleep
from openai import OpenAI
from food_recognition.utils import app_logger, extract_json_from_openai
import os
from food_recognition import vault_client
from food_recognition.db import (
    get_food_types,
    get_food_types_list,
    get_glycemic_index,
    update_food_register_similar_food,
)
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

    openai_api_key = vault_client.get_openai_secrets()["api_key"]
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


def add_similar_food_info_to_food(food_registers: list[dict]) -> dict:
    """Fill in `similar_food`/`similar_glycemic_index` for each row, computing
    (and persisting) them via OpenAI only the first time — rows that already
    have a cached value from a previous view are reused as-is, so viewing an
    already-classified photo again doesn't repeat the OpenAI call."""
    ret_food_registers: list[dict] = []
    for food_register in food_registers:
        if food_register.get('similar_food') is None:
            similar_food: str = find_similar_food(food_register['food_type'])
            similar_glycemic_index: int = get_glycemic_index(similar_food)
            update_food_register_similar_food(
                uuid=food_register['uuid'],
                similar_food=similar_food,
                similar_glycemic_index=similar_glycemic_index,
            )
            food_register['similar_food'] = similar_food
            food_register['similar_glycemic_index'] = similar_glycemic_index
        food_register['all_food_types'] = get_food_types_list(food_type=food_register['food_type'])
        ret_food_registers.append(food_register)
    return ret_food_registers

    