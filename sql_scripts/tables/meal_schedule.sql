-- Reference table for the habitual time range of each meal (breakfast/lunch/dinner),
-- split by weekday vs. weekend. Not used by the app to auto-classify food_register
-- rows yet; this is only the schema. Kept as a manual-init fallback — in normal
-- operation this table is created and seeded automatically by db.sync_schema()
-- when the app starts (see main.py). Requires meal_type.sql to run first.
CREATE TABLE IF NOT EXISTS meal_schedule (
    uuid CHAR(36) NOT NULL,
    meal_type VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (uuid),
    FOREIGN KEY (meal_type) REFERENCES meal_type (meal_type)
);

CREATE UNIQUE INDEX idx_meal_type_weekend ON meal_schedule (meal_type, is_weekend);
