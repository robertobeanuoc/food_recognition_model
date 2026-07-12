-- Tracks Slack reminder state for one (meal_type, meal_date): when the first
-- reminder DM was sent, when it was last escalated ("you still haven't
-- logged breakfast") at a later meal's window, and when it was resolved.
-- resolved_at is a cache for observability only — the scheduler always
-- re-derives resolution live from food_register, never trusts this flag as
-- source of truth (see reminder_scheduler.py:check_and_send_meal_reminders()).
-- Kept as a manual-init fallback — in normal operation this table is created
-- automatically by db.sync_schema() when the app starts. Requires
-- meal_type.sql to run first.
CREATE TABLE IF NOT EXISTS meal_reminder_log (
    uuid CHAR(36) NOT NULL,
    meal_type VARCHAR(20) NOT NULL,
    meal_date DATE NOT NULL,
    notified_at DATETIME,
    last_nudge_at DATETIME,
    last_nudge_meal_context VARCHAR(20),
    resolved_at DATETIME,
    PRIMARY KEY (uuid),
    FOREIGN KEY (meal_type) REFERENCES meal_type (meal_type)
);

CREATE UNIQUE INDEX idx_meal_type_date ON meal_reminder_log (meal_type, meal_date);
