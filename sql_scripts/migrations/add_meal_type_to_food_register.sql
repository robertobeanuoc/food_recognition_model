-- Migration: classify existing food_register rows by meal_type.
--
-- Adds food_register.meal_type and backfills it by matching each row's
-- created_at against the habitual meal_schedule ranges, falling back to
-- 'other' for anything that doesn't fall inside a range.
--
-- Timezone note: food_register.created_at and meal_schedule.start_time /
-- end_time are both stored in the same UTC reference frame (see CLAUDE.md
-- "Timezones"), so this compares them directly (TIME(created_at) against
-- start_time/end_time, WEEKDAY(created_at) for the weekday/weekend split) —
-- no CONVERT_TZ or extra conversion needed, and none should be added here,
-- or the comparison would no longer be against the same reference frame.
--
-- Requires meal_type.sql and meal_schedule.sql to already be applied.
--
-- Not idempotent: running the ADD/backfill steps below undoes and redoes
-- the whole migration every time, rather than silently no-op'ing. That
-- means it errors if there's nothing to drop yet (e.g. a database that
-- never had this migration applied) — remove step 0 for that first run.

-- 0. Undo a previous run of this migration, if any, before redoing it.
--    The FK constraint must be dropped before the column it references,
--    or the DROP COLUMN fails.
ALTER TABLE food_register DROP FOREIGN KEY fk_food_register_meal_type;
ALTER TABLE food_register DROP COLUMN meal_type;

-- 1. Make sure the 'other' fallback meal_type exists. It is intentionally
--    not part of meal_schedule.
INSERT IGNORE INTO meal_type (meal_type) VALUES ('other');

-- 2. Add the column, nullable for now so the ALTER succeeds on a populated
--    table; tightened to NOT NULL once every row has been backfilled below.
ALTER TABLE food_register
    ADD COLUMN meal_type VARCHAR(20) NULL AFTER weight_grams;

-- 3. Backfill: match each row against the same-weekday-class range that
--    contains its time-of-day.
UPDATE food_register fr
JOIN meal_schedule ms
  ON ms.is_weekend = (WEEKDAY(fr.created_at) >= 5)
 AND TIME(fr.created_at) BETWEEN ms.start_time AND ms.end_time
SET fr.meal_type = ms.meal_type
WHERE fr.meal_type IS NULL;

-- 4. Anything left unmatched (outside every configured range) falls back to 'other'.
UPDATE food_register
SET meal_type = 'other'
WHERE meal_type IS NULL;

-- 5. Enforce the invariant going forward.
ALTER TABLE food_register
    MODIFY COLUMN meal_type VARCHAR(20) NOT NULL,
    ADD CONSTRAINT fk_food_register_meal_type FOREIGN KEY (meal_type) REFERENCES meal_type (meal_type);
