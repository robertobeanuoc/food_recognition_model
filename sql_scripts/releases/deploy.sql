
-- Update food_register table
ALTER TABLE food_register ADD COLUMN uuid CHAR(36) NOT NULL;
ALTER TABLE food_register ADD COLUMN original_food_type nvarchar(100);
ALTER TABLE food_register ADD COLUMN original_glycemic_index int;
ALTER TABLE food_register ADD COLUMN updated_at datetime;

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
DROP TABLE IF EXISTS food_register_update;