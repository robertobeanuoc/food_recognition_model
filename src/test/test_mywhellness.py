import os
from food_recognition.mywhelness import get_token

username: str= os.getenv("MYWELLNESS_USERNAME")
password: str= os.getenv("MYWELLNESS_PASSWORD") 

token = get_token(username=username, password=password)