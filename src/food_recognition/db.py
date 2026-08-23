import datetime
import pytz
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

import random

from food_recognition import vault_client
from food_recognition.db_models import (
    Base,
    ChatLinkRequest,
    FoodCharacteristics,
    FoodRegister,
    MealDefaultItem,
    MealReminderLog,
    MealSchedule,
    MealType,
    SlackInstallation,
    UserChatLink,
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
    alters or drops existing tables/columns, except for the one explicit,
    idempotent migration below.
    """
    Base.metadata.create_all(_engine)
    _drop_legacy_uuid_triggers()
    _migrate_add_owner_user_id_columns()
    _seed_meal_type()
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


def _migrate_unique_index(
    connection, table_name: str, old_index_name: str, new_index_name: str, new_index_columns: str
) -> None:
    """Swap a table's unique index for one that also covers owner_user_id.

    The new index is added *before* the old one is dropped because several
    of these tables have a FOREIGN KEY into meal_type.meal_type, and MySQL
    refuses to drop whichever index currently satisfies that constraint
    unless another one covering the same leading column already exists.
    Only touched if the old index is still there, checked via
    information_schema so this is safe to run on every startup.
    """
    old_index_exists = connection.execute(
        text(
            "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table_name AND INDEX_NAME = :index_name"
        ),
        {"table_name": table_name, "index_name": old_index_name},
    ).first()
    new_index_exists = connection.execute(
        text(
            "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table_name AND INDEX_NAME = :index_name"
        ),
        {"table_name": table_name, "index_name": new_index_name},
    ).first()
    if old_index_exists and not new_index_exists:
        connection.execute(text(f"ALTER TABLE {table_name} ADD UNIQUE INDEX {new_index_name} ({new_index_columns})"))
        connection.execute(text(f"ALTER TABLE {table_name} DROP INDEX {old_index_name}"))
        app_logger.info(f"Migrated {table_name}'s unique index to include owner_user_id")


def _migrate_add_owner_user_id_columns() -> None:
    """One-time, idempotent addition of `owner_user_id` to the four per-user
    tables (create_all() only creates whole tables that don't exist yet, it
    never alters existing ones — see sync_schema()).

    meal_reminder_log and meal_schedule also each need their uniqueness to
    grow by one column now that they're tracked per person, or two people's
    rows for the same (meal_type, meal_date) / (meal_type, is_weekend) would
    collide on one row. meal_default_item has no unique constraint to
    migrate, just the new column.
    """
    with _engine.begin() as connection:
        # MySQL (unlike MariaDB) has no `ADD COLUMN IF NOT EXISTS` — check
        # information_schema first instead.
        for table_name in ("food_register", "meal_reminder_log", "meal_schedule", "meal_default_item"):
            column_exists = connection.execute(
                text(
                    "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = :table_name AND COLUMN_NAME = 'owner_user_id'"
                ),
                {"table_name": table_name},
            ).first()
            if not column_exists:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN owner_user_id VARCHAR(255)"))
                app_logger.info(f"Added owner_user_id column to {table_name}")

        _migrate_unique_index(
            connection,
            table_name="meal_reminder_log",
            old_index_name="idx_meal_type_date",
            new_index_name="idx_meal_type_date_owner",
            new_index_columns="meal_type, meal_date, owner_user_id",
        )
        _migrate_unique_index(
            connection,
            table_name="meal_schedule",
            old_index_name="idx_meal_type_weekend",
            new_index_name="idx_meal_type_weekend_owner",
            new_index_columns="meal_type, is_weekend, owner_user_id",
        )


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


def _seed_meal_schedule(owner_user_id: str) -> None:
    """Give a person their own starting habitual meal-time ranges the first
    time their schedule is requested (see get_meal_schedule()) — each owner
    gets an independent copy of _DEFAULT_MEAL_SCHEDULE, not a shared one.
    """
    with _SessionFactory() as session:
        if session.query(MealSchedule).filter(MealSchedule.owner_user_id == owner_user_id).count() > 0:
            return
        for row in _DEFAULT_MEAL_SCHEDULE:
            session.add(MealSchedule(**row, owner_user_id=owner_user_id))
        session.commit()
        app_logger.info(f"Seeded meal_schedule with default habitual time ranges for {owner_user_id}")


# Default habitual breakfast (preset_order=1, every day of the week) seeded
# once as a concrete starting example — lunch/dinner start with no presets
# configured, filled in later from the /meal_default_presets UI.
_DEFAULT_BREAKFAST_PRESET: list[tuple[str, int]] = [("milk", 200), ("banana", 120)]


def _seed_meal_default_items(owner_user_id: str) -> None:
    """Give a person their own starting breakfast preset (milk + banana) the
    first time their presets are requested (see get_meal_default_items()) —
    lunch/dinner start with no presets configured, filled in later from the
    /meal_default_presets UI, same as before this was scoped per owner.
    """
    with _SessionFactory() as session:
        if (
            session.query(MealDefaultItem)
            .filter(MealDefaultItem.meal_type == "breakfast", MealDefaultItem.owner_user_id == owner_user_id)
            .count()
            > 0
        ):
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
                        owner_user_id=owner_user_id,
                    )
                )
        session.commit()
        app_logger.info(f"Seeded meal_default_item with a default breakfast preset (milk + banana) for {owner_user_id}")


def get_meal_type_for_time(time_of_day: datetime.time, is_weekend: bool, owner_user_id: str) -> str:
    """Look up the meal_type whose habitual meal_schedule range covers `time_of_day`
    for `owner_user_id` (each person has their own habitual ranges).

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
            MealSchedule.owner_user_id == owner_user_id,
        )
        app_logger.info(f"Query: {query}")

        record = query.first()
        app_logger.info("Query executed successfully")

    app_logger.info("Connection closed")
    return record[0] if record else OTHER_MEAL_TYPE


def get_meal_schedule_start_time(meal_type: str, is_weekend: bool, owner_user_id: str) -> datetime.time | None:
    """The habitual start_time (UTC time-of-day) for (meal_type, is_weekend, owner_user_id),
    or None if meal_type isn't part of that owner's meal_schedule (e.g.
    OTHER_MEAL_TYPE, which is deliberately excluded — see _seed_meal_type()).

    Used to backdate food_register.created_at to when a meal habitually
    starts for manual-log flows (e.g. the Slack modal) that don't carry an
    actual eaten-at timestamp, instead of leaving it at the moment the row
    happened to be inserted.
    """
    with _SessionFactory() as session:
        record = (
            session.query(MealSchedule.start_time)
            .filter(
                MealSchedule.meal_type == meal_type,
                MealSchedule.is_weekend == is_weekend,
                MealSchedule.owner_user_id == owner_user_id,
            )
            .first()
        )
        return record[0] if record else None


def _classify_meal_type(created_at: datetime.datetime, owner_user_id: str) -> str:
    """Classify a (naive UTC) created_at into a meal_type via get_meal_type_for_time().

    Seeds `owner_user_id`'s meal_schedule first (a no-op once it exists) so a
    person's very first upload — before they've ever visited /meal_schedule —
    still gets classified against their default ranges instead of falling
    back to OTHER_MEAL_TYPE for lack of any configured schedule.
    """
    _seed_meal_schedule(owner_user_id)
    is_weekend: bool = created_at.weekday() >= 5  # Monday=0 .. Sunday=6
    return get_meal_type_for_time(time_of_day=created_at.time(), is_weekend=is_weekend, owner_user_id=owner_user_id)


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
    owner_user_id: str,
    meal_type: str = None,
    carbohydrate_percentage: float = None,
    carbohydrate_weight_grams: float = None,
    absorption_type: str = None,
    created_at: datetime.datetime = None,
):
    if created_at is None:
        created_at = utcnow()
    if meal_type is None:
        meal_type = _classify_meal_type(created_at, owner_user_id)

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
            owner_user_id=owner_user_id,
        )
        session.add(food_register)
        app_logger.info("Record inserted successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


def update_food_register(
    uuid: str,
    owner_user_id: str,
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
        # food_type changed: the cached similar_food match now refers to the
        # old food, so drop it and let it be recomputed on the next view.
        values["similar_food"] = None
        values["similar_glycemic_index"] = None
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

        session.query(FoodRegister).filter(
            FoodRegister.uuid == uuid, FoodRegister.owner_user_id == owner_user_id
        ).update(values, synchronize_session=False)
        app_logger.info("Record inserted successfully")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


def delete_food_register(uuid: str, owner_user_id: str) -> None:
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        session.query(FoodRegister).filter(
            FoodRegister.uuid == uuid, FoodRegister.owner_user_id == owner_user_id
        ).delete(synchronize_session=False)
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
    owner_user_id: str,
    start_date: datetime.date | datetime.datetime = None,
    file_uid: str = None,
) -> list[dict]:
    """`created_at` is stored as naive UTC — pass `start_date` already in UTC
    (callers with a browser-local date should convert local midnight to UTC
    first, see main.py:meals())."""
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(FoodRegister).filter(FoodRegister.owner_user_id == owner_user_id)
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
                "similar_food": record.similar_food,
                "similar_glycemic_index": record.similar_glycemic_index,
            }
            for record in records
        ]
        app_logger.info("Records fetched")

    app_logger.info("Connection closed")
    app_logger.info("Records fetched")
    return records_json


def update_food_register_similar_food(
    uuid: str, similar_food: str, similar_glycemic_index: int
) -> None:
    """Persist the result of similar_food.py:find_similar_food() for one row,
    so subsequent /view_photo loads can reuse it instead of calling OpenAI
    again (see add_similar_food_info_to_food()).

    No owner_user_id filter: this always operates on a uuid already resolved
    from an owner-scoped get_food_registers() call (see main.py:view_photo()
    -> similar_food.py:add_similar_food_info_to_food()), so re-checking the
    owner here would be redundant.
    """
    with _SessionFactory() as session:
        session.query(FoodRegister).filter(FoodRegister.uuid == uuid).update(
            {"similar_food": similar_food, "similar_glycemic_index": similar_glycemic_index},
            synchronize_session=False,
        )
        session.commit()


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


def get_food_types_ranked_by_usage(meal_type: str, owner_user_id: str, days: int = 14) -> list[dict]:
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
            .filter(
                FoodRegister.meal_type == meal_type,
                FoodRegister.created_at >= cutoff,
                FoodRegister.owner_user_id == owner_user_id,
            )
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


def upsert_food_characteristics(
    food_type: str,
    food_type_es: str = None,
    glycemic_index: int = None,
    carbohydrate_percentage: float = None,
    absorption_type: str = None,
) -> None:
    """Upsert: updates the existing food_characteristics row for food_type
    with whichever fields are given, or inserts a new row if food_type isn't
    in the table yet (e.g. a food just classified by
    food_classification.py:classify_food_characteristics() for the Slack
    manual-log flow)."""
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

        exists = (
            session.query(FoodCharacteristics.food_type)
            .filter(FoodCharacteristics.food_type == food_type)
            .first()
        )
        if exists:
            session.query(FoodCharacteristics).filter(
                FoodCharacteristics.food_type == food_type
            ).update(values, synchronize_session=False)
            app_logger.info("Record updated successfully")
        else:
            session.add(FoodCharacteristics(food_type=food_type, **values))
            app_logger.info(f"Added '{food_type}' to food_characteristics")

        session.commit()
        app_logger.info("Changes committed")

    app_logger.info("Connection closed")


def update_verfied(
    verfied: int, owner_user_id: str, uuid: str = "", file_uid: str = "", food_type: str = ""
):
    if uuid == "":
        if file_uid == "" or food_type == "":
            error_message = "Either uid or file_uid and food_type must be provided"
            app_logger.error(error_message)
            raise Exception(error_message)

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = session.query(FoodRegister).filter(FoodRegister.owner_user_id == owner_user_id)
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
    owner_user_id: str,
    start_time: datetime.time,
    end_time: datetime.time,
    updated_at: datetime.datetime = None,
) -> None:
    if updated_at is None:
        updated_at = utcnow()

    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        session.query(MealSchedule).filter(
            MealSchedule.uuid == uuid, MealSchedule.owner_user_id == owner_user_id
        ).update(
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


def get_meal_schedule(owner_user_id: str) -> list[dict]:
    _seed_meal_schedule(owner_user_id)
    with _SessionFactory() as session:
        app_logger.info("Connected to the database")

        query = (
            session.query(MealSchedule)
            .filter(MealSchedule.owner_user_id == owner_user_id)
            .order_by(MealSchedule.meal_type, MealSchedule.is_weekend)
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


def get_meal_default_items(owner_user_id: str) -> list[dict]:
    _seed_meal_default_items(owner_user_id)
    with _SessionFactory() as session:
        query = (
            session.query(MealDefaultItem)
            .filter(MealDefaultItem.owner_user_id == owner_user_id)
            .order_by(
                MealDefaultItem.meal_type,
                MealDefaultItem.day_of_week,
                MealDefaultItem.preset_order,
                MealDefaultItem.item_order,
            )
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
    owner_user_id: str,
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
            owner_user_id=owner_user_id,
        )
        session.add(item)
        session.commit()
        return item.uuid


def update_meal_default_item(
    uuid: str, owner_user_id: str, food_type: str = None, weight_grams: int = None
) -> None:
    values: dict = {"updated_at": utcnow()}
    if food_type != None and food_type != "":
        values["food_type"] = food_type
    if weight_grams != None:
        values["weight_grams"] = weight_grams

    with _SessionFactory() as session:
        session.query(MealDefaultItem).filter(
            MealDefaultItem.uuid == uuid, MealDefaultItem.owner_user_id == owner_user_id
        ).update(values, synchronize_session=False)
        session.commit()


def delete_meal_default_item(uuid: str, owner_user_id: str) -> None:
    with _SessionFactory() as session:
        session.query(MealDefaultItem).filter(
            MealDefaultItem.uuid == uuid, MealDefaultItem.owner_user_id == owner_user_id
        ).delete(synchronize_session=False)
        session.commit()


def get_next_default_preset(meal_type: str, target_date: datetime.date, owner_user_id: str) -> list[dict]:
    """Pick which habitual preset to suggest for `meal_type` on `target_date`.

    Presets for (meal_type, target_date.weekday()) are numbered by
    preset_order; the suggested one is presets[N % len(presets)], where N is
    how many distinct calendar days this week (Monday..target_date) already
    have a food_register row for meal_type (for `owner_user_id`) — so once a
    meal's been logged once this week, the next reminder rotates to the next
    habitual option instead of repeating the same suggestion. Returns [] if
    no presets are configured for that meal_type/day. Presets (meal_default_item)
    are per-owner, same as the usage they're rotated against.

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
                MealDefaultItem.owner_user_id == owner_user_id,
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
                FoodRegister.owner_user_id == owner_user_id,
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
                MealDefaultItem.owner_user_id == owner_user_id,
            )
            .order_by(MealDefaultItem.item_order)
            .all()
        )
        return [{"food_type": item.food_type, "weight_grams": item.weight_grams} for item in items]


def has_food_register_for_meal(meal_type: str, meal_date: datetime.date, owner_user_id: str) -> bool:
    day_start = datetime.datetime.combine(meal_date, datetime.time.min)
    day_end = datetime.datetime.combine(meal_date, datetime.time.max)
    with _SessionFactory() as session:
        exists = (
            session.query(FoodRegister.uuid)
            .filter(
                FoodRegister.meal_type == meal_type,
                FoodRegister.created_at >= day_start,
                FoodRegister.created_at <= day_end,
                FoodRegister.owner_user_id == owner_user_id,
            )
            .first()
        )
        return exists is not None


def get_or_create_meal_reminder_log(meal_type: str, meal_date: datetime.date, owner_user_id: str) -> dict:
    with _SessionFactory() as session:
        record = (
            session.query(MealReminderLog)
            .filter(
                MealReminderLog.meal_type == meal_type,
                MealReminderLog.meal_date == meal_date,
                MealReminderLog.owner_user_id == owner_user_id,
            )
            .first()
        )
        if record is None:
            record = MealReminderLog(meal_type=meal_type, meal_date=meal_date, owner_user_id=owner_user_id)
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


def mark_meal_reminder_resolved(meal_type: str, meal_date: datetime.date, owner_user_id: str) -> None:
    with _SessionFactory() as session:
        session.query(MealReminderLog).filter(
            MealReminderLog.meal_type == meal_type,
            MealReminderLog.meal_date == meal_date,
            MealReminderLog.owner_user_id == owner_user_id,
            MealReminderLog.resolved_at.is_(None),
        ).update({"resolved_at": utcnow()}, synchronize_session=False)
        session.commit()


# ---------------------------------------------------------------------------
# Chat identity linking (Slack today, other providers later — see
# slack_bot.py's module docstring for the design this implements)
# ---------------------------------------------------------------------------

# Excludes 0/O/1/I/L — characters easy to misread when typing a code by hand
# into a chat client.
_LINK_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LINK_CODE_LENGTH = 8
_LINK_CODE_TTL_MINUTES = 10


def _generate_link_code() -> str:
    rng = random.SystemRandom()
    return "".join(rng.choice(_LINK_CODE_CHARS) for _ in range(_LINK_CODE_LENGTH))


def create_chat_link_code(owner_user_id: str, provider: str) -> dict:
    """Start (or restart) linking `owner_user_id`'s account on `provider`.

    Upserts the single pending-request row for this owner (see
    ChatLinkRequest's unique constraint) — regenerating a code simply
    replaces the previous one. Deliberately doesn't touch UserChatLink:
    an already-verified link keeps working until this new code is actually
    consumed (see verify_chat_link()), so requesting a code you never use
    can't break an existing link.
    """
    now = utcnow()
    expires_at = now + datetime.timedelta(minutes=_LINK_CODE_TTL_MINUTES)
    link_code = _generate_link_code()
    with _SessionFactory() as session:
        record = session.query(ChatLinkRequest).filter(ChatLinkRequest.owner_user_id == owner_user_id).first()
        if record is None:
            record = ChatLinkRequest(owner_user_id=owner_user_id, created_at=now)
            session.add(record)
        record.provider = provider
        record.link_code = link_code
        record.expires_at = expires_at
        session.commit()
    return {"link_code": link_code, "expires_at": expires_at}


def get_pending_chat_link_request(owner_user_id: str) -> dict | None:
    with _SessionFactory() as session:
        record = session.query(ChatLinkRequest).filter(ChatLinkRequest.owner_user_id == owner_user_id).first()
        if record is None:
            return None
        return {
            "provider": record.provider,
            "link_code": record.link_code,
            "expires_at": record.expires_at,
            "is_expired": record.expires_at <= utcnow(),
        }


def verify_chat_link(
    link_code: str, provider: str, provider_chat_id: str, provider_workspace_id: str | None
) -> str | None:
    """Consume a pending link code from a chat platform (e.g. the /food-link
    <code> Slack command). On success, upserts UserChatLink (creating the
    person's first link, or overwriting their previous one — "last one
    wins", the confirmed design) and returns the owner_user_id it belongs
    to. Returns None if the code doesn't exist, is for a different
    provider, or has expired (an expired row found here is deleted as a
    side effect — no separate cleanup job needed for something this cheap).
    """
    now = utcnow()
    with _SessionFactory() as session:
        request = (
            session.query(ChatLinkRequest)
            .filter(ChatLinkRequest.link_code == link_code, ChatLinkRequest.provider == provider)
            .first()
        )
        if request is None:
            return None
        if request.expires_at <= now:
            session.delete(request)
            session.commit()
            return None

        owner_user_id = request.owner_user_id
        link = session.query(UserChatLink).filter(UserChatLink.owner_user_id == owner_user_id).first()
        if link is None:
            link = UserChatLink(owner_user_id=owner_user_id, created_at=now)
            session.add(link)
        link.provider = provider
        link.provider_workspace_id = provider_workspace_id
        link.provider_chat_id = provider_chat_id
        link.verified_at = now
        link.updated_at = now
        session.delete(request)
        session.commit()
    return owner_user_id


def get_chat_link(owner_user_id: str) -> dict | None:
    with _SessionFactory() as session:
        record = session.query(UserChatLink).filter(UserChatLink.owner_user_id == owner_user_id).first()
        if record is None:
            return None
        return {
            "provider": record.provider,
            "provider_workspace_id": record.provider_workspace_id,
            "provider_chat_id": record.provider_chat_id,
            "verified_at": record.verified_at,
        }


def unlink_chat(owner_user_id: str) -> None:
    with _SessionFactory() as session:
        session.query(UserChatLink).filter(UserChatLink.owner_user_id == owner_user_id).delete(
            synchronize_session=False
        )
        session.commit()


def get_all_verified_chat_links(provider: str) -> list[dict]:
    """Every owner with a verified link on `provider` — what the reminder
    scheduler iterates over instead of running for one fixed owner."""
    with _SessionFactory() as session:
        records = session.query(UserChatLink).filter(UserChatLink.provider == provider).all()
        return [
            {
                "owner_user_id": record.owner_user_id,
                "provider_workspace_id": record.provider_workspace_id,
                "provider_chat_id": record.provider_chat_id,
            }
            for record in records
        ]


def get_owner_for_chat_identity(
    provider: str, provider_chat_id: str, provider_workspace_id: str | None
) -> str | None:
    """Resolve an incoming chat event (e.g. a Slack team_id/user_id pair)
    back to the Authentik owner_user_id it's linked to, or None if that
    chat identity hasn't linked an account yet."""
    with _SessionFactory() as session:
        query = session.query(UserChatLink.owner_user_id).filter(
            UserChatLink.provider == provider, UserChatLink.provider_chat_id == provider_chat_id
        )
        if provider_workspace_id is not None:
            query = query.filter(UserChatLink.provider_workspace_id == provider_workspace_id)
        record = query.first()
        return record[0] if record else None


def upsert_slack_installation(team_id: str, team_name: str, bot_token: str, installed_by: str) -> None:
    """Save (or update, e.g. after a re-install/token rotation) the
    bot_token Slack issued for one workspace's installation."""
    now = utcnow()
    with _SessionFactory() as session:
        record = session.query(SlackInstallation).filter(SlackInstallation.team_id == team_id).first()
        if record is None:
            record = SlackInstallation(team_id=team_id, installed_at=now)
            session.add(record)
        record.team_name = team_name
        record.bot_token = bot_token
        record.installed_by = installed_by
        session.commit()


def get_slack_installation(team_id: str) -> dict | None:
    with _SessionFactory() as session:
        record = session.query(SlackInstallation).filter(SlackInstallation.team_id == team_id).first()
        if record is None:
            return None
        return {"team_id": record.team_id, "team_name": record.team_name, "bot_token": record.bot_token}
