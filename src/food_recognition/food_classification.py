#!/usr/bin/env python3
import base64
from openai import OpenAI
from food_recognition.utils import app_logger
import os
import re
import json


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
    message_response:str = response.to_dict()['choices'][0]['message']['content'].replace("json", "").replace("```", "")
    app_logger.info(f"Message response: {message_response}")
    json_files:list[str] = re.findall(r'\[[\s\S]*?\]',message_response)
    if json_files.count == 0 or json_files is None:
        app_logger.error("No json file found")
    else:        
        try:
            message_json:str = json_files[0]
            app_logger.info(f"Message json: {message_json}")
            output_json = json.loads(message_json)
        except Exception as e:
            output_json = {}
            app_logger.error(f"Error: {e}")
    return output_json
    
    
    