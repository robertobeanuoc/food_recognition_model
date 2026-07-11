-- Requires meal_type.sql to run first (meal_type FK below).
CREATE TABLE IF NOT EXISTS food_register (
    uuid CHAR(36) NOT NULL,
    file_uid VARCHAR(100),
    created_at DATETIME,
    updated_at DATETIME,
    food_type VARCHAR(100),
    original_food_type VARCHAR(100),
    glycemic_index INT,
    original_glycemic_index INT,
    weight_grams INT,
    -- Auto-classified from meal_schedule at insert time, 'other' if no
    -- range matches. See sql_scripts/migrations/add_meal_type_to_food_register.sql
    -- for backfilling an existing table.
    meal_type VARCHAR(20) NOT NULL,
    carbohydrate_percentage DECIMAL(5,2),
    carbohydrate_weight_grams DECIMAL(8,2),
    absorption_type VARCHAR(10),
    verified BOOLEAN,
    PRIMARY KEY (uuid),
    FOREIGN KEY (meal_type) REFERENCES meal_type (meal_type)
);

CREATE UNIQUE INDEX idx_file_food ON food_register (file_uid, food_type);

