#!/usr/bin/env python3
import base64
from time import sleep
from openai import OpenAI
from food_recognition.utils import app_logger
import os
from food_recognition.utils import extract_json_from_openai
from food_recognition.constants import WAIT_TIME_OPEANAI_API


def encode_image(image_file:str)->bytes:
    with open(image_file, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def classify_image(image_file:str) -> dict:
    output_json: dict = {}
    openai_api_key = os.getenv("OPENAI_API_KEY")
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
            "text": "Identify all food types in the image, and for each food type, determine the glycemic index and estimate its weight in grams. Export this information as a JSON array where each element is an object with the following key-value pairs: food_type for the food type, glycemic_index for the glycemic index, and weight_grams for the estimated weight in grams.",
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
    max_tokens=300,
    )
    sleep(WAIT_TIME_OPEANAI_API)
    output_json = extract_json_from_openai(response)
    return output_json


    
    
    