
import datetime
import shutil
from flask import Flask, session ,render_template, request, redirect, url_for, Blueprint
import cv2
import numpy as np
import os
from food_recognition.food_classification import classify_image
from food_recognition.utils import app_logger
from food_recognition.db import get_glycemic_index, insert_food_type, update_food_register, update_verfied, get_food_registers, get_glycemic_index, update_food_register
from food_recognition.similar_food import add_similar_food_info_to_food
import json
import uuid

from flask_session import Session


app = Flask(__name__,static_folder='food_recognition/static', template_folder='food_recognition/templates')
app.secret_key = os.getenv('SECRET_KEY')

additionnal_static: Blueprint = Blueprint('additional_static', __name__, static_folder=os.getenv('PHOTO_FOLDER'),static_url_path='/photo')
app.register_blueprint(additionnal_static)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = app.secret_key
UPLOAD_FOLDER:str = 'food_recognition/static/uploads'

Session(app)

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

    app_logger.info(f"Current working  directory: {os.getcwd()}")
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
        
    return redirect(url_for('view_photo', file_uid=uuid_img))

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


@app.route('/update_values', methods=['POST'])
def update_values():
    app_logger.info("Updating values ..")
    num_food_types:int = 0
    if 'num_food_types' in request.form:
        num_food_types = int(request.form['num_food_types'])
    uuid_img:str = request.form['uuid_img']
    for i in range(1, num_food_types+1):
        food_type = request.form[f'food_type_{i}']
        glycemic_index:int =  get_glycemic_index(food_type=food_type)
        weight_grams:int = int(request.form[f'weight_grams_{i}'])
        update_food_register(file_uid=uuid_img, food_type=food_type, glycemic_index=glycemic_index, weight_grams=weight_grams)

    return redirect(url_for('view_photo', file_uid=uuid_img))



@app.route('/update_food_register/<uuid>/<food_type>/<int:glycemic_index>/<int:weight_grams>/<int:verified>', methods=['GET'])
def api_update_food_register(uuid:str, food_type:str, glycemic_index:int, weight_grams:int, verified:int):
    app_logger.info(f"Updating food_register for {uuid} ..")
    update_food_register(uuid=uuid, food_type=food_type, glycemic_index=glycemic_index, weight_grams=weight_grams, verified=verified)
    #TODO return to the previus page
    return redirect(url_for('meals'))


@app.route('/view_photo/<file_uid>', methods=['GET'])
def view_photo(file_uid:str):
    created_at:str = ""
    food_registers: list[dict] = get_food_registers(file_uid=file_uid)
    food_registers = add_similar_food_info_to_food(food_registers=food_registers)
    if len(food_registers) != 0:
        created_at: str = food_registers[0]['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return render_template('view_photo.html', uuid_img=file_uid,food_registers=food_registers, created_at=created_at )

@app.route('/meals', methods=['GET','POST'])
def meals():
    start_date: str = ""
    if 'datepicker' in request.form:
        start_date = request.form['datepicker']
    filter_start_date:datetime.date = datetime.date.today()
    if start_date:
        filter_start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        filter_start_date = filter_start_date - datetime.timedelta(days=int(os.getenv("DEFAULT_DAYS")))
    food_registers: list[dict] = get_food_registers(start_date=filter_start_date) 
    return render_template('meals.html', food_registers=food_registers, start_date=filter_start_date)


@app.route('/glycemic_index/<food_type>', methods=['GET'])
def glycemic_index(food_type:str):
    glycemic_index:int = get_glycemic_index(food_type=food_type)
    return str(glycemic_index)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5010, ssl_context='adhoc')
