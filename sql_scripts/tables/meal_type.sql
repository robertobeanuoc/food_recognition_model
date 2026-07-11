-- Reference table of valid meal types (English canonical values).
-- meal_schedule.meal_type is a foreign key into this natural key, not into a
-- surrogate id, so the relationship stays meaningful across migrations/restores.
CREATE TABLE IF NOT EXISTS meal_type (
    meal_type VARCHAR(20) NOT NULL,
    PRIMARY KEY (meal_type)
);
