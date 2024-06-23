#!/usr/bin/env python3
import openai
import os 
import base64
from openai import OpenAI

def encode_image(image_file:str)->bytes:
    with open(image_file, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def classify_image(image_file:str):
    client = OpenAI()
    base_64_image:bytes = encode_image(image_file)
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
    print(response.to_dict()['choices'][0]['message']['content'].replace("json", "").replace("```", ""))


classify_image("/Users/rbean/temp/IMG_0617.png")
classify_image("/Users/rbean/temp/IMG_0618.png")