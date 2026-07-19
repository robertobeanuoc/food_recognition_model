# Food Recognition Model

A Flask web app that recognizes food from a photo. Upload a picture of a meal, and it:

1. Classifies each food item in the photo using OpenAI GPT-4o vision (food type, estimated weight, glycemic index, carbohydrate content).
2. Persists the results to MySQL.
3. Enriches each classification by matching it against a reference food-characteristics table, using GPT-4o again to find the closest known food.
4. Lets you review, correct, and browse your meal history over time.
5. Runs a background scheduler that watches your habitual meal times and, if a meal window passes without anything logged, sends a Slack reminder that lets you log the meal (with sensible default foods/quantities) directly from Slack.

## Table of contents

- [Architecture](#architecture)
- [Requirements](#requirements)
- [Running locally (no Docker)](#running-locally-no-docker)
- [Running with Docker Compose](#running-with-docker-compose)
- [Vault secrets](#vault-secrets)
- [Slack meal reminders](#slack-meal-reminders)
- [Database](#database)
- [Environment variables](#environment-variables)
- [Timezones](#timezones)
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
5. `similar_food.py:add_similar_food_info_to_food()` — for **each** food item, makes **two** GPT-4o calls: one to find the closest food in the `food_characteristics` reference table (via a Jinja2 prompt), and one to read the matched glycemic index back from the DB. This can be slow for photos with many food items.

### Persistence layer

Database access goes through SQLAlchemy (`db.py` + `db_models.py`): a module-level `Engine` with connection pooling, and short-lived, per-call `Session`s bound to the `FoodRegister`, `FoodCharacteristics`, `MealType`, `MealSchedule`, `MealDefaultItem` and `MealReminderLog` ORM models. `food_register.uuid`, `meal_schedule.uuid` and `meal_default_item.uuid`/`meal_reminder_log.uuid` are populated client-side by the ORM (a `default=` callable on each model's `uuid` column), not by the app relying on the database to generate them — MySQL doesn't support `RETURNING`, so a server/trigger-generated non-integer primary key can't be read back into the ORM's identity map after INSERT.

The schema is kept in sync with these models programmatically: `db.sync_schema()` runs once at app startup (`main.py`) and creates any table that's missing (via `Base.metadata.create_all()`), drops the legacy UUID `BEFORE INSERT` triggers if a database still has them from before uuid generation moved client-side, and seeds reference tables (`meal_type`, `meal_schedule`, `meal_default_item`) with default data if they're empty. It never alters or drops existing tables/columns — it's schema creation, not a migration tool.

### Slack meal-reminder flow

1. `reminder_scheduler.py:start_scheduler()` starts a background `APScheduler` job from `main.py` at startup (interval `REMINDER_CHECK_INTERVAL_MINUTES`, default 10 minutes), guarded against Flask's debug reloader starting it twice.
2. Each tick, `check_and_send_meal_reminders()` resolves "today"/weekday in `APP_TIMEZONE` (a background job has no request/cookie to read the browser timezone from), and for every `meal_schedule` window that has already ended today:
   - if `food_register` already has a row for that meal → nothing to do (covers meals logged normally via photo upload too);
   - if nothing was logged and no reminder has been sent yet → sends the initial Slack DM;
   - if a reminder was already sent and a *later* meal's window has since started while it's still unregistered → sends an escalation nudge ("you still haven't logged breakfast"), so a missed meal keeps surfacing instead of being silently dropped.
3. The reminder DM (`slack_bot.py`, built on Slack Bolt over **Socket Mode** — no public URL/webhook needed) has a "Registrar ahora" button. Clicking it opens a modal pre-filled with that meal's habitual foods/quantities (`db.py:get_next_default_preset()` — see `meal_default_item` below). Each food row is a searchable dropdown of the known foods, sorted by how often you've logged them for that meal type in the last 14 days (`db.py:get_food_types_ranked_by_usage()`), with an "Otro (nuevo alimento)" option to type a food not seen before. Add more rows, remove a pre-filled/added one you don't want, and submit with "Finalizar".
4. On submit, each food item is inserted the same way a photo upload would (`db.py:insert_food_type()`), sharing one synthetic `file_uid` so they show up together on `/view_photo/<file_uid>` for later editing.
5. `/meal_default_presets` — an admin page (same style as `/meal_schedule`/`/food_characteristics`) for editing which foods/quantities are habitual per meal type, per day of week, with support for more than one "preset" per meal/day (e.g. breakfast could rotate between milk+banana and eggs+toast) — see [Database](#database).

## Requirements

- Python 3.10+
- A MySQL 8 instance (not bundled — you point the app at one)
- An OpenAI API key with access to GPT-4o
- Optional but recommended: a HashiCorp Vault instance (KV v2 secrets engine) for storing DB/OpenAI/Slack credentials — see [Vault secrets](#vault-secrets). Without it, the app falls back to plain `DB_*`/`OPENAI_API_KEY` env vars and the Slack reminder bot simply stays disabled.
- Optional: a Slack app (Socket Mode enabled, bot token + app-level token) if you want meal reminders — see [Slack meal reminders](#slack-meal-reminders).

## Running locally (no Docker)

```bash
# From repo root
python -m pip install -r requirements.txt

export SECRET_KEY="your-secret"
export PHOTO_FOLDER="$PWD/photos"

# Option A: Vault (recommended — also required for the Slack reminder bot)
export VAULT_ADDR="https://vault.example.com"
export VAULT_TOKEN="s.xxxxxxxx"
# see "Vault secrets" below for what to put at these paths

# Option B: plain env vars (DB/OpenAI only — no Slack reminders without Vault)
export OPENAI_API_KEY="sk-..."
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

Configure credentials via Vault (`VAULT_ADDR`, `VAULT_TOKEN`) or the `DB_*`/`OPENAI_API_KEY` fallback env vars — the compose file does **not** spin up MySQL, Vault, or a Slack app, it points at existing instances. See `docker-compose.yml` for the full list of variables and volume mounts (uploads folder and `PHOTO_FOLDER`).

When `VAULT_ADDR` is set, the `web` container's entrypoint (`docker/wait-for-vault.py`) polls Vault's unauthenticated `/v1/sys/seal-status` endpoint every 5s and blocks startup until Vault reports `sealed: false`, before exec'ing the app. This matters because Vault typically runs in its own Compose project here (no `depends_on` across separate compose files), so nothing otherwise stops the app from starting — and reading its secrets — before Vault has been unsealed (e.g. right after a Vault restart). Skipped entirely when `VAULT_ADDR` isn't set.

## Vault secrets

DB, OpenAI, and Slack credentials are read from HashiCorp Vault (KV v2, static-token auth) via `src/food_recognition/vault_client.py`, one secret per path, each read once and cached. When `VAULT_ADDR`/`VAULT_TOKEN` aren't set, DB and OpenAI credentials fall back to plain env vars (`DB_*`, `OPENAI_API_KEY`) — Slack has no such fallback, since the reminder bot only makes sense with Vault configured.

Each Vault path's secret **is** a JSON object — a KV v2 secret's data is inherently a set of key/value fields, which is exactly what a JSON object is (it's what `vault kv get -format=json` or the UI's "JSON" view show you). So each secret is authored as a plain JSON file and uploaded whole with `vault kv put <path> @file.json`, which loads the file's top-level keys directly as the secret's fields — there is no extra wrapper field or nested JSON string, `vault_client.py:_read_kv_secret()` just returns `response["data"]["data"]` as-is. The KV v2 engine is assumed mounted at `secret/` unless `VAULT_MOUNT_POINT` says otherwise (e.g. `VAULT_MOUNT_POINT=kv`) — set it to match whatever your Vault admin actually named the mount, and adjust the `vault kv put`/CLI paths below the same way. Sample payloads live in [`vault/`](vault/) (`db.example.json`, `openai.example.json`, `slack.example.json`) — copy one, fill in real values, and upload it with `@<file>` (adjust the `secret/` mount prefix if your KV v2 engine is mounted elsewhere):

```bash
# VAULT_DB_SECRET_PATH (default: food_recognition/db)
cp vault/db.example.json db.json   # edit db.json with real values
vault kv put secret/food_recognition/db @db.json
rm db.json

# VAULT_OPENAI_SECRET_PATH (default: food_recognition/openai)
cp vault/openai.example.json openai.json   # edit openai.json with real values
vault kv put secret/food_recognition/openai @openai.json
rm openai.json

# VAULT_SLACK_SECRET_PATH (default: food_recognition/slack)
cp vault/slack.example.json slack.json   # edit slack.json with real values
vault kv put secret/food_recognition/slack @slack.json
rm slack.json
```

(`db.json`/`openai.json`/`slack.json` are gitignored — see [`vault/README.md`](vault/README.md) — so it's safe to stage them locally, just delete them after uploading.)

Each secret's JSON keys, exactly as `vault_client.py` reads them:

| Secret path | Keys | Notes |
|---|---|---|
| `food_recognition/db` | `host`, `port`, `user`, `password`, `name` | `port` is read as a string and coerced when building the SQLAlchemy URL; same values as `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` |
| `food_recognition/openai` | `api_key` | Same value as `OPENAI_API_KEY` |
| `food_recognition/slack` | `bot_token`, `app_token`, `user_id` | `bot_token` (`xoxb-…`, scope `chat:write`), `app_token` (`xapp-…`, scope `connections:write`, for Socket Mode), `user_id` is the Slack user ID reminders get DM'd to (not a username — find it via the profile's "Copy member ID") |

Requires a Slack app already created at [api.slack.com](https://api.slack.com/apps) with **Socket Mode** enabled and Interactivity turned on — this repo doesn't create or configure the Slack app itself, only talks to it.

## Slack meal reminders

See [Architecture → Slack meal-reminder flow](#slack-meal-reminder-flow) above for how it works, and [Vault secrets](#vault-secrets) for the credentials it needs. Two tunables:

- `APP_TIMEZONE` (default `UTC`) — the scheduler has no per-request cookie to read a browser timezone from, so it needs this to resolve "today"/weekday when comparing against `meal_schedule`.
- `REMINDER_CHECK_INTERVAL_MINUTES` (default `10`) — how often the background job checks for unregistered meals.

Habitual defaults (what gets pre-filled in the Slack form) are managed at `/meal_default_presets`.

## Database

### Schema

The schema is created automatically the first time the app connects — `db.sync_schema()` runs at startup and creates any table declared in `db_models.py` that doesn't exist yet, seeding `meal_type`, `meal_schedule`, and one starting `meal_default_item` preset (breakfast: milk + banana, every day). No manual step is required for a fresh database. The `sql_scripts/tables/*.sql` files are kept as human-readable documentation and a manual fallback:

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/food_characteristics.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_type.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_schedule.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_default_item.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_reminder_log.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/food_register.sql
```

Tables:

- **`food_register`** — one row per food item per photo (per served portion), or per food item logged manually from Slack. `file_uid` groups all rows belonging to the same photo (or the same Slack submission); `uuid` is the per-row primary key, generated client-side by the ORM. `meal_type` is a foreign key into `meal_type`, auto-classified from `meal_schedule` when the row is inserted (falling back to `'other'` if `created_at` isn't inside any configured range) unless passed explicitly (e.g. from the Slack modal), and editable afterwards from the photo review page.
- **`food_characteristics`** — reference table of per-food-type nutritional characteristics (formerly named `glycemic_index`): `food_type` (EN, primary key), `food_type_es` (ES), `glycemic_index`, `carbohydrate_percentage`, `absorption_type`. Whenever a photo is uploaded (or a meal logged from Slack) and the food type isn't already in this table, a row is added automatically (never overwriting an existing one) — see `db.py:_ensure_food_characteristics()`. Editable from the UI at `/food_characteristics`.
- **`meal_type`** — reference table of valid meal types (`breakfast` | `lunch` | `dinner` | `other`). `meal_type` itself is the primary key (a natural key, not a surrogate id), so other tables can reference it in a way that stays meaningful and intact across database migrations/restores. `other` is a fallback classification for `food_register` rows that don't match any `meal_schedule` range — it's intentionally not itself part of `meal_schedule`.
- **`meal_schedule`** — the habitual time range (`start_time`–`end_time`) for each `meal_type`, split by `is_weekend`. `uuid` is the per-row primary key (same client-side generation pattern as `food_register`); `meal_type` is a foreign key into the `meal_type` table; `UNIQUE(meal_type, is_weekend)` allows at most one range per combination. Seeded with reasonable default ranges if empty, editable from the UI at `/meal_schedule`. Used to auto-classify `food_register.meal_type` at insert time, and to drive the reminder scheduler.
- **`meal_default_item`** — habitual food items for a `(meal_type, day_of_week)`, grouped into ordered "presets" (`preset_order`) with items ordered within a preset by `item_order` — a preset is just the set of rows sharing `(meal_type, day_of_week, preset_order)`, there's no separate header row. Seeded with one default breakfast preset (milk + banana, all 7 days); lunch/dinner start empty. Editable from `/meal_default_presets`. Used by `db.py:get_next_default_preset()` to pick which preset to pre-fill in the Slack modal — if a meal's already been logged once this week, the next configured preset is proposed instead of repeating the same one.
- **`meal_reminder_log`** — one row per `(meal_type, meal_date)`, tracking Slack reminder state: when the first DM was sent, when it was last escalated (and at which later meal's window), and when it was resolved. `resolved_at` is a cache for observability only — the scheduler always re-derives resolution live from `food_register`. Managed entirely by the reminder scheduler/Slack bot, not user-editable.

Migrations (schema changes after initial creation) live in `sql_scripts/migrations/`:
- `add_meal_type_to_food_register.sql` adds `food_register.meal_type` to an existing database and backfills every existing row by matching its `created_at` against the current `meal_schedule` ranges (falling back to `'other'`).
- `rename_glycemic_index_to_food_characteristics.sql` renames the `glycemic_index` table to `food_characteristics` and adds the `carbohydrate_percentage`/`absorption_type` columns.

`meal_default_item` and `meal_reminder_log` are brand-new tables, so they need no migration script — `db.sync_schema()` creates them automatically on any existing database too.

### Backups

```bash
bash scripts/backup_mysql_databases.sh /path/to/backup/dir
```

Reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` from the environment (this script itself always uses the plain env vars, even if the app is configured to read them from Vault).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `changeme` | Flask session secret |
| `PHOTO_FOLDER` | — | Persistent storage path for uploaded images and their companion JSON files |
| `VAULT_ADDR` / `VAULT_TOKEN` | — | HashiCorp Vault address + static token. When unset, DB/OpenAI credentials fall back to the env vars below and the Slack bot is disabled — see [Vault secrets](#vault-secrets) |
| `VAULT_MOUNT_POINT` | `secret` | Name of the KV v2 secrets engine mount (e.g. `kv` if that's what your Vault admin named it) — set this if your engine isn't mounted at the default `secret/` |
| `VAULT_DB_SECRET_PATH` | `food_recognition/db` | Vault KV v2 path for DB credentials |
| `VAULT_OPENAI_SECRET_PATH` | `food_recognition/openai` | Vault KV v2 path for the OpenAI API key |
| `VAULT_SLACK_SECRET_PATH` | `food_recognition/slack` | Vault KV v2 path for Slack credentials |
| `OPENAI_API_KEY` | — | Fallback OpenAI key, used only when Vault isn't configured |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | see `docker-compose.yml` | Fallback MySQL connection, used only when Vault isn't configured |
| `APP_TIMEZONE` | `UTC` | Timezone the reminder scheduler uses to resolve "today"/weekday (no per-request cookie in a background job) |
| `REMINDER_CHECK_INTERVAL_MINUTES` | `10` | How often the reminder scheduler checks for unregistered meals |
| `WAIT_TIME_OPEANAI_API` | `5` | Seconds to sleep between OpenAI calls |
| `DEFAULT_DAYS` | `30` | Default look-back window for `/meals` |

## Timezones

`created_at`/`updated_at`, and `meal_schedule.start_time`/`end_time`, are always stored in the database as UTC (`db.py:_utcnow()` for full datetimes). The viewer's timezone is applied only at display time: an inline script in `base.html` reads the browser's IANA timezone (`Intl.DateTimeFormat().resolvedOptions().timeZone`) into a `tz` cookie on every page load, and `main.py:get_request_timezone()` reads that cookie (falling back to UTC if it isn't set yet, e.g. the very first request of a session, or holds an unrecognised value).

- Full datetimes: `main.py`'s `local_dt` Jinja filter converts a stored UTC datetime for display in `meals.html` / `view_photo.html`. The `/meals` date filter works in the other direction — the local calendar date picked in the UI is converted to a UTC boundary (local midnight → UTC) server-side before querying.
- Bare times (`meal_schedule.start_time`/`end_time`, no date component): `main.py:_utc_time_to_local()` / `_local_time_to_utc()` convert using today's date as an arbitrary reference for the UTC offset, used by `/meal_schedule` (display) and `/update_meal_schedule` (save). Because there's no real date attached to a recurring daily time, the resolved offset can shift by an hour right at a DST boundary — an accepted limitation of storing a timezone-converted bare time.
- The reminder scheduler is a background job, not a request, so it has no `tz` cookie to read — it uses the `APP_TIMEZONE` env var instead (default `UTC`), applying the same date-as-reference approximation described above (`reminder_scheduler.py:_meal_window_utc_datetime()`).

## Tests

Tests live in `src/test/` and require a live MySQL database. `test_similar.py` additionally requires a valid `OPENAI_API_KEY`. Run from `src/`:

```bash
cd src && python -m pytest test/
```

`test_db.py` exercises `insert_food_type` / `update_food_register` / `delete_food_register` against the real database but is non-destructive: `test/conftest.py` wraps each test in a single DB transaction (sessions are bound to a shared connection with `join_transaction_mode="create_savepoint"`, so each function's internal `session.commit()` only releases a SAVEPOINT) and rolls the whole thing back at teardown, so no row is ever actually persisted. A session-scoped fixture in the same `conftest.py` calls `db.sync_schema()` once before any test runs, so `meal_schedule`, `meal_default_item` and friends exist in the test database too — that part runs outside the rollback (MySQL `CREATE TABLE`/`TRIGGER` auto-commit and can't be wrapped in a transaction), but it's idempotent and safe to repeat.

`test_meal_schedule.py` is a read-only check that `get_meal_schedule()` returns all 6 `meal_type` × `is_weekend` combinations with sane (`start_time < end_time`) ranges.

`test_meal_default_presets.py` covers `meal_default_item` CRUD and the preset-rotation logic in `db.py:get_next_default_preset()`. `test_reminder_scheduler.py` drives `reminder_scheduler.check_and_send_meal_reminders()` with a controlled "now" and monkeypatches `slack_bot.send_reminder` (tests never hit real Slack), asserting the initial-reminder and next-meal-escalation timing.

## Project structure

```
src/
  main.py                              Entry point; all HTTP routes; starts the reminder scheduler + Slack bot thread
  food_recognition/
    food_classification.py             GPT-4o vision call; returns classified food list
    similar_food.py                    GPT-4o text call; maps a free-text food name to the food_characteristics table
    db.py                              SQLAlchemy engine/session setup, all DB queries, and sync_schema()
    db_models.py                       SQLAlchemy ORM models (FoodRegister, FoodCharacteristics, MealType, MealSchedule, MealDefaultItem, MealReminderLog)
    vault_client.py                    Vault (KV v2, static token) client: get_db_secrets()/get_openai_secrets()/get_slack_secrets()
    reminder_scheduler.py              APScheduler background job watching meal_schedule windows, triggers Slack reminders/escalations
    slack_bot.py                       Slack Bolt app (Socket Mode): reminder DMs, the log-meal modal, its dynamic add/remove-item/submit handlers
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
  wait-for-vault.py                    Entrypoint wrapper: blocks until Vault is unsealed (if VAULT_ADDR is set) before starting the app
docker-compose.yml
```

### Important path dependency

`main.py` and `constants.py` use relative paths (`food_recognition/static/uploads`, `food_recognition/jinja2_templates/similar_files.jinja`). The app **must be launched from `src/`**, otherwise these paths break.

## Known issues

- `similar_food.py` makes two OpenAI calls **per food item** on every `/view_photo` load; there is no caching.
- `update_food_register` in `main.py` is called with keyword argument `file_uid=` at one call site but the function signature uses `uuid=` — the two call sites use different parameter names; verify carefully when editing that function.
- Food items logged from Slack have no photo, so their `/view_photo/<file_uid>` page shows a broken image icon — a known, accepted gap.
- `slack_bot.py`'s Bolt `App` is created lazily on first use, not at import time, so importing the module (e.g. from tests) doesn't require Slack/Vault credentials to be configured; if they're missing at runtime, the bot thread logs an error and the rest of the app keeps working without Slack reminders.

## License

MIT — see [LICENSE](LICENSE).
