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
    carbohydrate_percentage DECIMAL(5,2),
    carbohydrate_weight_grams DECIMAL(8,2),
    absorption_type VARCHAR(10),
    verified BOOLEAN,
    PRIMARY KEY (uuid)
);

CREATE UNIQUE INDEX idx_file_food ON food_register (file_uid, food_type);

DROP TRIGGER IF EXISTS before_insert_food_registers;

CREATE TRIGGER before_insert_food_registers
BEFORE INSERT ON food_register
FOR EACH ROW
SET NEW.uuid = COALESCE(NULLIF(NEW.uuid, ''), UUID());

