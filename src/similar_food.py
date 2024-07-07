import base64
from openai import OpenAI
from utils import app_logger
import os
import re
import json


def find_similar_food(food:str) -> dict:
    output_json: dict = {}
    