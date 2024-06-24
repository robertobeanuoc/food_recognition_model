--mysql 
CREATE DATABASE IF NOT EXISTS food_db;
USE food_db;
CREATE TABLE food_register 
(
    created_at datetime,
    food_type nvarchar(100),
    glycemic_index int,
    weight_grams int,
    PRIMARY KEY (created_at, food_type, glycemic_index, weight_grams)
)

