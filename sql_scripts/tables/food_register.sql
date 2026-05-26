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
    verified BOOLEAN,
    PRIMARY KEY (uuid)
);

CREATE UNIQUE INDEX idx_file_food ON food_register (file_uid, food_type);

DELIMITER //
CREATE TRIGGER before_insert_food_registers
BEFORE INSERT ON food_register
FOR EACH ROW
BEGIN
    IF NEW.uuid IS NULL OR NEW.uuid = '' THEN
        SET NEW.uuid = UUID();
    END IF;
END
//
DELIMITER ;

