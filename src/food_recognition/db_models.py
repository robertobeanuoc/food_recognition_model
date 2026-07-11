from sqlalchemy import (
    CHAR,
    DECIMAL,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class FoodRegister(Base):
    __tablename__ = "food_register"

    uuid = Column(CHAR(36), primary_key=True)
    file_uid = Column(String(100))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    food_type = Column(String(100))
    original_food_type = Column(String(100))
    glycemic_index = Column(Integer)
    original_glycemic_index = Column(Integer)
    weight_grams = Column(Integer)
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
