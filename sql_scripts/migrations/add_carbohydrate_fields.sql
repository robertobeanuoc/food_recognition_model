-- Migration: add carbohydrate and absorption fields to food_register
-- Run this script against existing databases to add the new columns.

ALTER TABLE food_register
    ADD COLUMN IF NOT EXISTS carbohydrate_percentage  DECIMAL(5,2) AFTER weight_grams,
    ADD COLUMN IF NOT EXISTS carbohydrate_weight_grams DECIMAL(8,2) AFTER carbohydrate_percentage,
    ADD COLUMN IF NOT EXISTS absorption_type           VARCHAR(10)  AFTER carbohydrate_weight_grams;
