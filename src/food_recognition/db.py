import datetime
import os
import pytz
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from food_recognition.db_models import Base, FoodRegister, GlycemicIndex, MealSchedule, MealType
from food_recognition.utils import app_logger


def utcnow() -> datetime.datetime:
    """Current time as naive UTC, the format `created_at`/`updated_at` are stored in.

    The browser's local timezone is only applied at display time (see
    `local_dt` in main.py) — everything persisted to the database is UTC.
    """
    return datetime.datetime.now(tz=pytz.utc).replace(tzinfo=None)


def _build_db_url() -> str:
    user: str = os.getenv("DB_USER")
    password: str = os.getenv("DB_PASSWORD")
    host: str = os.getenv("DB_HOST")
    port: str = os.getenv("DB_PORT")
    name: str = os.getenv("DB_NAME")
    return f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{name}"


_engine = create_engine(_build_db_url(), pool_pre_ping=True)
_SessionFactory = sessionmaker(bind=_engine)

# Fallback meal_type for food_register rows whose created_at doesn't fall
# inside any configured meal_schedule range. Deliberately not part of
# meal_schedule (see _seed_meal_type / _classify_meal_type below).
OTHER_MEAL_TYPE: str = "other"

_DEFAULT_MEAL_SCHEDULE: list[dict] = [
    {"meal_type": "breakfast", "is_weekend": False, "start_time": datetime.time(7, 0), "end_time": datetime.time(10, 0)},
    {"meal_type": "breakfast", "is_weekend": True, "start_time": datetime.time(8, 0), "end_time": datetime.time(11, 0)},
    {"meal_type": "lunch", "is_weekend": False, "start_time": datetime.time(13, 0), "end_time": datetime.time(15, 30)},
    {"meal_type": "lunch", "is_weekend": True, "start_time": datetime.time(13, 30), "end_time": datetime.time(16, 30)},
    {"meal_type": "dinner", "is_weekend": False, "start_time": datetime.time(20, 0), "end_time": datetime.time(22, 30)},
    {"meal_type": "dinner", "is_weekend": True, "start_time": datetime.time(20, 30), "end_time": datetime.time(23, 30)},
]


def sync_schema() -> None:
    """Create any tables present in the ORM models but missing in the database.

    Called once when the app starts (see main.py) so the schema is kept in
    sync with db_models.py programmatically, instead of requiring a manual
    `mysql ... < sql_scripts/tables/*.sql` step. This only creates missing
    tables (SQLAlchemy's create_all is not a migration tool) — it never
    alters or drops existing tables/columns.
    """
    Base.metadata.create_all(_engine)
    _drop_legacy_uuid_triggers()
    _seed_meal_type()
    _seed_meal_schedule()
    app_logger.info("Database schema synced")


def _drop_legacy_uuid_triggers() -> None:
    # uuid primary keys are now generated client-side (see the `default=` on
    # FoodRegister.uuid / MealSchedule.uuid in db_models.py), so these
    # BEFORE INSERT triggers are no longer needed. This drops them from
    # databases provisioned before that change; it's a no-op once they're
    # gone. Safe to keep calling indefinitely — DROP TRIGGER IF EXISTS.
    with _engine.begin() as connection:
        connection.execute(text("DROP TRIGGER IF EXISTS before_insert_food_registers"))
        connection.execute(text("DROP TRIGGER IF EXISTS before_insert_meal_schedule"))


def _seed_meal_type() -> None:
    with _SessionFactory() as session:
        if session.query(MealType).count() == 0:
            for meal_type in ("breakfast", "lunch", "dinner"):
                session.add(MealType(meal_type=meal_type))
            session.commit()
            app_logger.info("Seeded meal_type with default values")

        # Ensured unconditionally (not just on first seed) so it also shows
        # up in databases that already had meal_type populated before this
        # was introduced. Intentionally not added to meal_schedule.
        if session.query(MealType).filter(MealType.meal_type == OTHER_MEAL_TYPE).count() == 0:
            session.add(MealType(meal_type=OTHER_MEAL_TYPE))
            session.commit()
            app_logger.info(f"Added '{OTHER_MEAL_TYPE}' fallback meal_type")


def _seed_meal_schedule() -> None:
    with _SessionFactory() as session:
        if session.query(MealSchedule).count() > 0:
            return
        for row in _DEFAULT_MEAL_SCHEDULE:
            session.add(MealSchedule(**row))
        session.commit()
        app_logger.info("Seeded meal_schedule with default habitual time ranges")


def get_meal_type_for_time(time_of_day: datetime.time, is_weekend: bool) -> str:
    """Look up the meal_type whose habitual meal_schedule range covers `time_of_day`.

    `time_of_day` must already be in the same reference frame as
    meal_schedule.start_time/end_time — both are stored as UTC time-of-day
    (see CLAUDE.md "Timezones"), so callers must pass the UTC time-of-day of
    the record being classified, not a browser-local-converted one, or the
    match will be off by the viewer's UTC offset. Falls back to
    OTHER_MEAL_TYPE if no configured range covers it.
    """
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(MealSchedule.meal_type).filter(
            MealSchedule.is_weekend == is_weekend,
            MealSchedule.start_time <= time_of_day,
            MealSchedule.end_time >= time_of_day,
        )
        app_logger.info(f"Query: {query}")

        record = query.first()
        app_logger.info("Query executed successfully")

    app_logger.info("Connection closed")
    return record[0] if record else OTHER_MEAL_TYPE


def _classify_meal_type(created_at: datetime.datetime) -> str:
    """Classify a (naive UTC) created_at into a meal_type via get_meal_type_for_time()."""
    is_weekend: bool = created_at.weekday() >= 5  # Monday=0 .. Sunday=6
    return get_meal_type_for_time(time_of_day=created_at.time(), is_weekend=is_weekend)


def insert_food_type(
    file_uid: str,
    food_type: str,
    glycemic_index: int,
    weight_grams: int,
    meal_type: str = None,
    carbohydrate_percentage: float = None,
    carbohydrate_weight_grams: float = None,
    absorption_type: str = None,
    created_at: datetime.datetime = None,
):
    if created_at is None:
        created_at = utcnow()
    if meal_type is None:
        meal_type = _classify_meal_type(created_at)

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        food_register: FoodRegister = FoodRegister(
            file_uid=file_uid,
            food_type=food_type,
            original_food_type=food_type,
            glycemic_index=glycemic_index,
            original_glycemic_index=glycemic_index,
            weight_grams=weight_grams,
            meal_type=meal_type,
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
    meal_type: str = None,
    updated_at: datetime.datetime = None,
):
    if updated_at is None:
        updated_at = utcnow()

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
    if meal_type != None and meal_type != "":
        values["meal_type"] = meal_type

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
    start_date: datetime.date | datetime.datetime = None, file_uid: str = None
) -> list[dict]:
    """`created_at` is stored as naive UTC — pass `start_date` already in UTC
    (callers with a browser-local date should convert local midnight to UTC
    first, see main.py:meals())."""
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(FoodRegister)
        if file_uid:
            query = query.filter(FoodRegister.file_uid == file_uid)
        if start_date:
            query = query.filter(FoodRegister.created_at >= start_date)
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
                "meal_type": record.meal_type,
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


def update_meal_schedule(
    uuid: str,
    start_time: datetime.time,
    end_time: datetime.time,
    updated_at: datetime.datetime = None,
) -> None:
    if updated_at is None:
        updated_at = utcnow()

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        session.query(MealSchedule).filter(MealSchedule.uuid == uuid).update(
            {
                "start_time": start_time,
                "end_time": end_time,
                "updated_at": updated_at,
            },
            synchronize_session=False,
        )
        app_logger.info("Record updated successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


def get_meal_schedule() -> list[dict]:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(MealSchedule).order_by(
            MealSchedule.meal_type, MealSchedule.is_weekend
        )
        app_logger.info(f"Query: {query}")

        records = query.all()
        app_logger.info("Query executed successfully")

        records_json = [
            {
                "uuid": record.uuid,
                "meal_type": record.meal_type,
                "is_weekend": record.is_weekend,
                "start_time": record.start_time,
                "end_time": record.end_time,
            }
            for record in records
        ]
        app_logger.info("Records fetched")

    app_logger.info("Connection closed")
    return records_json


# Canonical display order for the meal_type dropdown — chronological, with
# the 'other' fallback last. Anything present in the DB but not listed here
# (shouldn't normally happen) is appended alphabetically at the end.
_MEAL_TYPE_ORDER: dict[str, int] = {"breakfast": 0, "lunch": 1, "dinner": 2, OTHER_MEAL_TYPE: 3}


def get_meal_types() -> list[str]:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(MealType.meal_type)
        app_logger.info(f"Query: {query}")

        records = query.all()
        app_logger.info("Query executed successfully")

        meal_types = [record[0] for record in records]

    app_logger.info("Connection closed")
    return sorted(meal_types, key=lambda m: (_MEAL_TYPE_ORDER.get(m, len(_MEAL_TYPE_ORDER)), m))
