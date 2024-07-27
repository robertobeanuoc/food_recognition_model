
-- Update food_register table
ALTER TABLE food_register ADD COLUMN uuid CHAR(36) NOT NULL;

UPDATE food_register SET uuid = UUID();

ALTER TABLE food_register DROP PRIMARY KEY;


CREATE UNIQUE INDEX idx_file_food ON food_register (file_uid, food_type);

ALTER TABLE food_register ADD PRIMARY KEY (uuid);


CREATE TRIGGER before_insert_food_registers
BEFORE INSERT ON food_register
FOR EACH ROW
BEGIN
    SET NEW.uuid = UUID();
END;

-- Update food_register_update table

ALTER TABLE food_register_update ADD COLUMN uuid CHAR(36) NOT NULL;

UPDATE food_register_update SET uuid = UUID();

ALTER TABLE food_register_update DROP PRIMARY KEY;

ALTER TABLE food_register_update ADD PRIMARY KEY (uuid);

CREATE UNIQUE INDEX idx_food_register_update ON food_register_update (file_uid, original_food_type);

CREATE TRIGGER before_insert_food_register_update
BEFORE INSERT ON food_register_update
FOR EACH ROW
BEGIN
    SET NEW.uuid = UUID();
END;

