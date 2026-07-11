# Food Recognition Model

A Flask web app that recognizes food from a photo. Upload a picture of a meal, and it:

1. Classifies each food item in the photo using OpenAI GPT-4o vision (food type, estimated weight, glycemic index, carbohydrate content).
2. Persists the results to MySQL.
3. Enriches each classification by matching it against a reference glycemic-index table, using GPT-4o again to find the closest known food.
4. Lets you review, correct, and browse your meal history over time.

## Table of contents

- [Architecture](#architecture)
- [Requirements](#requirements)
- [Running locally (no Docker)](#running-locally-no-docker)
- [Running with Docker Compose](#running-with-docker-compose)
- [Database](#database)
- [Environment variables](#environment-variables)
- [Tests](#tests)
- [Project structure](#project-structure)
- [Known issues](#known-issues)
- [License](#license)

## Architecture

### Request flow

1. `POST /upload` → `main.py:upload()` — decodes the uploaded image with OpenCV, saves it as `<uuid>.jpg` under `static/uploads/`, and calls `classify_image()`.
2. `food_classification.py:classify_image()` — base64-encodes the image and sends it to GPT-4o vision. Returns a JSON array: `[{food_type, glycemic_index, weight_grams}, ...]`.
3. Each item is inserted into `food_register` via `db.py:insert_food_type()`. The image and a companion `.json` file are copied to `PHOTO_FOLDER`.
4. The request redirects to `GET /view_photo/<file_uid>`, which fetches all rows for that `file_uid` and calls `add_similar_food_info_to_food()`.
5. `similar_food.py:add_similar_food_info_to_food()` — for **each** food item, makes **two** GPT-4o calls: one to find the closest food in the `glycemic_index` reference table (via a Jinja2 prompt), and one to read the matched glycemic index back from the DB. This can be slow for photos with many food items.

### Persistence layer

Database access goes through SQLAlchemy (`db.py` + `db_models.py`): a module-level `Engine` with connection pooling, and short-lived, per-call `Session`s bound to the `FoodRegister`, `GlycemicIndex`, `MealType` and `MealSchedule` ORM models. `food_register.uuid` and `meal_schedule.uuid` are populated client-side by the ORM (a `default=` callable on each model's `uuid` column), not by the app relying on the database to generate them — MySQL doesn't support `RETURNING`, so a server/trigger-generated non-integer primary key can't be read back into the ORM's identity map after INSERT.

The schema is kept in sync with these models programmatically: `db.sync_schema()` runs once at app startup (`main.py`) and creates any table that's missing (via `Base.metadata.create_all()`), drops the legacy UUID `BEFORE INSERT` triggers if a database still has them from before uuid generation moved client-side, and seeds reference tables (`meal_type`, `meal_schedule`) with default data if they're empty. It never alters or drops existing tables/columns — it's schema creation, not a migration tool.

## Requirements

- Python 3.10+
- A MySQL 8 instance (not bundled — you point the app at one)
- An OpenAI API key with access to GPT-4o

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

The app is available at `https://localhost:5010` (Flask starts with `ssl_context='adhoc'`, so the browser will warn about a self-signed certificate).

## Running with Docker Compose

```bash
docker compose up --build
```

Configure the DB connection via env vars (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`) — the compose file does **not** spin up MySQL, it points at an existing instance. See `docker-compose.yml` for the full list of variables and volume mounts (uploads folder and `PHOTO_FOLDER`).

## Database

### Schema

The schema is created automatically the first time the app connects — `db.sync_schema()` runs at startup and creates any table declared in `db_models.py` that doesn't exist yet. No manual step is required for a fresh database. The `sql_scripts/tables/*.sql` files are kept as human-readable documentation and a manual fallback:

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/glycemic_index.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_type.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_schedule.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/food_register.sql
```

Tables:

- **`food_register`** — one row per food item per photo. `file_uid` groups all rows belonging to the same photo; `uuid` is the per-row primary key, generated client-side by the ORM. `meal_type` is a foreign key into `meal_type`, auto-classified from `meal_schedule` when the row is inserted (falling back to `'other'` if `created_at` isn't inside any configured range) and editable afterwards from the photo review page.
- **`glycemic_index`** — reference table used to look up a standard glycemic index for a free-text food name: `food_type` (EN), `food_type_es` (ES), `glycemic_index`.
- **`meal_type`** — reference table of valid meal types (`breakfast` | `lunch` | `dinner` | `other`). `meal_type` itself is the primary key (a natural key, not a surrogate id), so other tables can reference it in a way that stays meaningful and intact across database migrations/restores. `other` is a fallback classification for `food_register` rows that don't match any `meal_schedule` range — it's intentionally not itself part of `meal_schedule`.
- **`meal_schedule`** — the habitual time range (`start_time`–`end_time`) for each `meal_type`, split by `is_weekend`. `uuid` is the per-row primary key (same client-side generation pattern as `food_register`); `meal_type` is a foreign key into the `meal_type` table; `UNIQUE(meal_type, is_weekend)` allows at most one range per combination. Seeded with reasonable default ranges if empty, editable from the UI at `/meal_schedule`. Used to auto-classify `food_register.meal_type` at insert time.

Migrations (schema changes after initial creation) live in `sql_scripts/migrations/`. `add_meal_type_to_food_register.sql` adds `food_register.meal_type` to an existing database and backfills every existing row by matching its `created_at` against the current `meal_schedule` ranges (falling back to `'other'`).

### Backups

```bash
bash scripts/backup_mysql_databases.sh /path/to/backup/dir
```

Reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` from the environment.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for all GPT-4o calls |
| `SECRET_KEY` | `changeme` | Flask session secret |
| `PHOTO_FOLDER` | — | Persistent storage path for uploaded images and their companion JSON files |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | see `docker-compose.yml` | MySQL connection |
| `WAIT_TIME_OPEANAI_API` | `5` | Seconds to sleep between OpenAI calls |
| `DEFAULT_DAYS` | `30` | Default look-back window for `/meals` |

## Timezones

`created_at`/`updated_at`, and `meal_schedule.start_time`/`end_time`, are always stored in the database as UTC (`db.py:_utcnow()` for full datetimes). The viewer's timezone is applied only at display time: an inline script in `base.html` reads the browser's IANA timezone (`Intl.DateTimeFormat().resolvedOptions().timeZone`) into a `tz` cookie on every page load, and `main.py:get_request_timezone()` reads that cookie (falling back to UTC if it isn't set yet, e.g. the very first request of a session, or holds an unrecognised value).

- Full datetimes: `main.py`'s `local_dt` Jinja filter converts a stored UTC datetime for display in `meals.html` / `view_photo.html`. The `/meals` date filter works in the other direction — the local calendar date picked in the UI is converted to a UTC boundary (local midnight → UTC) server-side before querying.
- Bare times (`meal_schedule.start_time`/`end_time`, no date component): `main.py:_utc_time_to_local()` / `_local_time_to_utc()` convert using today's date as an arbitrary reference for the UTC offset, used by `/meal_schedule` (display) and `/update_meal_schedule` (save). Because there's no real date attached to a recurring daily time, the resolved offset can shift by an hour right at a DST boundary — an accepted limitation of storing a timezone-converted bare time.

## Tests

Tests live in `src/test/` and require a live MySQL database. `test_similar.py` additionally requires a valid `OPENAI_API_KEY`. Run from `src/`:

```bash
cd src && python -m pytest test/
```

`test_db.py` exercises `insert_food_type` / `update_food_register` / `delete_food_register` against the real database but is non-destructive: `test/conftest.py` wraps each test in a single DB transaction (sessions are bound to a shared connection with `join_transaction_mode="create_savepoint"`, so each function's internal `session.commit()` only releases a SAVEPOINT) and rolls the whole thing back at teardown, so no row is ever actually persisted. A session-scoped fixture in the same `conftest.py` calls `db.sync_schema()` once before any test runs, so `meal_schedule` and friends exist in the test database too — that part runs outside the rollback (MySQL `CREATE TABLE`/`TRIGGER` auto-commit and can't be wrapped in a transaction), but it's idempotent and safe to repeat.

`test_meal_schedule.py` is a read-only check that `get_meal_schedule()` returns all 6 `meal_type` × `is_weekend` combinations with sane (`start_time < end_time`) ranges.

## Project structure

```
src/
  main.py                              Entry point; all HTTP routes
  food_recognition/
    food_classification.py             GPT-4o vision call; returns classified food list
    similar_food.py                    GPT-4o text call; maps a free-text food name to the glycemic_index table
    db.py                              SQLAlchemy engine/session setup, all DB queries, and sync_schema()
    db_models.py                       SQLAlchemy ORM models (FoodRegister, GlycemicIndex, MealType, MealSchedule)
    validate_parameters.py             Route input validation (UUIDs, food type strings)
    utils.py                           Shared logger and extract_json_from_openai() parser
    constants.py                       Jinja2 template path and OpenAI wait time constant
    templates/                         Flask/Jinja2 HTML templates
    jinja2_templates/                  Prompt templates sent to OpenAI
    static/uploads/                    Scratch folder for the image currently being processed
  test/                                Pytest test suite
sql_scripts/
  tables/                              CREATE TABLE scripts
  migrations/                          Schema changes applied after initial creation
  releases/                            Deployment scripts
  views/                               Reporting SQL views
scripts/
  backup_mysql_databases.sh            MySQL backup helper
docker/
  Dockerfile
docker-compose.yml
```

### Important path dependency

`main.py` and `constants.py` use relative paths (`food_recognition/static/uploads`, `food_recognition/jinja2_templates/similar_files.jinja`). The app **must be launched from `src/`**, otherwise these paths break.

## Known issues

- `similar_food.py` makes two OpenAI calls **per food item** on every `/view_photo` load; there is no caching.
- `update_food_register` in `main.py` is called with keyword argument `file_uid=` at one call site but the function signature uses `uuid=` — the two call sites use different parameter names; verify carefully when editing that function.

## License

MIT — see [LICENSE](LICENSE).
