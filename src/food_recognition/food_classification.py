#!/usr/bin/env python3
import base64
from time import sleep
from openai import OpenAI
from food_recognition.utils import app_logger
from food_recognition import vault_client
from food_recognition.utils import extract_json_from_openai
from food_recognition.constants import WAIT_TIME_OPEANAI_API


def encode_image(image_file:str)->bytes:
    with open(image_file, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def classify_image(image_file:str) -> dict:
    output_json: dict = {}
    openai_api_key = vault_client.get_openai_secrets()["api_key"]
    client = OpenAI(api_key=openai_api_key)
    base_64_image:bytes = encode_image(image_file)
    message_info: str = "Create message for open ai"
    app_logger.info(f"Message info: {message_info}")
    response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {
        "role": "user",
        "content": [
            {
            "type": "text",
            "text": (
                "Identify all food types in the image. For each food type, determine: "
                "(1) the glycemic index (integer), "
                "(2) the estimated weight in grams (integer), "
                "(3) the carbohydrate percentage of the food as a decimal between 0 and 100 (e.g. 45.5), "
                "(4) the carbohydrate weight in grams calculated as carbohydrate_percentage * weight_grams / 100 (rounded to one decimal), "
                "(5) the absorption type: 'slow' if glycemic_index < 55, 'fast' if glycemic_index >= 55. "
                "Export as a JSON array where each element has keys: "
                "food_type, glycemic_index, weight_grams, carbohydrate_percentage, carbohydrate_weight_grams, absorption_type."
            ),
            },
            {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{base_64_image}"
            },
            },
        ],
        }
    ],
    max_tokens=600,
    )
    sleep(WAIT_TIME_OPEANAI_API)
    output_json = extract_json_from_openai(response)
    return output_json


def classify_food_characteristics(food_type: str) -> dict:
    """Ask GPT-4o for the glycemic_index/carbohydrate_percentage/absorption_type
    of a food by name only, no image — used when a food_type has no row (or an
    incomplete one) in food_characteristics yet, e.g. a food typed in free-text
    via the Slack "Other (new food)" manual-log option (see slack_bot.py).
    """
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
            "text": (
                f"For the food '{food_type}', determine: "
                "(1) the glycemic index (integer), "
                "(2) the carbohydrate percentage of the food as a decimal between 0 and 100 (e.g. 45.5), "
                "(3) the absorption type: 'slow' if glycemic_index < 55, 'fast' if glycemic_index >= 55. "
                "Export as a JSON object with keys: glycemic_index, carbohydrate_percentage, absorption_type."
            ),
            },
        ],
        }
    ],
    max_tokens=300,
    )
    sleep(WAIT_TIME_OPEANAI_API)
    return extract_json_from_openai(response)

    