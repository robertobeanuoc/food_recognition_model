from flask import Flask, session ,render_template, request, redirect, url_for
import cv2
import numpy as np
import os
from datetime import datetime
from food_classification import classify_image
from utils import app_logger
from db import insert_food_type
import json
import uuid

app = Flask(__name__,static_folder='static', template_folder='templates')
app.secret_key = os.getenv('SECRET_KEY')

UPLOAD_FOLDER = 'static/uploads/'
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
    app_logger.info("Saving the image ..")
    uuid_img: str = str(uuid.uuid4())
    filename_image:str = f"{uuid_img}.jpg"
    filepath:str = os.path.join(UPLOAD_FOLDER, filename_image)
    cv2.imwrite(filepath, img)
    app_logger.info(f"Image saved at {filepath}")

    food_types:list[dict] = classify_image(filepath)

    for food_type in food_types:
        insert_food_type(food_type=food_type['food_type'], glycemic_index=food_type['glycemic_index'], weight_grams=food_type['weight_grams'])
    
    file_name_json:str = os.path.join(UPLOAD_FOLDER,f"{uuid_img}.json")
    with open(file_name_json, 'w') as f:
        f.write(json.dumps(food_types))
    
    session['food_types'] = json.dumps(food_types)
    

    return redirect(url_for('view_photo', uuid_img=uuid_img,food_types=food_types))


@app.route('/view_photo/<uuid_img>')
def view_photo(uuid_img):    

    app_logger.info(f"Viewing photo {uuid_img}")
    return render_template('view_photo.html', uuid_img=uuid_img, food_types=session['food_types'])

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5010, ssl_context='adhoc')
