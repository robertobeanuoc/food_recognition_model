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

## Initialising the database schema

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/glycemic_index.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/food_register.sql
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
| `src/food_recognition/db.py` | All MySQL queries (no ORM; raw `mysql-connector-python`) |
| `src/food_recognition/utils.py` | Shared logger (`app_logger`) and `extract_json_from_openai()` parser |
| `src/food_recognition/constants.py` | `SIMILAR_JINJA2_TEMPLATE` path and `WAIT_TIME_OPEANAI_API` |

### Database tables

- **`food_register`** — one row per food type per image. `file_uid` groups all rows for the same photo; `uuid` is the per-row PK (set by a `BEFORE INSERT` trigger).
- **`glycemic_index`** — reference table: `food_type` (EN), `food_type_es` (ES), `glycemic_index`.

### Important path dependency

`main.py` and `constants.py` use relative paths (`food_recognition/static/uploads`, `food_recognition/jinja2_templates/similar_files.jinja`). The app **must be launched from `src/`**; otherwise these paths break.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for all GPT-4o calls |
| `SECRET_KEY` | `changeme` | Flask session secret |
| `PHOTO_FOLDER` | — | Persistent storage path for images/JSON |
| `DB_HOST/PORT/USER/PASSWORD/NAME` | see compose | MySQL connection |
| `DB_TZ_DATES` | `UTC` | Timezone for `created_at` conversion |
| `WAIT_TIME_OPEANAI_API` | `5` | Seconds to sleep between OpenAI calls |
| `DEFAULT_DAYS` | `30` | Default look-back window for `/meals` |

### Known issues / watch-outs

- `db.py` builds SQL with f-strings throughout — no parameterized queries. Any new DB code should use `%s` placeholders with `cursor.execute(query, params)`.
- `similar_food.py` makes two OpenAI calls **per food item** on every `/view_photo` load; there is no caching.
- `update_food_register` in `main.py` is called with keyword argument `file_uid=` but the function signature uses `uuid=` — the two call sites use different parameter names; verify carefully when editing that function.
