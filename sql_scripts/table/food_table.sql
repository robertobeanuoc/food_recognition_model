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

-- food_db.glycemic_index definition

CREATE TABLE `glycemic_index` (
  `food_type` varchar(50) DEFAULT NULL,
  `food_type_es` varchar(50) DEFAULT NULL,
  `glycemic_index` int DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE food_register_update
(
    file_uid nvarchar(100),
    created_at datetime,
    food_type nvarchar(100),
    glycemic_index int,
    weight_grams int,
    PRIMARY KEY (file_uid,food_type )
)
