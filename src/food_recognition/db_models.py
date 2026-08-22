import uuid as uuid_lib

from sqlalchemy import (
    CHAR,
    DECIMAL,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class FoodRegister(Base):
    __tablename__ = "food_register"

    # Client-side default so the ORM has a primary key value to put in its
    # identity map right after flush. Without it, SQLAlchemy has no way to
    # learn a server-generated uuid back (MySQL doesn't support RETURNING and
    # this isn't an autoincrement column), so it would raise
    # `FlushError: Instance <...> has a NULL identity key` on every insert.
    uuid = Column(CHAR(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    file_uid = Column(String(100))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    food_type = Column(String(100))
    original_food_type = Column(String(100))
    glycemic_index = Column(Integer)
    original_glycemic_index = Column(Integer)
    weight_grams = Column(Integer)
    # Auto-classified from meal_schedule at insert time (falls back to
    # 'other' if the timestamp doesn't fall in any configured range) — see
    # db.py:_classify_meal_type(). Editable afterwards like any other field.
    meal_type = Column(String(20), ForeignKey("meal_type.meal_type"), nullable=False)
    carbohydrate_percentage = Column(DECIMAL(5, 2))
    carbohydrate_weight_grams = Column(DECIMAL(8, 2))
    absorption_type = Column(String(10))
    verified = Column(Boolean)
    # Cached result of similar_food.py:find_similar_food() — the closest
    # food_characteristics match for food_type, and its glycemic_index.
    # Computed and persisted the first time this row is viewed (see
    # similar_food.py:add_similar_food_info_to_food()) so /view_photo
    # doesn't re-call OpenAI on every subsequent load. NULL means not
    # computed yet, not "no match found".
    similar_food = Column(String(100))
    similar_glycemic_index = Column(Integer)
    # Authentik user `sub` this row belongs to. Nullable at the schema level
    # only because ADD COLUMN can't backfill existing rows for free (see
    # db.py:_migrate_add_owner_user_id_columns()) — the application always
    # supplies it. scripts/backfill_owner_user_id.py fills in pre-existing
    # rows once.
    owner_user_id = Column(String(255), nullable=True)


class FoodCharacteristics(Base):
    __tablename__ = "food_characteristics"

    # Reference table of per-food-type nutritional characteristics (as
    # opposed to food_register, which holds one row per served portion).
    # food_type is the natural primary key. New rows are added automatically
    # by db.py:_ensure_food_characteristics() whenever the LLM classifies a
    # food_type not already present; existing rows are never overwritten by
    # that path, only by an explicit edit from the /food_characteristics UI.
    food_type = Column(String(50), primary_key=True)
    food_type_es = Column(String(50))
    glycemic_index = Column(Integer)
    carbohydrate_percentage = Column(DECIMAL(5, 2))
    absorption_type = Column(String(10))


class MealType(Base):
    __tablename__ = "meal_type"

    # Reference table of valid meal types (English canonical values:
    # breakfast/lunch/dinner). meal_schedule.meal_type is a foreign key into
    # this natural key, so the relationship stays meaningful and intact
    # across database migrations/restores, independent of any surrogate id.
    meal_type = Column(String(20), primary_key=True)


class MealSchedule(Base):
    __tablename__ = "meal_schedule"
    __table_args__ = (
        # owner_user_id is part of the uniqueness (not just meal_type/
        # is_weekend) now that each person has their own habitual meal
        # times — see db.py:_migrate_add_owner_user_id_columns() for how an
        # existing 2-column index gets migrated to this 3-column one.
        UniqueConstraint("meal_type", "is_weekend", "owner_user_id", name="idx_meal_type_weekend_owner"),
    )

    # Client-side default, same pattern and reasoning as FoodRegister.uuid.
    uuid = Column(CHAR(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    meal_type = Column(String(20), ForeignKey("meal_type.meal_type"), nullable=False)
    is_weekend = Column(Boolean, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    # Same meaning/caveats as FoodRegister.owner_user_id above — each person
    # has their own habitual meal-time ranges, seeded on first use (see
    # db.py:get_meal_schedule()).
    owner_user_id = Column(String(255), nullable=True)


class MealDefaultItem(Base):
    __tablename__ = "meal_default_item"

    # A "preset" is not a separate row/table — it's just the group of items
    # sharing (meal_type, day_of_week, preset_order). Rotation logic (see
    # db.py:get_next_default_preset()) picks one preset_order per reminder
    # based on how many times that meal_type was already logged this week.
    uuid = Column(CHAR(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    meal_type = Column(String(20), ForeignKey("meal_type.meal_type"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday..6=Sunday (date.weekday())
    preset_order = Column(Integer, nullable=False)  # 1, 2, 3... rotation order
    item_order = Column(Integer, nullable=False)  # display order within one preset
    food_type = Column(String(100), nullable=False)
    weight_grams = Column(Integer)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    # Same meaning/caveats as FoodRegister.owner_user_id above — each person
    # eats different default items, seeded on first use (see
    # db.py:get_meal_default_items()).
    owner_user_id = Column(String(255), nullable=True)


class MealReminderLog(Base):
    __tablename__ = "meal_reminder_log"
    __table_args__ = (
        # owner_user_id is part of the uniqueness (not just meal_type/
        # meal_date) so two different people's reminder state for the same
        # meal/day don't collide on one row — see
        # db.py:_migrate_add_owner_user_id_columns() for how an existing
        # 2-column index gets migrated to this 3-column one.
        UniqueConstraint("meal_type", "meal_date", "owner_user_id", name="idx_meal_type_date_owner"),
    )

    # Tracks Slack reminder state for one (meal_type, meal_date, owner_user_id).
    # resolved_at is a cache for observability only — the scheduler always
    # re-derives resolution live from food_register, never trusts this flag
    # as source of truth (see reminder_scheduler.py:check_and_send_meal_reminders()).
    uuid = Column(CHAR(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    meal_type = Column(String(20), ForeignKey("meal_type.meal_type"), nullable=False)
    meal_date = Column(Date, nullable=False)
    notified_at = Column(DateTime)
    last_nudge_at = Column(DateTime)
    last_nudge_meal_context = Column(String(20))
    resolved_at = Column(DateTime)
    # Same meaning/caveats as FoodRegister.owner_user_id above.
    owner_user_id = Column(String(255), nullable=True)
