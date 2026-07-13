-- Adds the similar_food/similar_glycemic_index cache columns to an existing
-- food_register table. Nullable, no backfill: existing rows are simply
-- recomputed (once) and persisted the next time they're viewed via
-- /view_photo — see similar_food.py:add_similar_food_info_to_food().
ALTER TABLE food_register
    ADD COLUMN similar_food VARCHAR(100) NULL,
    ADD COLUMN similar_glycemic_index INT NULL;
