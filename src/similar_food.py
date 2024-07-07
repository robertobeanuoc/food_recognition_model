
from openai import OpenAI
from utils import app_logger
import os
from db import get_food_types
from jinja2 import Template
from constants import SIMILAR_JINJA2_TEMPLATE


def render_template(food_type: str, food_types: dict) -> str:
    app_logger.info(f"{os.getcwd()}")
    template: str = open(SIMILAR_JINJA2_TEMPLATE).read()
    template = Template(template)
    rendered_template = template.render(food_type=food_type, food_types=food_types)
    return rendered_template


def find_similar_food(food_type:str) -> dict:
    food_types: dict = get_food_types()

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
            "text": f"{render_template(food_type=food_type, food_types=food_types)}",
            },
        ],
        }
    ],
    max_tokens=4096,
    )

    print(response.to_dict()['choices'][0]['message']['content'])

    

    # output_json: dict = 
    