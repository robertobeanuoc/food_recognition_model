# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Flask web app that accepts a food photo, classifies it via OpenAI GPT-4o vision, persists results to MySQL, and enriches each classification by finding the closest matching food from a reference glycemic-index table (also via GPT-4o).

## Running locally (no Docker)

```bash
# From repo root
python -m pip install -r requirements.txt

export OPENAI_API_KEY="sk-..."
export SECRET_KEY="your-secret"
export PHOTO_FOLDER="$PWD/photos"
export DB_HOST=127.0.0.1 DB_PORT=3306 DB_USER=root DB_PASSWORD=... DB_NAME=food_recognition
mkdir -p photos src/food_recognition/static/uploads

# Must run from src/ — paths in the app are relative to that directory
cd src && python main.py
```

App is available at `https://localhost:5010` (Flask starts with `ssl_context='adhoc'`).

## Running with Docker Compose

```bash
docker compose up --build
```

Configure DB connection via env vars (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`). The compose file does **not** spin up MySQL — point it at an existing instance.

## Tests

Tests live in `src/test/` and require a live MySQL database and a valid `OPENAI_API_KEY`. Run from `src/`:

```bash
cd src && python -m pytest test/
```

`test/test_db.py` exercises `insert_food_type`/`update_food_register`/`delete_food_register` against the real database but is non-destructive: `test/conftest.py` wraps each test in one DB transaction (sessions are bound to a shared connection with `join_transaction_mode="create_savepoint"`, so each function's internal `session.commit()` only releases a SAVEPOINT) and rolls the whole thing back at teardown — no row is ever actually persisted.

## Initialising the database schema

The schema is created/synced automatically: `db.sync_schema()` runs once at app startup (called from `main.py`, right after the Flask app is built) and issues `Base.metadata.create_all()` against the models in `db_models.py`, so any table missing in the target database (e.g. a brand-new empty DB, or a new table like `meal_schedule` added later) gets created without a manual step. It also drops the legacy `BEFORE INSERT` UUID triggers if present (uuid PKs are now generated client-side by the ORM, see below) and seeds reference tables (`meal_type`, `meal_schedule`) with default data if they're empty.

This is **not** a migration tool — it only creates tables that don't exist yet; it never alters or drops existing tables/columns. The `sql_scripts/tables/*.sql` files are kept as human-readable schema documentation and a manual fallback:

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/glycemic_index.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_type.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_schedule.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/food_register.sql
```

An **existing** database (one that already had `food_register` before `meal_type` was added to it) needs the one-off migration instead, which adds the column and backfills existing rows:

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/migrations/add_meal_type_to_food_register.sql
```

## Database backup

```bash
bash scripts/backup_mysql_databases.sh /path/to/backup/dir
```

Reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` from the environment.

## Architecture

### Request flow

1. `POST /upload` → `main.py:upload()` — decodes image with OpenCV, saves as `<uuid>.jpg` under `static/uploads/`, calls `classify_image()`.
2. `food_classification.py:classify_image()` — base64-encodes the image and sends it to GPT-4o vision. Returns a JSON array: `[{food_type, glycemic_index, weight_grams}, ...]`.
3. Each item is inserted into `food_register` via `db.py:insert_food_type()`. The image and a companion `.json` file are copied to `PHOTO_FOLDER`.
4. Redirect to `GET /view_photo/<file_uid>` — fetches all rows for that `file_uid` and calls `add_similar_food_info_to_food()`.
5. `similar_food.py:add_similar_food_info_to_food()` — for **each** food item makes **two** GPT-4o calls: one to find the closest food in the `glycemic_index` reference table (via a Jinja2 prompt), and then reads the matched glycemic index from DB. This can be slow for photos with many food types.

### Key modules

| File | Role |
|---|---|
| `src/main.py` | Entry point; all HTTP routes |
| `src/food_recognition/food_classification.py` | GPT-4o vision call; returns classified food list |
| `src/food_recognition/similar_food.py` | GPT-4o text call; maps a free-text food name to the reference `glycemic_index` table |
| `src/food_recognition/db.py` | All MySQL queries via SQLAlchemy ORM (engine + pooled sessions, `mysql+mysqlconnector` dialect); also `sync_schema()`, the programmatic schema-sync entry point |
| `src/food_recognition/db_models.py` | SQLAlchemy declarative models (`FoodRegister`, `GlycemicIndex`, `MealType`, `MealSchedule`) mapping the existing tables |
| `src/food_recognition/utils.py` | Shared logger (`app_logger`) and `extract_json_from_openai()` parser |
| `src/food_recognition/constants.py` | `SIMILAR_JINJA2_TEMPLATE` path and `WAIT_TIME_OPEANAI_API` |

### Database tables

- **`food_register`** — one row per food type per image. `file_uid` groups all rows for the same photo; `uuid` is the per-row PK, generated client-side by the ORM (`default=` on `FoodRegister.uuid` in `db_models.py`). `meal_type` is a foreign key into `meal_type`, auto-classified at insert time from `meal_schedule` (`db.py:_classify_meal_type()`/`get_meal_type_for_time()`) — falls back to `'other'` if `created_at` doesn't fall inside any configured range. Editable afterwards from `/view_photo/<file_uid>` like any other field.
- **`glycemic_index`** — reference table: `food_type` (EN), `food_type_es` (ES), `glycemic_index`.
- **`meal_type`** — reference table of valid meal types (`breakfast` | `lunch` | `dinner` | `other`, English canonical values). `meal_type` (the string itself) is the primary key, so other tables reference it by natural key rather than by a surrogate id — that relationship stays meaningful and intact across migrations/restores, independent of any auto-increment id. `'other'` is the fallback for `food_register` rows outside every `meal_schedule` range — it's deliberately excluded from `meal_schedule` itself (`db.py:_seed_meal_type()`).
- **`meal_schedule`** — the habitual time range (`start_time`–`end_time`) for each `meal_type`, split by `is_weekend`. `uuid` is the per-row PK (same client-side generation pattern as `food_register`); `meal_type` is a foreign key into `meal_type`; `UNIQUE(meal_type, is_weekend)` allows at most one range per combination (6 rows total). Seeded with default ranges by `db.sync_schema()` if empty. Editable from the UI at `/meal_schedule`. Used to auto-classify `food_register.meal_type` at insert time — see `db.py:get_meal_type_for_time()`.

### Important path dependency

`main.py` and `constants.py` use relative paths (`food_recognition/static/uploads`, `food_recognition/jinja2_templates/similar_files.jinja`). The app **must be launched from `src/`**; otherwise these paths break.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for all GPT-4o calls |
| `SECRET_KEY` | `changeme` | Flask session secret |
| `PHOTO_FOLDER` | — | Persistent storage path for images/JSON |
| `DB_HOST/PORT/USER/PASSWORD/NAME` | see compose | MySQL connection |
| `WAIT_TIME_OPEANAI_API` | `5` | Seconds to sleep between OpenAI calls |
| `DEFAULT_DAYS` | `30` | Default look-back window for `/meals` |

### Timezones

`created_at`/`updated_at` are always stored as naive UTC (`db.py:_utcnow()`; `FoodRegister`/`MealSchedule` rows are never written with a server-local or configurable timezone). `meal_schedule.start_time`/`end_time` are also stored as UTC time-of-day. Display-time conversion to the viewer's timezone happens per-request: an inline script in `base.html` reads `Intl.DateTimeFormat().resolvedOptions().timeZone` and stores it in a `tz` cookie (takes effect from the *next* request — the very first page load of a session may briefly render in UTC). `main.py:get_request_timezone()` reads that cookie (falling back to UTC if missing/invalid).

- Full datetimes (`created_at`): the `local_dt` Jinja filter converts a stored UTC datetime for display — used in `meals.html` and `view_photo.html`. The `/meals` date-picker filter goes the other direction: the browser-local calendar date the user picks is turned into UTC (local midnight → UTC) in `main.py:meals()` before querying.
- Bare times (`meal_schedule.start_time`/`end_time`, no date component): `main.py:_utc_time_to_local()`/`_local_time_to_utc()` convert using *today's* date as an arbitrary reference to resolve the UTC offset — used by the `/meal_schedule` route (display) and `/update_meal_schedule` (save). Because there's no real date tied to a recurring daily time, the resolved offset — and thus the displayed/stored value — can shift by an hour right at a DST boundary; this is an accepted limitation, not a bug.

### Known issues / watch-outs

- `similar_food.py` makes two OpenAI calls **per food item** on every `/view_photo` load; there is no caching.
- `update_food_register` in `main.py` is called with keyword argument `file_uid=` but the function signature uses `uuid=` — the two call sites use different parameter names; verify carefully when editing that function.
