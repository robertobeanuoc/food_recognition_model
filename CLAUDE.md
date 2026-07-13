# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Flask web app that accepts a food photo, classifies it via OpenAI GPT-4o vision, persists results to MySQL, and enriches each classification by finding the closest matching food from a reference food-characteristics table (also via GPT-4o). It also runs an in-process background scheduler that watches habitual meal times (`meal_schedule`) and, if a meal window passes unregistered, DMs a Slack bot reminder that lets the user log the meal directly from Slack.

## Running locally (no Docker)

```bash
# From repo root
python -m pip install -r requirements.txt

export SECRET_KEY="your-secret"
export PHOTO_FOLDER="$PWD/photos"
# DB + OpenAI + Slack credentials — see "Vault secrets" below. Without
# VAULT_ADDR/VAULT_TOKEN set, DB and OpenAI credentials fall back to the plain
# env vars below (handy for local dev):
export OPENAI_API_KEY="sk-..."
export DB_HOST=127.0.0.1 DB_PORT=3306 DB_USER=root DB_PASSWORD=... DB_NAME=food_recognition
# Slack has no such fallback — omit VAULT_ADDR/VAULT_TOKEN entirely to run
# without the reminder bot (it fails to start, logs a warning, and the rest
# of the app works normally).
mkdir -p photos src/food_recognition/static/uploads

# Must run from src/ — paths in the app are relative to that directory
cd src && python main.py
```

App is available at `https://localhost:5010` (Flask starts with `ssl_context='adhoc'`).

## Running with Docker Compose

```bash
docker compose up --build
```

Configure DB, OpenAI, and Slack bot credentials via Vault (`VAULT_ADDR`, `VAULT_TOKEN`, see "Vault secrets" below), or via the `DB_*`/`OPENAI_API_KEY` env vars as a fallback (DB/OpenAI only — no Slack reminders without Vault). The compose file does **not** spin up MySQL, Vault, or a Slack app — point it at existing instances.

## Tests

Tests live in `src/test/` and require a live MySQL database and a valid `OPENAI_API_KEY`. Run from `src/`:

```bash
cd src && python -m pytest test/
```

`test/test_db.py` exercises `insert_food_type`/`update_food_register`/`delete_food_register` against the real database but is non-destructive: `test/conftest.py` wraps each test in one DB transaction (sessions are bound to a shared connection with `join_transaction_mode="create_savepoint"`, so each function's internal `session.commit()` only releases a SAVEPOINT) and rolls the whole thing back at teardown — no row is ever actually persisted.

`test_reminder_scheduler.py` monkeypatches `slack_bot.send_reminder` (tests never hit real Slack) and drives `reminder_scheduler.check_and_send_meal_reminders()` against the real (transactional-rollback) test DB.

## Initialising the database schema

The schema is created/synced automatically: `db.sync_schema()` runs once at app startup (called from `main.py`, right after the Flask app is built) and issues `Base.metadata.create_all()` against the models in `db_models.py`, so any table missing in the target database (e.g. a brand-new empty DB, or a new table like `meal_schedule`, `meal_default_item` or `meal_reminder_log` added later) gets created without a manual step. It also drops the legacy `BEFORE INSERT` UUID triggers if present (uuid PKs are now generated client-side by the ORM, see below) and seeds reference tables (`meal_type`, `meal_schedule`, `meal_default_item`) with default data if they're empty.

This is **not** a migration tool — it only creates tables that don't exist yet; it never alters or drops existing tables/columns. The `sql_scripts/tables/*.sql` files are kept as human-readable schema documentation and a manual fallback:

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/food_characteristics.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_type.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_schedule.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_default_item.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/meal_reminder_log.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/tables/food_register.sql
```

An **existing** database needs one-off migrations instead:

```bash
# food_register.meal_type (adds the column and backfills existing rows)
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/migrations/add_meal_type_to_food_register.sql
# renames glycemic_index -> food_characteristics and adds carbohydrate_percentage/absorption_type
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/migrations/rename_glycemic_index_to_food_characteristics.sql
# adds food_register.similar_food/similar_glycemic_index (nullable, no backfill —
# existing rows get filled in lazily the next time they're viewed)
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < sql_scripts/migrations/add_similar_food_to_food_register.sql
```

## Database backup

```bash
bash scripts/backup_mysql_databases.sh /path/to/backup/dir
```

Reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` from the environment (or, if Vault is configured, these can instead be sourced from the same Vault path the app reads — the backup script itself still expects plain env vars).

## Vault secrets

DB connection credentials, the OpenAI API key, and Slack bot credentials are read from HashiCorp Vault (KV v2, static-token auth) via `src/food_recognition/vault_client.py`, instead of being passed as plain env vars.

Each Vault path's secret **is** a JSON object — a KV v2 secret's data is inherently a set of key/value fields, which is what a JSON object is, so `_read_kv_secret()` just returns `response["data"]["data"]` as-is (no wrapper field, no nested JSON string to decode). Each secret is authored as a plain JSON file and uploaded whole with `vault kv put <path> @file.json`, which loads the file's top-level keys directly as the secret's fields. The KV v2 mount itself is `VAULT_MOUNT_POINT` (default `secret`, passed as `mount_point=` to `read_secret_version()`) — set it if your engine is mounted somewhere other than `secret/` (e.g. `kv`).

- `get_db_secrets()` reads `VAULT_DB_SECRET_PATH` (default `food_recognition/db`), expecting a JSON object with keys `host`/`port`/`user`/`password`/`name`. **Falls back to the plain `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` env vars** whenever `VAULT_ADDR`/`VAULT_TOKEN` aren't set, so local dev/tests don't require a running Vault instance.
- `get_openai_secrets()` reads `VAULT_OPENAI_SECRET_PATH` (default `food_recognition/openai`), expecting a JSON object with key `api_key`. **Falls back to the plain `OPENAI_API_KEY` env var** whenever `VAULT_ADDR`/`VAULT_TOKEN` aren't set, same as `get_db_secrets()`. Used by `food_classification.py` and `similar_food.py` instead of calling `os.getenv("OPENAI_API_KEY")` directly.
- `get_slack_secrets()` reads `VAULT_SLACK_SECRET_PATH` (default `food_recognition/slack`), expecting a JSON object with keys `bot_token` (`xoxb-...`), `app_token` (`xapp-...`), `user_id` (the Slack user ID to DM reminders to). No env-var fallback — Slack integration is opt-in and only makes sense with Vault configured; if unset, the Slack bot thread logs an error at startup and the rest of the app keeps working normally.

All three are read once and cached at module level (same pattern as `db._engine` being built once at import). Requires a Slack app already created at api.slack.com with **Socket Mode** enabled (an App-Level Token with `connections:write`), a bot token with `chat:write` scope, and Interactivity turned on — this repo does not create or configure the Slack app itself.

Sample payloads live in `vault/` (`db.example.json`, `openai.example.json`, `slack.example.json`, plus `vault/README.md`) — copy one, fill in real values, and upload it with `@<file>` (Vault CLI; the examples below assume the default `secret/` mount — swap in your own if `VAULT_MOUNT_POINT` differs, e.g. `kv/food_recognition/db`). The `VAULT_*_SECRET_PATH` env vars only cover the path *within* the mount, never the mount name itself, and never start with `/`:

```bash
cp vault/db.example.json db.json && vault kv put secret/food_recognition/db @db.json && rm db.json
cp vault/openai.example.json openai.json && vault kv put secret/food_recognition/openai @openai.json && rm openai.json
cp vault/slack.example.json slack.json && vault kv put secret/food_recognition/slack @slack.json && rm slack.json
```

## Architecture

### Request flow

1. `POST /upload` → `main.py:upload()` — decodes image with OpenCV, saves as `<uuid>.jpg` under `static/uploads/`, calls `classify_image()`.
2. `food_classification.py:classify_image()` — base64-encodes the image and sends it to GPT-4o vision. Returns a JSON array: `[{food_type, glycemic_index, weight_grams}, ...]`.
3. Each item is inserted into `food_register` via `db.py:insert_food_type()`. The image and a companion `.json` file are copied to `PHOTO_FOLDER`.
4. Redirect to `GET /view_photo/<file_uid>` — fetches all rows for that `file_uid` and calls `add_similar_food_info_to_food()`.
5. `similar_food.py:add_similar_food_info_to_food()` — for **each** food item whose `food_register.similar_food` is still `NULL`, makes a GPT-4o call to find the closest food in the `food_characteristics` reference table (via a Jinja2 prompt), reads the matched glycemic index from DB, and persists both (`db.py:update_food_register_similar_food()`) so the row never needs to be re-matched on a later view. This can still be slow the *first* time a photo with many food types is viewed, but every subsequent `/view_photo` load for that row is OpenAI-call-free.

### Slack meal-reminder flow

1. `reminder_scheduler.py:start_scheduler()` is started from `main.py` at app startup (background `APScheduler` job, interval `REMINDER_CHECK_INTERVAL_MINUTES`, default 10 min) — guarded against double-start under Flask's debug reloader via the `WERKZEUG_RUN_MAIN` env var.
2. Each tick, `check_and_send_meal_reminders()` resolves "today"/weekday in `APP_TIMEZONE` (a background job has no request/cookie to read the browser tz from, unlike `get_request_timezone()`), and for every `meal_schedule` row matching today whose `end_time` has passed:
   - if `food_register` already has a row for that `meal_type`/date → marks `meal_reminder_log.resolved_at` (if unset) and does nothing else — this is how meals logged normally via photo upload are picked up, no Slack message needed;
   - else, if no reminder has been sent yet (`meal_reminder_log.notified_at` is null) → sends the initial Slack DM via `slack_bot.send_reminder()`;
   - else, if a *later* meal's window has since started (tracked via `meal_reminder_log.last_nudge_meal_context`) → sends an escalation nudge ("you still haven't logged breakfast") — this is how a missed meal keeps getting surfaced at the next meal instead of being silently dropped.
3. The reminder DM has a "Registrar ahora" button (`slack_bot.py`, Slack Bolt, Socket Mode). Clicking it opens a modal pre-filled via `db.py:get_next_default_preset()` — the habitual `meal_default_item` preset for that `meal_type`/day, rotated to the next configured preset if that meal type's already been logged N times this week (`N % number_of_presets`). Each food-item row is a searchable `static_select` (Slack's built-in type-to-filter) sourced from `food_characteristics`, ordered by `db.py:get_food_types_ranked_by_usage()` — food_types logged for that specific `meal_type` in the last 14 days first (most-used first), then the rest of the catalog alphabetically — plus a trailing "Otro (nuevo alimento)" option that reveals a free-text block for a food not in the catalog yet. The modal also supports adding more rows ("+ Añadir alimento"), removing a pre-filled or added row ("Eliminar alimento" — hidden while only one row remains, since submit still requires at least one resolved food_type), and a native Submit button ("Finalizar").
4. On submit, `slack_bot.py:handle_meal_log_submission()` looks up each item's `food_characteristics` row first; if it's missing or has no `glycemic_index` (e.g. a brand-new food typed via "Other (new food)", or a row that was never fully populated), it calls `food_classification.py:classify_food_characteristics()` — a text-only GPT-4o call (no image) that returns `glycemic_index`/`carbohydrate_percentage`/`absorption_type` for that food by name — and persists the result via `db.py:upsert_food_characteristics()` (updates the row if it exists, inserts it otherwise) so that food_type is never re-classified by the LLM again. Each food item is then inserted via the same `db.py:insert_food_type()` used by the photo-upload flow (explicit `meal_type` passed so it isn't re-classified from the timestamp), all sharing one synthetic `file_uid` so they show up together on the existing `/view_photo/<file_uid>` page for later editing (no photo, so the `<img>` there will show broken — a known, accepted gap). `meal_reminder_log.resolved_at` is then marked and a confirmation DM is sent.
5. `/meal_default_presets` — an admin UI (same minimalist per-row-AJAX style as `/meal_schedule`/`/food_characteristics`) for editing/adding/deleting `meal_default_item` rows: which foods+quantities are habitual for a given meal type, day of week, and preset order.

### Key modules

| File | Role |
|---|---|
| `src/main.py` | Entry point; all HTTP routes; starts the reminder scheduler and Slack bot thread at startup |
| `src/food_recognition/food_classification.py` | GPT-4o vision call (`classify_image`); returns classified food list. Also `classify_food_characteristics()`, a text-only GPT-4o call used by the Slack manual-log flow to classify a food_type with no `food_characteristics` row yet |
| `src/food_recognition/similar_food.py` | GPT-4o text call; maps a free-text food name to the reference `food_characteristics` table |
| `src/food_recognition/db.py` | All MySQL queries via SQLAlchemy ORM (engine + pooled sessions, `mysql+mysqlconnector` dialect); also `sync_schema()`, the programmatic schema-sync entry point |
| `src/food_recognition/db_models.py` | SQLAlchemy declarative models (`FoodRegister`, `FoodCharacteristics`, `MealType`, `MealSchedule`, `MealDefaultItem`, `MealReminderLog`) mapping the existing tables |
| `src/food_recognition/vault_client.py` | Vault (KV v2, static token) client — `get_db_secrets()` (with env-var fallback) and `get_slack_secrets()` |
| `src/food_recognition/reminder_scheduler.py` | `APScheduler` background job that watches `meal_schedule` windows and triggers Slack reminders/escalations — see "Slack meal-reminder flow" |
| `src/food_recognition/slack_bot.py` | Slack Bolt app (Socket Mode): sends reminder DMs, opens the log-meal modal, handles its dynamic "add item"/"remove item"/submit interactions |
| `src/food_recognition/utils.py` | Shared logger (`app_logger`) and `extract_json_from_openai()` parser |
| `src/food_recognition/constants.py` | `SIMILAR_JINJA2_TEMPLATE` path and `WAIT_TIME_OPEANAI_API` |

### Database tables

- **`food_register`** — one row per food type per image (per served portion). `file_uid` groups all rows for the same photo (or the same Slack manual-log submission — see "Slack meal-reminder flow"); `uuid` is the per-row PK, generated client-side by the ORM (`default=` on `FoodRegister.uuid` in `db_models.py`). `meal_type` is a foreign key into `meal_type`, auto-classified at insert time from `meal_schedule` (`db.py:_classify_meal_type()`/`get_meal_type_for_time()`) unless passed explicitly (e.g. from the Slack modal) — falls back to `'other'` if `created_at` doesn't fall inside any configured range. Editable afterwards from `/view_photo/<file_uid>` like any other field. `similar_food`/`similar_glycemic_index` cache the result of `similar_food.py:find_similar_food()` — `NULL` until the row's first `/view_photo` load, after which it's persisted and never recomputed (see "Request flow" step 5).
- **`food_characteristics`** — reference table of per-food-type nutritional characteristics (formerly named `glycemic_index`): `food_type` (EN, primary key), `food_type_es` (ES), `glycemic_index`, `carbohydrate_percentage`, `absorption_type`. `db.py:_ensure_food_characteristics()` inserts a new row automatically whenever `insert_food_type()` sees a `food_type` not already present — using whatever the LLM classified for it — but never overwrites an existing row; that path is used by the photo-upload flow (`main.py:upload()`) and, as a no-op fallback, by the Slack manual-log flow (which upserts explicitly beforehand — see below). `db.py:upsert_food_characteristics()` is a separate upsert used by (a) manual edits from the `/food_characteristics` UI and (b) the Slack manual-log flow persisting a `classify_food_characteristics()` LLM result for a food_type with no (or an incomplete) row — unlike `_ensure_food_characteristics()`, this one does overwrite whatever fields are passed in.
- **`meal_type`** — reference table of valid meal types (`breakfast` | `lunch` | `dinner` | `other`, English canonical values). `meal_type` (the string itself) is the primary key, so other tables reference it by natural key rather than by a surrogate id — that relationship stays meaningful and intact across migrations/restores, independent of any auto-increment id. `'other'` is the fallback for `food_register` rows outside every `meal_schedule` range — it's deliberately excluded from `meal_schedule` itself (`db.py:_seed_meal_type()`).
- **`meal_schedule`** — the habitual time range (`start_time`–`end_time`) for each `meal_type`, split by `is_weekend`. `uuid` is the per-row PK (same client-side generation pattern as `food_register`); `meal_type` is a foreign key into `meal_type`; `UNIQUE(meal_type, is_weekend)` allows at most one range per combination (6 rows total). Seeded with default ranges by `db.sync_schema()` if empty. Editable from the UI at `/meal_schedule`. Used to auto-classify `food_register.meal_type` at insert time (see `db.py:get_meal_type_for_time()`) and to drive the reminder scheduler.
- **`meal_default_item`** — habitual food items for a `(meal_type, day_of_week)`, grouped into ordered presets (`preset_order`) with items ordered within a preset by `item_order`; no separate preset "header" row — a preset is just the set of rows sharing `(meal_type, day_of_week, preset_order)`. `db.sync_schema()` seeds one default breakfast preset (milk + banana, all 7 days) as a starting example; lunch/dinner start empty. Editable from `/meal_default_presets`. Used by `db.py:get_next_default_preset()` to pick which preset to pre-fill in the Slack modal (rotated weekly — see "Slack meal-reminder flow").
- **`meal_reminder_log`** — one row per `(meal_type, meal_date)` (`UNIQUE` constraint), tracking Slack reminder state: `notified_at` (first DM sent), `last_nudge_at`/`last_nudge_meal_context` (last escalation and which later meal window triggered it), `resolved_at` (cache only — the scheduler always re-derives resolution live from `food_register`). Managed entirely by `reminder_scheduler.py`/`slack_bot.py`; not user-editable.

### Important path dependency

`main.py` and `constants.py` use relative paths (`food_recognition/static/uploads`, `food_recognition/jinja2_templates/similar_files.jinja`). The app **must be launched from `src/`**; otherwise these paths break.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `changeme` | Flask session secret |
| `PHOTO_FOLDER` | — | Persistent storage path for images/JSON |
| `VAULT_ADDR` / `VAULT_TOKEN` | — | HashiCorp Vault address + static token; when unset, DB/OpenAI credentials fall back to the env vars below and Slack integration is disabled (see "Vault secrets") |
| `VAULT_MOUNT_POINT` | `secret` | Name of the KV v2 secrets engine mount (e.g. `kv`) — set if your engine isn't mounted at the default `secret/` |
| `VAULT_DB_SECRET_PATH` | `food_recognition/db` | Vault KV v2 path for DB credentials (`host`/`port`/`user`/`password`/`name`) |
| `VAULT_OPENAI_SECRET_PATH` | `food_recognition/openai` | Vault KV v2 path for the OpenAI API key (`api_key`) |
| `VAULT_SLACK_SECRET_PATH` | `food_recognition/slack` | Vault KV v2 path for Slack credentials (`bot_token`/`app_token`/`user_id`) |
| `OPENAI_API_KEY` | — | Fallback OpenAI key, used only when Vault isn't configured |
| `DB_HOST/PORT/USER/PASSWORD/NAME` | see compose | Fallback MySQL connection, used only when Vault isn't configured |
| `APP_TIMEZONE` | `UTC` | Timezone the reminder scheduler uses to resolve "today"/weekday (no per-request cookie in a background job) |
| `REMINDER_CHECK_INTERVAL_MINUTES` | `10` | How often the reminder scheduler checks for unregistered meals |
| `WAIT_TIME_OPEANAI_API` | `5` | Seconds to sleep between OpenAI calls |
| `DEFAULT_DAYS` | `30` | Default look-back window for `/meals` |

### Timezones

`created_at`/`updated_at` are always stored as naive UTC (`db.py:_utcnow()`; `FoodRegister`/`MealSchedule` rows are never written with a server-local or configurable timezone). `meal_schedule.start_time`/`end_time` are also stored as UTC time-of-day. Display-time conversion to the viewer's timezone happens per-request: an inline script in `base.html` reads `Intl.DateTimeFormat().resolvedOptions().timeZone` and stores it in a `tz` cookie (takes effect from the *next* request — the very first page load of a session may briefly render in UTC). `main.py:get_request_timezone()` reads that cookie (falling back to UTC if missing/invalid).

- Full datetimes (`created_at`): the `local_dt` Jinja filter converts a stored UTC datetime for display — used in `meals.html` and `view_photo.html`. The `/meals` date-picker filter goes the other direction: the browser-local calendar date the user picks is turned into UTC (local midnight → UTC) in `main.py:meals()` before querying.
- Bare times (`meal_schedule.start_time`/`end_time`, no date component): `main.py:_utc_time_to_local()`/`_local_time_to_utc()` convert using *today's* date as an arbitrary reference to resolve the UTC offset — used by the `/meal_schedule` route (display) and `/update_meal_schedule` (save). Because there's no real date tied to a recurring daily time, the resolved offset — and thus the displayed/stored value — can shift by an hour right at a DST boundary; this is an accepted limitation, not a bug.
- The reminder scheduler has no request/cookie to read a timezone from (it's a background job, not a request), so it uses the `APP_TIMEZONE` env var instead (default `UTC`) to resolve "today"/weekday, and combines that local date with `meal_schedule`'s stored UTC time-of-day the same approximate way `_utc_time_to_local`/`_local_time_to_utc` do — same accepted DST-boundary caveat applies (see `reminder_scheduler.py:_meal_window_utc_datetime()`).

### Known issues / watch-outs

- `similar_food.py` makes one OpenAI call per food item **the first time** that row is viewed; the match is cached in `food_register.similar_food`/`similar_glycemic_index` and reused on every later `/view_photo` load (`db.py:update_food_register_similar_food()`). Editing a row's `food_type` (`db.py:update_food_register()`) clears both cached fields back to `NULL` so the next view recomputes the match against the new food_type instead of showing a stale one.
- `update_food_register` in `main.py` is called with keyword argument `file_uid=` but the function signature uses `uuid=` — the two call sites use different parameter names; verify carefully when editing that function.
- `slack_bot.py`'s Bolt `App` is created lazily (first call to `_get_app()`), not at module import time, specifically so importing the module (e.g. from tests that monkeypatch `send_reminder()`) doesn't require Slack/Vault credentials to be configured.
- The Slack bot thread and the reminder scheduler are only started when `WERKZEUG_RUN_MAIN == 'true'` (or `app.debug` is falsy) — this guards against Flask's debug-mode reloader spawning them twice; `app.debug` is set explicitly right after the Flask app is constructed (before `sync_schema()`/the startup block run) precisely so that guard can read it ahead of the `app.run(debug=True, ...)` call at the bottom of `main.py`.
