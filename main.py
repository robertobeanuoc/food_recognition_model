from flask import Flask, render_template, request, redirect, url_for
import cv2
import numpy as np
import os
from datetime import datetime
from food_clasification import classify_image
from utils import app_logger
from db import insert_food_type
import ssl

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads/'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    # Check if the post request has the file part
    if 'photo' not in request.files:
        error_message: str = "Error: No file part in the request."
        app_logger.error(error_message)
        return error_message
    file = request.files['photo']
    if not file:
        error_message: str = "Error: No file uploaded."
        app_logger.error(error_message)
        return error_message

    # Convert file to numpy array
    message_info: str = "Convert file to numpy array"
    app_logger.info(message_info)
    file_bytes = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)


    # Remove all files under uploads folder
    for file in os.listdir(UPLOAD_FOLDER):
        os.remove(os.path.join(UPLOAD_FOLDER, file))

    # Save the image
    app_logger.info("Saving the image ..")
    filename = datetime.now().strftime("%Y%m%d%H%M%S") + '.jpg'
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    cv2.imwrite(filepath, img)
    app_logger.info(f"Image saved at {filepath}")

    food_types:list[dict] = classify_image(filepath)
    for food_type in food_types:
        insert_food_type(food_type=food_type['food_type'], glycemic_index=food_type['glycemic_index'], weight_grams=food_type['weight_grams'])
    


    return redirect(url_for('view_photo', filename=filepath))


@app.route('/view_photo/<filename>')
def view_photo(filename):
    return render_template('view_photo.html', filename=filename)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5010, ssl_context='adhoc')
