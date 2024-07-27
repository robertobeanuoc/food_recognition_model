CREATE TABLE food_register_update
(   
    uuid CHAR(36) NOT NULL,
    food_register_uid CHAR(36) NOT NULL,
    file_uid nvarchar(100),
    created_at datetime,
    original_food_type nvarchar(100),
    food_type nvarchar(100),
    glycemic_index int,
    weight_grams int,
    PRIMARY KEY (uuid)
)

CREATE UNIQUE INDEX idx_food_register_update ON food_register_update (file_uid, original_food_type);


CREATE TRIGGER before_insert_food_register_update
BEFORE INSERT ON food_register_update
FOR EACH ROW
BEGIN
    SET NEW.uuid = UUID();
END;
