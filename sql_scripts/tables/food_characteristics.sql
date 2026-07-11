-- food_db.food_characteristics definition
--
-- Reference table of per-food-type nutritional characteristics (glycemic
-- index, carbohydrate percentage, absorption speed) — as opposed to
-- food_register, which holds one row per served portion. New food types
-- identified by the LLM are added here automatically on insert if missing
-- (db.py:_ensure_food_characteristics()); existing rows are only changed by
-- an explicit edit from the /food_characteristics UI. Formerly named
-- `glycemic_index`.

CREATE TABLE `food_characteristics` (
  `food_type` varchar(50) NOT NULL,
  `food_type_es` varchar(50) DEFAULT NULL,
  `glycemic_index` int DEFAULT NULL,
  `carbohydrate_percentage` decimal(5,2) DEFAULT NULL,
  `absorption_type` varchar(10) DEFAULT NULL,
  PRIMARY KEY (`food_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
