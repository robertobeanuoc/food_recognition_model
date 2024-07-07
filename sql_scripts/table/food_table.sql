--mysql 
CREATE DATABASE IF NOT EXISTS food_db;
USE food_db;
CREATE TABLE food_register 
(
    file_uid nvarchar(100),
    created_at datetime,
    food_type nvarchar(100),
    glycemic_index int,
    weight_grams int,
    verified boolean,
    PRIMARY KEY (file_uid,food_type )
)

