-- food_db.glycemic_index definition

CREATE TABLE `glycemic_index` (
  `food_type` varchar(50) DEFAULT NULL,
  `food_type_es` varchar(50) DEFAULT NULL,
  `glycemic_index` int DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
