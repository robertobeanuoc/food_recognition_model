import datetime
import os
import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from food_recognition.db_models import FoodRegister, GlycemicIndex
from food_recognition.utils import app_logger

ENV_VAR_DB_TZ_DATES: str = os.getenv("DB_TZ_DATES", "UTC")


def convert_utc_to_db_datetime(utc_datetime: datetime.datetime) -> datetime.datetime:
    tz = pytz.timezone(ENV_VAR_DB_TZ_DATES)
    ret_db_datetime: datetime.datetime = utc_datetime.astimezone(tz)
    return ret_db_datetime


def _build_db_url() -> str:
    user: str = os.getenv("DB_USER")
    password: str = os.getenv("DB_PASSWORD")
    host: str = os.getenv("DB_HOST")
    port: str = os.getenv("DB_PORT")
    name: str = os.getenv("DB_NAME")
    return f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{name}"


_engine = create_engine(_build_db_url(), pool_pre_ping=True)
_SessionFactory = sessionmaker(bind=_engine)


def insert_food_type(
    file_uid: str,
    food_type: str,
    glycemic_index: int,
    weight_grams: int,
    carbohydrate_percentage: float = None,
    carbohydrate_weight_grams: float = None,
    absorption_type: str = None,
    created_at: datetime.datetime = None,
):
    if created_at is None:
        created_at = convert_utc_to_db_datetime(datetime.datetime.now(tz=pytz.utc))

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        food_register: FoodRegister = FoodRegister(
            file_uid=file_uid,
            food_type=food_type,
            original_food_type=food_type,
            glycemic_index=glycemic_index,
            original_glycemic_index=glycemic_index,
            weight_grams=weight_grams,
            carbohydrate_percentage=carbohydrate_percentage,
            carbohydrate_weight_grams=carbohydrate_weight_grams,
            absorption_type=absorption_type,
            created_at=created_at,
        )
        session.add(food_register)
        app_logger.info("Record inserted successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


def update_food_register(
    uuid: str,
    food_type: str = None,
    glycemic_index: int = None,
    weight_grams: int = None,
    verified: int = None,
    carbohydrate_percentage: float = None,
    carbohydrate_weight_grams: float = None,
    updated_at: datetime.datetime = None,
):
    if updated_at is None:
        updated_at = datetime.datetime.now()

    values: dict = {"updated_at": updated_at}
    if food_type != None and food_type != "":
        values["food_type"] = food_type
    if glycemic_index != None:
        values["glycemic_index"] = glycemic_index
    if weight_grams != None:
        values["weight_grams"] = weight_grams
    if verified != None:
        values["verified"] = verified
    if carbohydrate_percentage != None:
        values["carbohydrate_percentage"] = carbohydrate_percentage
    if carbohydrate_weight_grams != None:
        values["carbohydrate_weight_grams"] = carbohydrate_weight_grams

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        session.query(FoodRegister).filter(FoodRegister.uuid == uuid).update(
            values, synchronize_session=False
        )
        app_logger.info("Record inserted successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


def delete_food_register(uuid: str) -> None:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        session.query(FoodRegister).filter(FoodRegister.uuid == uuid).delete(
            synchronize_session=False
        )
        app_logger.info("Record deleted successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


def get_food_types(food_type: str = "") -> list[dict]:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(
            GlycemicIndex.food_type,
            GlycemicIndex.food_type_es,
            GlycemicIndex.glycemic_index,
        )
        if food_type:
            query = query.filter(GlycemicIndex.food_type == food_type)
        query = query.order_by(GlycemicIndex.food_type)
        app_logger.info(f"Query: {query}")

        records = query.all()
        app_logger.info("Query executed successfully")

        records_json = [
            {
                "food_type": record.food_type,
                "food_type_es": record.food_type_es,
                "glycemic_index": record.glycemic_index,
            }
            for record in records
        ]
        app_logger.info("Records fetched")

    app_logger.info("Connection closed")
    app_logger.info("Records fetched")
    return records_json


def get_food_registers(
    start_date: datetime.date = None, file_uid: str = None
) -> list[dict]:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(FoodRegister)
        if file_uid:
            query = query.filter(FoodRegister.file_uid == file_uid)
        if start_date:
            query = query.filter(
                FoodRegister.created_at >= start_date.strftime("%Y-%m-%d")
            )
        query = query.order_by(FoodRegister.created_at.desc())
        app_logger.info(f"Query: {query}")

        records = query.all()
        app_logger.info("Query executed successfully")

        records_json = [
            {
                "food_type": record.food_type,
                "glycemic_index": record.glycemic_index,
                "weight_grams": record.weight_grams,
                "created_at": record.created_at,
                "file_uid": record.file_uid,
                "verified": record.verified,
                "uuid": record.uuid,
                "carbohydrate_percentage": record.carbohydrate_percentage,
                "carbohydrate_weight_grams": record.carbohydrate_weight_grams,
                "absorption_type": record.absorption_type,
            }
            for record in records
        ]
        app_logger.info("Records fetched")

    app_logger.info("Connection closed")
    app_logger.info("Records fetched")
    return records_json


def get_glycemic_index(food_type: str) -> int:
    ret_glycemic_index: int = 0

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(GlycemicIndex.glycemic_index).filter(
            GlycemicIndex.food_type == food_type
        )
        app_logger.info(f"Query: {query}")

        record = query.first()
        app_logger.info("Query executed successfully")

        if record:
            ret_glycemic_index = record[0]
            app_logger.info("Record fetched")
            app_logger.info("Glycemic index fetched")

    app_logger.info("Connection closed")
    return ret_glycemic_index


def get_food_types_list(food_type: str = "") -> list[str]:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(GlycemicIndex.food_type).order_by(
            GlycemicIndex.food_type
        )
        app_logger.info(f"Query: {query}")

        records = query.all()
        app_logger.info("Query executed successfully")

        ret_records = [record[0] for record in records]
        if not food_type in records:
            ret_records.append(food_type)
        app_logger.info("Records fetched")

    app_logger.info("Connection closed")
    app_logger.info("Records fetched")
    return ",".join(ret_records)


def update_verfied(
    verfied: int, uuid: str = "", file_uid: str = "", food_type: str = ""
):
    if uuid == "":
        if file_uid == "" or food_type == "":
            error_message = "Either uid or file_uid and food_type must be provided"
            app_logger.error(error_message)
            raise Exception(error_message)

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(FoodRegister)
        if uuid != "":
            query = query.filter(FoodRegister.uuid == uuid)
        else:
            query = query.filter(
                FoodRegister.file_uid == file_uid, FoodRegister.food_type == food_type
            )
        app_logger.info(f"Query: {query}")

        query.update({FoodRegister.verified: verfied}, synchronize_session=False)
        app_logger.info("Record inserted successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")
