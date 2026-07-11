-- Migration: rename glycemic_index to food_characteristics and extend it
-- with the carbohydrate_percentage / absorption_type columns that
-- food_register already tracks per portion, so the same characteristics
-- are also kept at the food-type level and reused across portions.
--
-- Not idempotent: run once against a database that still has `glycemic_index`.

RENAME TABLE glycemic_index TO food_characteristics;

ALTER TABLE food_characteristics
    ADD COLUMN carbohydrate_percentage DECIMAL(5,2) AFTER glycemic_index,
    ADD COLUMN absorption_type VARCHAR(10) AFTER carbohydrate_percentage;

-- The old table had no real primary key, so duplicate food_type rows may
-- exist. If the next statement fails with a duplicate-key error, find and
-- remove the duplicates first, e.g.:
--   SELECT food_type, COUNT(*) FROM food_characteristics GROUP BY food_type HAVING COUNT(*) > 1;
ALTER TABLE food_characteristics
    ADD PRIMARY KEY (food_type);
