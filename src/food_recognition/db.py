import datetime
import pytz
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

from food_recognition import vault_client
from food_recognition.db_models import (
    Base,
    FoodCharacteristics,
    FoodRegister,
    MealDefaultItem,
    MealReminderLog,
    MealSchedule,
    MealType,
)
from food_recognition.utils import app_logger


def utcnow() -> datetime.datetime:
    """Current time as naive UTC, the format `created_at`/`updated_at` are stored in.

    The browser's local timezone is only applied at display time (see
    `local_dt` in main.py) — everything persisted to the database is UTC.
    """
    return datetime.datetime.now(tz=pytz.utc).replace(tzinfo=None)


def _build_db_url() -> str:
    secrets: dict = vault_client.get_db_secrets()
    user: str = secrets["user"]
    password: str = secrets["password"]
    host: str = secrets["host"]
    port: str = secrets["port"]
    name: str = secrets["name"]
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
    _seed_meal_default_items()
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


# Default habitual breakfast (preset_order=1, every day of the week) seeded
# once as a concrete starting example — lunch/dinner start with no presets
# configured, filled in later from the /meal_default_presets UI.
_DEFAULT_BREAKFAST_PRESET: list[tuple[str, int]] = [("milk", 200), ("banana", 120)]


def _seed_meal_default_items() -> None:
    with _SessionFactory() as session:
        if session.query(MealDefaultItem).filter(MealDefaultItem.meal_type == "breakfast").count() > 0:
            return
        now = utcnow()
        for day_of_week in range(7):
            for item_order, (food_type, weight_grams) in enumerate(_DEFAULT_BREAKFAST_PRESET, start=1):
                session.add(
                    MealDefaultItem(
                        meal_type="breakfast",
                        day_of_week=day_of_week,
                        preset_order=1,
                        item_order=item_order,
                        food_type=food_type,
                        weight_grams=weight_grams,
                        created_at=now,
                        updated_at=now,
                    )
                )
        session.commit()
        app_logger.info("Seeded meal_default_item with a default breakfast preset (milk + banana)")


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


def get_meal_schedule_start_time(meal_type: str, is_weekend: bool) -> datetime.time | None:
    """The habitual start_time (UTC time-of-day) for (meal_type, is_weekend), or
    None if meal_type isn't part of meal_schedule (e.g. OTHER_MEAL_TYPE, which
    is deliberately excluded — see _seed_meal_type()).

    Used to backdate food_register.created_at to when a meal habitually
    starts for manual-log flows (e.g. the Slack modal) that don't carry an
    actual eaten-at timestamp, instead of leaving it at the moment the row
    happened to be inserted.
    """
    with _SessionFactory() as session:
        record = (
            session.query(MealSchedule.start_time)
            .filter(MealSchedule.meal_type == meal_type, MealSchedule.is_weekend == is_weekend)
            .first()
        )
        return record[0] if record else None


def _classify_meal_type(created_at: datetime.datetime) -> str:
    """Classify a (naive UTC) created_at into a meal_type via get_meal_type_for_time()."""
    is_weekend: bool = created_at.weekday() >= 5  # Monday=0 .. Sunday=6
    return get_meal_type_for_time(time_of_day=created_at.time(), is_weekend=is_weekend)


def _ensure_food_characteristics(
    food_type: str,
    glycemic_index: int = None,
    carbohydrate_percentage: float = None,
    absorption_type: str = None,
) -> None:
    """Add food_type to food_characteristics if the LLM just classified a food
    that isn't in the reference table yet, so that knowledge accumulates over
    time instead of being lost. Never overwrites an existing row — those may
    have been curated by hand from the /food_characteristics UI.
    """
    with _SessionFactory() as session:
        exists = (
            session.query(FoodCharacteristics.food_type)
            .filter(FoodCharacteristics.food_type == food_type)
            .first()
        )
        if exists:
            return

        session.add(
            FoodCharacteristics(
                food_type=food_type,
                glycemic_index=glycemic_index,
                carbohydrate_percentage=carbohydrate_percentage,
                absorption_type=absorption_type,
            )
        )
        app_logger.info(f"Added '{food_type}' to food_characteristics")
        session.commit()


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

    _ensure_food_characteristics(
        food_type=food_type,
        glycemic_index=glycemic_index,
        carbohydrate_percentage=carbohydrate_percentage,
        absorption_type=absorption_type,
    )

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

        query = session.query(FoodCharacteristics)
        if food_type:
            query = query.filter(FoodCharacteristics.food_type == food_type)
        query = query.order_by(FoodCharacteristics.food_type)
        app_logger.info(f"Query: {query}")

        records = query.all()
        app_logger.info("Query executed successfully")

        records_json = [
            {
                "food_type": record.food_type,
                "food_type_es": record.food_type_es,
                "glycemic_index": record.glycemic_index,
                "carbohydrate_percentage": record.carbohydrate_percentage,
                "absorption_type": record.absorption_type,
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


def get_food_characteristics(food_type: str) -> dict | None:
    """Full food_characteristics row for `food_type` (glycemic_index/carbohydrate_percentage/
    absorption_type), or None if that food_type isn't in the reference table yet.

    Used by callers that insert a food_register row without going through the
    photo-classification flow (e.g. the Slack manual-log modal) so they can
    carry over the same nutritional fields the photo flow gets from GPT-4o,
    instead of only the glycemic_index (see get_glycemic_index()).
    """
    with _SessionFactory() as session:
        record = (
            session.query(FoodCharacteristics)
            .filter(FoodCharacteristics.food_type == food_type)
            .first()
        )
        if record is None:
            return None
        return {
            "glycemic_index": record.glycemic_index,
            "carbohydrate_percentage": record.carbohydrate_percentage,
            "absorption_type": record.absorption_type,
        }


def get_glycemic_index(food_type: str) -> int:
    ret_glycemic_index: int = 0

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(FoodCharacteristics.glycemic_index).filter(
            FoodCharacteristics.food_type == food_type
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


def get_food_types_ranked_by_usage(meal_type: str, days: int = 14) -> list[dict]:
    """food_characteristics catalog (food_type/food_type_es), ordered by how
    often each food_type was logged for `meal_type` in the last `days` days
    (most frequent first), then alphabetically for the rest of the catalog
    that hasn't been logged recently — used to order the Slack food-type
    picker so habitual choices for that meal surface first without hiding
    anything else.
    """
    cutoff = utcnow() - datetime.timedelta(days=days)
    with _SessionFactory() as session:
        usage_rows = (
            session.query(FoodRegister.food_type, func.count(FoodRegister.uuid).label("usage_count"))
            .filter(FoodRegister.meal_type == meal_type, FoodRegister.created_at >= cutoff)
            .group_by(FoodRegister.food_type)
            .order_by(text("usage_count DESC"), FoodRegister.food_type)
            .all()
        )
        ranked_food_types = [row[0] for row in usage_rows]

        catalog = {record.food_type: record.food_type_es for record in session.query(FoodCharacteristics).all()}

    ordered_food_types = [food_type for food_type in ranked_food_types if food_type in catalog]
    ordered_food_types += sorted(food_type for food_type in catalog if food_type not in ordered_food_types)

    return [{"food_type": ft, "food_type_es": catalog[ft]} for ft in ordered_food_types]


def get_food_types_list(food_type: str = "") -> list[str]:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(FoodCharacteristics.food_type).order_by(
            FoodCharacteristics.food_type
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


def update_food_characteristics(
    food_type: str,
    food_type_es: str = None,
    glycemic_index: int = None,
    carbohydrate_percentage: float = None,
    absorption_type: str = None,
) -> None:
    values: dict = {}
    if food_type_es != None and food_type_es != "":
        values["food_type_es"] = food_type_es
    if glycemic_index != None:
        values["glycemic_index"] = glycemic_index
    if carbohydrate_percentage != None:
        values["carbohydrate_percentage"] = carbohydrate_percentage
    if absorption_type != None and absorption_type != "":
        values["absorption_type"] = absorption_type

    if not values:
        return

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        session.query(FoodCharacteristics).filter(
            FoodCharacteristics.food_type == food_type
        ).update(values, synchronize_session=False)
        app_logger.info("Record updated successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


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


def get_meal_default_items() -> list[dict]:
    with _SessionFactory() as session:
        query = session.query(MealDefaultItem).order_by(
            MealDefaultItem.meal_type,
            MealDefaultItem.day_of_week,
            MealDefaultItem.preset_order,
            MealDefaultItem.item_order,
        )
        records = query.all()
        return [
            {
                "uuid": record.uuid,
                "meal_type": record.meal_type,
                "day_of_week": record.day_of_week,
                "preset_order": record.preset_order,
                "item_order": record.item_order,
                "food_type": record.food_type,
                "weight_grams": record.weight_grams,
            }
            for record in records
        ]


def add_meal_default_item(
    meal_type: str,
    day_of_week: int,
    preset_order: int,
    item_order: int,
    food_type: str,
    weight_grams: int = None,
) -> str:
    now = utcnow()
    with _SessionFactory() as session:
        item = MealDefaultItem(
            meal_type=meal_type,
            day_of_week=day_of_week,
            preset_order=preset_order,
            item_order=item_order,
            food_type=food_type,
            weight_grams=weight_grams,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        session.commit()
        return item.uuid


def update_meal_default_item(
    uuid: str, food_type: str = None, weight_grams: int = None
) -> None:
    values: dict = {"updated_at": utcnow()}
    if food_type != None and food_type != "":
        values["food_type"] = food_type
    if weight_grams != None:
        values["weight_grams"] = weight_grams

    with _SessionFactory() as session:
        session.query(MealDefaultItem).filter(MealDefaultItem.uuid == uuid).update(
            values, synchronize_session=False
        )
        session.commit()


def delete_meal_default_item(uuid: str) -> None:
    with _SessionFactory() as session:
        session.query(MealDefaultItem).filter(MealDefaultItem.uuid == uuid).delete(
            synchronize_session=False
        )
        session.commit()


def get_next_default_preset(meal_type: str, target_date: datetime.date) -> list[dict]:
    """Pick which habitual preset to suggest for `meal_type` on `target_date`.

    Presets for (meal_type, target_date.weekday()) are numbered by
    preset_order; the suggested one is presets[N % len(presets)], where N is
    how many distinct calendar days this week (Monday..target_date) already
    have a food_register row for meal_type — so once a meal's been logged
    once this week, the next reminder rotates to the next habitual option
    instead of repeating the same suggestion. Returns [] if no presets are
    configured for that meal_type/day.

    `target_date`/week boundaries are compared against food_register's
    naive-UTC created_at directly (same simplification already accepted
    elsewhere for date/time-of-day handling — see CLAUDE.md "Timezones").
    """
    day_of_week = target_date.weekday()
    week_start = target_date - datetime.timedelta(days=day_of_week)

    with _SessionFactory() as session:
        preset_orders = [
            row[0]
            for row in session.query(MealDefaultItem.preset_order)
            .filter(
                MealDefaultItem.meal_type == meal_type,
                MealDefaultItem.day_of_week == day_of_week,
            )
            .distinct()
            .order_by(MealDefaultItem.preset_order)
            .all()
        ]
        if not preset_orders:
            return []

        week_end_exclusive = datetime.datetime.combine(
            target_date + datetime.timedelta(days=1), datetime.time.min
        )
        logged_days: int = (
            session.query(func.date(FoodRegister.created_at))
            .filter(
                FoodRegister.meal_type == meal_type,
                FoodRegister.created_at >= datetime.datetime.combine(week_start, datetime.time.min),
                FoodRegister.created_at < week_end_exclusive,
            )
            .distinct()
            .count()
        )
        chosen_preset_order = preset_orders[logged_days % len(preset_orders)]

        items = (
            session.query(MealDefaultItem)
            .filter(
                MealDefaultItem.meal_type == meal_type,
                MealDefaultItem.day_of_week == day_of_week,
                MealDefaultItem.preset_order == chosen_preset_order,
            )
            .order_by(MealDefaultItem.item_order)
            .all()
        )
        return [{"food_type": item.food_type, "weight_grams": item.weight_grams} for item in items]


def has_food_register_for_meal(meal_type: str, meal_date: datetime.date) -> bool:
    day_start = datetime.datetime.combine(meal_date, datetime.time.min)
    day_end = datetime.datetime.combine(meal_date, datetime.time.max)
    with _SessionFactory() as session:
        exists = (
            session.query(FoodRegister.uuid)
            .filter(
                FoodRegister.meal_type == meal_type,
                FoodRegister.created_at >= day_start,
                FoodRegister.created_at <= day_end,
            )
            .first()
        )
        return exists is not None


def get_or_create_meal_reminder_log(meal_type: str, meal_date: datetime.date) -> dict:
    with _SessionFactory() as session:
        record = (
            session.query(MealReminderLog)
            .filter(MealReminderLog.meal_type == meal_type, MealReminderLog.meal_date == meal_date)
            .first()
        )
        if record is None:
            record = MealReminderLog(meal_type=meal_type, meal_date=meal_date)
            session.add(record)
            session.commit()
            session.refresh(record)
        return {
            "uuid": record.uuid,
            "meal_type": record.meal_type,
            "meal_date": record.meal_date,
            "notified_at": record.notified_at,
            "last_nudge_at": record.last_nudge_at,
            "last_nudge_meal_context": record.last_nudge_meal_context,
            "resolved_at": record.resolved_at,
        }


def mark_meal_reminder_notified(uuid: str, meal_type_context: str) -> None:
    with _SessionFactory() as session:
        session.query(MealReminderLog).filter(MealReminderLog.uuid == uuid).update(
            {"notified_at": utcnow(), "last_nudge_meal_context": meal_type_context},
            synchronize_session=False,
        )
        session.commit()


def mark_meal_reminder_nudged(uuid: str, meal_type_context: str) -> None:
    with _SessionFactory() as session:
        session.query(MealReminderLog).filter(MealReminderLog.uuid == uuid).update(
            {"last_nudge_at": utcnow(), "last_nudge_meal_context": meal_type_context},
            synchronize_session=False,
        )
        session.commit()


def mark_meal_reminder_resolved(meal_type: str, meal_date: datetime.date) -> None:
    with _SessionFactory() as session:
        session.query(MealReminderLog).filter(
            MealReminderLog.meal_type == meal_type,
            MealReminderLog.meal_date == meal_date,
            MealReminderLog.resolved_at.is_(None),
        ).update({"resolved_at": utcnow()}, synchronize_session=False)
        session.commit()
