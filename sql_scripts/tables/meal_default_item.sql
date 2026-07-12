-- Habitual food items for a given meal_type/day_of_week, grouped into ordered
-- "presets" (preset_order) with no separate header row/table — a preset is
-- simply the set of rows sharing (meal_type, day_of_week, preset_order).
-- Used by the Slack reminder bot to pre-fill the log-meal form; if the first
-- preset was already logged this week, the next one is proposed instead (see
-- db.py:get_next_default_preset()). Kept as a manual-init fallback — in
-- normal operation this table is created (and seeded with a default
-- breakfast preset) automatically by db.sync_schema() when the app starts.
-- Requires meal_type.sql to run first.
CREATE TABLE IF NOT EXISTS meal_default_item (
    uuid CHAR(36) NOT NULL,
    meal_type VARCHAR(20) NOT NULL,
    day_of_week INT NOT NULL, -- 0=Monday .. 6=Sunday (Python date.weekday())
    preset_order INT NOT NULL, -- 1, 2, 3... rotation order within meal_type/day_of_week
    item_order INT NOT NULL, -- display order of food items within one preset
    food_type VARCHAR(100) NOT NULL,
    weight_grams INT,
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (uuid),
    FOREIGN KEY (meal_type) REFERENCES meal_type (meal_type)
);
