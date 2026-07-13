
import datetime
import shutil
import threading
from flask import Flask, session ,render_template, request, redirect, url_for, Blueprint
import cv2
import numpy as np
import os
import pytz
from food_recognition.food_classification import classify_image
from food_recognition.utils import app_logger
from food_recognition.db import get_glycemic_index, insert_food_type, update_food_register, update_verfied, get_food_registers, get_glycemic_index, update_food_register, delete_food_register, sync_schema, get_meal_schedule, update_meal_schedule, get_meal_types, utcnow, get_food_types, upsert_food_characteristics, get_meal_default_items, add_meal_default_item, update_meal_default_item, delete_meal_default_item
from food_recognition.similar_food import add_similar_food_info_to_food
from food_recognition import reminder_scheduler, slack_bot
import json
import uuid

from flask_session import Session

from food_recognition.validate_parameters import validate_food_type, validate_uuid


app = Flask(__name__,static_folder='food_recognition/static', template_folder='food_recognition/templates')
app.secret_key = os.getenv('SECRET_KEY')
# Set ahead of app.run(debug=True, ...) at the bottom of this file so the
# WERKZEUG_RUN_MAIN guard below (which runs before app.run() is ever called)
# can tell whether the dev-server reloader is in play.
app.debug = True

additionnal_static: Blueprint = Blueprint('additional_static', __name__, static_folder=os.getenv('PHOTO_FOLDER'),static_url_path='/photo')
app.register_blueprint(additionnal_static)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = app.secret_key
UPLOAD_FOLDER:str = 'food_recognition/static/uploads'

Session(app)

# Sync the DB schema with the current SQLAlchemy models (creates any missing
# tables, e.g. meal_schedule) as soon as the app connects to the database.
sync_schema()


def _run_slack_bot() -> None:
    try:
        slack_bot.start_bot()
    except Exception as e:
        app_logger.error(f"Slack bot failed to start (meal reminders via Slack disabled): {e}")


# Flask's debug reloader (implied by debug=True in the __main__ block below)
# re-imports this module in a watcher process before spawning the actual
# worker process — only WERKZEUG_RUN_MAIN='true' identifies the worker, so
# guard against starting the scheduler/Slack bot twice.
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    reminder_scheduler.start_scheduler()
    threading.Thread(target=_run_slack_bot, daemon=True, name="slack-bot").start()


def get_request_timezone() -> datetime.tzinfo:
    """Resolve the browser timezone captured by the `tz` cookie (see base.html).

    All datetimes are stored in the database as naive UTC. Falls back to UTC
    if the cookie is missing (e.g. first request of a session, before the
    page's JS has had a chance to set it) or holds an unrecognised value.
    """
    tz_name: str = request.cookies.get('tz', 'UTC')
    try:
        return pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        return pytz.utc


@app.template_filter('local_dt')
def local_dt_filter(value: datetime.datetime, fmt: str = '%Y-%m-%d %H:%M') -> str:
    """Render a naive-UTC datetime in the requesting browser's timezone."""
    if value is None:
        return ''
    utc_value: datetime.datetime = pytz.utc.localize(value) if value.tzinfo is None else value
    return utc_value.astimezone(get_request_timezone()).strftime(fmt)


def _utc_time_to_local(value: datetime.time, tz: datetime.tzinfo) -> datetime.time:
    """Convert a bare UTC time-of-day (e.g. meal_schedule.start_time) to local.

    TIME columns have no date, so today's date is used as an arbitrary
    reference to resolve the UTC offset (relevant around DST transitions).
    """
    reference_date: datetime.date = datetime.date.today()
    utc_dt: datetime.datetime = pytz.utc.localize(datetime.datetime.combine(reference_date, value))
    return utc_dt.astimezone(tz).time()


def _local_time_to_utc(value: datetime.time, tz: datetime.tzinfo) -> datetime.time:
    """Inverse of `_utc_time_to_local` — convert a browser-local time-of-day to UTC for storage."""
    reference_date: datetime.date = datetime.date.today()
    local_dt: datetime.datetime = tz.localize(datetime.datetime.combine(reference_date, value))
    return local_dt.astimezone(pytz.utc).time()


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
    # Computed once and shared across every item in this photo, so they all
    # get the exact same created_at (and therefore the same auto-classified
    # meal_type) instead of drifting a few milliseconds apart per insert.
    created_at: datetime.datetime = utcnow()
    for food_type in food_types:
        insert_food_type(
            file_uid=uuid_img,
            food_type=food_type['food_type'],
            glycemic_index=food_type['glycemic_index'],
            weight_grams=food_type['weight_grams'],
            carbohydrate_percentage=food_type.get('carbohydrate_percentage'),
            carbohydrate_weight_grams=food_type.get('carbohydrate_weight_grams'),
            absorption_type=food_type.get('absorption_type'),
            created_at=created_at,
        )

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

    validate_uuid(uuid)
    validate_food_type(food_type)
    app_logger.info(f"Updating food_register for {uuid} ..")

    carbohydrate_percentage: float = None
    carbohydrate_weight_grams: float = None
    if request.args.get('carbohydrate_percentage'):
        carbohydrate_percentage = float(request.args['carbohydrate_percentage'])
        carbohydrate_weight_grams = carbohydrate_percentage * weight_grams / 100

    meal_type: str = request.args.get('meal_type') or None

    update_food_register(
        uuid=uuid,
        food_type=food_type,
        glycemic_index=glycemic_index,
        weight_grams=weight_grams,
        verified=verified,
        carbohydrate_percentage=carbohydrate_percentage,
        carbohydrate_weight_grams=carbohydrate_weight_grams,
        meal_type=meal_type,
    )
    #TODO return to the previus page
    return redirect(url_for('meals'))


@app.route('/delete_food_register/<uuid>', methods=['DELETE'])
def api_delete_food_register(uuid: str):
    validate_uuid(uuid)
    app_logger.info(f"Deleting food_register {uuid} ..")
    delete_food_register(uuid=uuid)
    return {"status": "ok"}


@app.route('/view_photo/<file_uid>', methods=['GET'])
def view_photo(file_uid:str):
    created_at: datetime.datetime = None
    validate_uuid(file_uid)
    food_registers: list[dict] = get_food_registers(file_uid=file_uid)
    food_registers = add_similar_food_info_to_food(food_registers=food_registers)
    if len(food_registers) != 0:
        created_at = food_registers[0]['created_at']
    meal_types: list[str] = get_meal_types()
    return render_template('view_photo.html', uuid_img=file_uid,food_registers=food_registers, created_at=created_at, meal_types=meal_types )

@app.route('/meals', methods=['GET','POST'])
def meals():
    user_tz: datetime.tzinfo = get_request_timezone()

    start_date: str = ""
    if 'datepicker' in request.form:
        start_date = request.form['datepicker']
    filter_start_date: datetime.date
    if start_date:
        filter_start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        today_local: datetime.date = datetime.datetime.now(tz=user_tz).date()
        filter_start_date = today_local - datetime.timedelta(days=int(os.getenv("DEFAULT_DAYS")))

    # The date picker is a plain calendar date in the user's local timezone;
    # convert local midnight of that date to UTC before filtering, since
    # created_at is stored as naive UTC.
    local_midnight: datetime.datetime = user_tz.localize(datetime.datetime.combine(filter_start_date, datetime.time.min))
    start_datetime_utc: datetime.datetime = local_midnight.astimezone(pytz.utc).replace(tzinfo=None)

    food_registers: list[dict] = get_food_registers(start_date=start_datetime_utc)
    return render_template('meals.html', food_registers=food_registers, start_date=filter_start_date)


@app.route('/meal_schedule', methods=['GET'])
def meal_schedule():
    user_tz: datetime.tzinfo = get_request_timezone()
    meal_schedule_rows: list[dict] = get_meal_schedule()
    for row in meal_schedule_rows:
        row['start_time'] = _utc_time_to_local(row['start_time'], user_tz)
        row['end_time'] = _utc_time_to_local(row['end_time'], user_tz)
    return render_template('meal_schedule.html', meal_schedule_rows=meal_schedule_rows)


@app.route('/update_meal_schedule/<uuid>', methods=['POST'])
def api_update_meal_schedule(uuid: str):
    validate_uuid(uuid)
    app_logger.info(f"Updating meal_schedule for {uuid} ..")

    user_tz: datetime.tzinfo = get_request_timezone()
    local_start_time = datetime.datetime.strptime(request.form['start_time'], '%H:%M').time()
    local_end_time = datetime.datetime.strptime(request.form['end_time'], '%H:%M').time()

    start_time = _local_time_to_utc(local_start_time, user_tz)
    end_time = _local_time_to_utc(local_end_time, user_tz)

    update_meal_schedule(uuid=uuid, start_time=start_time, end_time=end_time)
    return {"status": "ok"}


@app.route('/food_characteristics', methods=['GET'])
def food_characteristics():
    food_types: list[dict] = get_food_types()
    return render_template('food_characteristics.html', food_types=food_types)


@app.route('/update_food_characteristics/<food_type>', methods=['POST'])
def api_update_food_characteristics(food_type: str):
    validate_food_type(food_type)
    app_logger.info(f"Updating food_characteristics for {food_type} ..")

    glycemic_index_value: int = None
    if request.form.get('glycemic_index'):
        glycemic_index_value = int(request.form['glycemic_index'])

    carbohydrate_percentage: float = None
    if request.form.get('carbohydrate_percentage'):
        carbohydrate_percentage = float(request.form['carbohydrate_percentage'])

    upsert_food_characteristics(
        food_type=food_type,
        food_type_es=request.form.get('food_type_es'),
        glycemic_index=glycemic_index_value,
        carbohydrate_percentage=carbohydrate_percentage,
        absorption_type=request.form.get('absorption_type'),
    )
    return {"status": "ok"}


@app.route('/glycemic_index/<food_type>', methods=['GET'])
def glycemic_index(food_type:str):
    glycemic_index:int = get_glycemic_index(food_type=food_type)
    return str(glycemic_index)


# Day names for the /meal_default_presets UI, Monday-first to match
# db_models.MealDefaultItem.day_of_week (Python date.weekday(), Monday=0).
_DAY_OF_WEEK_LABELS: list[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@app.route('/meal_default_presets', methods=['GET'])
def meal_default_presets():
    items: list[dict] = get_meal_default_items()
    meal_types: list[str] = [m for m in get_meal_types() if m != 'other']
    return render_template(
        'meal_default_presets.html',
        items=items,
        meal_types=meal_types,
        day_labels=_DAY_OF_WEEK_LABELS,
    )


@app.route('/add_meal_default_item', methods=['POST'])
def api_add_meal_default_item():
    meal_type: str = request.form['meal_type']
    validate_food_type(meal_type)  # reused: just guards against path/URL-breaking characters
    day_of_week: int = int(request.form['day_of_week'])
    preset_order: int = int(request.form['preset_order'])
    item_order: int = int(request.form['item_order'])
    food_type: str = request.form['food_type']
    validate_food_type(food_type)
    weight_grams: int = None
    if request.form.get('weight_grams'):
        weight_grams = int(request.form['weight_grams'])

    new_uuid: str = add_meal_default_item(
        meal_type=meal_type,
        day_of_week=day_of_week,
        preset_order=preset_order,
        item_order=item_order,
        food_type=food_type,
        weight_grams=weight_grams,
    )
    return {"status": "ok", "uuid": new_uuid}


@app.route('/update_meal_default_item/<uuid>', methods=['POST'])
def api_update_meal_default_item(uuid: str):
    validate_uuid(uuid)
    app_logger.info(f"Updating meal_default_item {uuid} ..")

    food_type: str = request.form.get('food_type')
    if food_type:
        validate_food_type(food_type)
    weight_grams: int = None
    if request.form.get('weight_grams'):
        weight_grams = int(request.form['weight_grams'])

    update_meal_default_item(uuid=uuid, food_type=food_type, weight_grams=weight_grams)
    return {"status": "ok"}


@app.route('/delete_meal_default_item/<uuid>', methods=['DELETE'])
def api_delete_meal_default_item(uuid: str):
    validate_uuid(uuid)
    app_logger.info(f"Deleting meal_default_item {uuid} ..")
    delete_meal_default_item(uuid=uuid)
    return {"status": "ok"}


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5010, ssl_context='adhoc')
