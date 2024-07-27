CREATE TABLE food_register 
(
        
    uuid CHAR(36) NOT NULL
    file_uid nvarchar(100),
    created_at datetime,
    food_type nvarchar(100),
    glycemic_index int,
    weight_grams int,
    verified boolean,
    PRIMARY KEY (uuid)
)

CREATE UNIQUE INDEX idx_file_food ON food_register (file_uid, food_type);



CREATE TRIGGER before_insert_food_registers
BEFORE INSERT ON food_register
FOR EACH ROW
BEGIN
    SET NEW.uuid = UUID();
END;

