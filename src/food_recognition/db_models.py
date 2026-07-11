import uuid as uuid_lib

from sqlalchemy import (
    CHAR,
    DECIMAL,
    Boolean,
    Column,
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


class GlycemicIndex(Base):
    __tablename__ = "glycemic_index"

    # The table has no real primary key in MySQL; food_type is marked as
    # primary_key here only so SQLAlchemy's ORM can map the class. This
    # table is read-only from the app, so no insert/update/delete relies
    # on it being an actual unique key.
    food_type = Column(String(50), primary_key=True)
    food_type_es = Column(String(50))
    glycemic_index = Column(Integer)


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
        UniqueConstraint("meal_type", "is_weekend", name="idx_meal_type_weekend"),
    )

    # Client-side default, same pattern and reasoning as FoodRegister.uuid.
    uuid = Column(CHAR(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    meal_type = Column(String(20), ForeignKey("meal_type.meal_type"), nullable=False)
    is_weekend = Column(Boolean, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
