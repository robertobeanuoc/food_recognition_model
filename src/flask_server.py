
import shutil
from flask import Flask, session ,render_template, request, redirect, url_for
import cv2
import numpy as np
import os
from datetime import datetime
from food_recognition.food_classification import classify_image
from food_recognition.utils import app_logger
from food_recognition.db import insert_food_type
from food_recognition.similar_food import add_similar_food_info_to_food, find_similar_food
import json
import uuid

app = Flask(__name__,static_folder='food_recognition/static', template_folder='food_recognition/templates')
app.secret_key = os.getenv('SECRET_KEY')

UPLOAD_FOLDER = 'src/food_recognition/static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST','GET'])
def upload():
    
    if 'file' not in request.files:
        error_message: str= "Error: No file part in the request."
        app_logger.error(error_message)
        return error_message
    
    file = request.files['file']
    if file.filename == '':
        error_message: str = "Error: No file uploaded."
        app_logger.error(error_message)
        return error_message
    
    


    # Convert file to numpy array
    message_info: str = "Convert file to numpy array"
    app_logger.info(message_info)
    file_bytes = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)    # Save the image

    # Remove all files under uploads folder
    for file in os.listdir(UPLOAD_FOLDER):
        os.remove(os.path.join(UPLOAD_FOLDER, file))

    uuid_img, file_image = save_image(img)


    app_logger.info("Classifying the image ..")
    food_types:list[dict] = classify_image(file_image)
    for food_type in food_types:
        insert_food_type(file_uid=uuid_img,food_type=food_type['food_type'], glycemic_index=food_type['glycemic_index'], weight_grams=food_type['weight_grams'])

    file_json:str = os.path.join(UPLOAD_FOLDER,f"{uuid_img}.json")
    with open(file_json, 'w') as f:
        f.write(json.dumps(food_types))

    save_files_to_storage(file_image=file_image, file_json=file_json)
    
    session['food_types'] = add_similar_food_info_to_food(food_types=food_types)
    

    return redirect(url_for('view_photo', uuid_img=uuid_img,food_types=food_types))

def save_image(img)->str:
    app_logger.info("Saving the image ..")
    uuid_img: str = str(uuid.uuid4())
    filename_image:str = f"{uuid_img}.jpg"
    filepath:str = os.path.join(UPLOAD_FOLDER, filename_image)
    cv2.imwrite(filepath, img)
    app_logger.info(f"Image saved at {filepath}")
    app_logger.info("Saving image in photo folder ..")
    return uuid_img,filepath

def save_files_to_storage(file_image:str, file_json:str):
    app_logger.info("Copying the folder content to another folder ..")
    try:
        upload_folder: str = os.getenv("PHOTO_FOLDER")
        shutil.copy(file_image, os.path.join(upload_folder, os.path.basename(file_image)))
        shutil.copy(file_json, os.path.join(upload_folder, os.path.basename(file_json)))

        app_logger.info("Folder content copied successfully.")
    except Exception as e:
        app_logger.error(f"Error copying folder content: {e}")


@app.route('/view_photo/<uuid_img>')
def view_photo(uuid_img):    

    app_logger.info(f"Viewing photo {uuid_img}")
    return render_template('view_photo.html', uuid_img=uuid_img, app_logger=app_logger)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5010, ssl_context='adhoc')
