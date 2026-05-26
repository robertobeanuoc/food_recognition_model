# Food Recognition Model

Lightweight Flask app that classifies food images, stores results in a MySQL database, and augments results using OpenAI.

Quick contents
- **Code:** [src/](src/)
- **SQL schema & init scripts:** [sql_scripts/](sql_scripts/)
- **Docker:** [docker/Dockerfile](docker/Dockerfile) and [docker-compose.yml](docker-compose.yml)

Prerequisites
- Docker & Docker Compose (for containerized run)
- Local MySQL (optional if using Docker Compose)
- Environment variables (see below)

Environment variables
- `OPENAI_API_KEY` — required to use OpenAI endpoints
- `SECRET_KEY` — Flask secret key (defaults to `changeme` in compose)
- `PHOTO_FOLDER` — path where photos/outputs are copied inside container (compose sets `/photos`)
- `DEFAULT_DAYS` — default days window for meals view (defaults to `30`)
- `MYSQL_*` — database connection variables (when not using the bundled MySQL)

Local development (no Docker)
1. Create a virtualenv and activate it.
2. Install dependencies:
```bash
python -m pip install -r src/requirements.txt
```
3. Set required env vars, for example:
```bash
export OPENAI_API_KEY="sk-..."
export SECRET_KEY="your-secret"
export PHOTO_FOLDER="$PWD/photos"
mkdir -p photos src/food_recognition/static/uploads
```
4. Run the app from the `src/` folder:
```bash
python src/flask_server.py
```

Run with Docker Compose
1. Build and start services:
```bash
docker compose up --build
```
2. The Flask app will be available at http://localhost:5010

Notes on the Docker setup
- The MySQL service in `docker-compose.yml` uses `./sql_scripts` mounted to `/docker-entrypoint-initdb.d` so schema/release scripts can be applied on first startup.
- Uploads are persisted via `./src/food_recognition/static/uploads` mapped into the container and copied to `PHOTO_FOLDER` when images are processed.

API / Web routes (summary)
- `GET /` — index page
- `POST /upload` — upload an image file; triggers classification and redirects to `view_photo`
- `GET /view_photo/<file_uid>` — view classification results for an image
- `GET /meals` — view meal records (filter via `datepicker` form)
- `GET /glycemic_index/<food_type>` — returns glycemic index for a food type

Tests
- A couple of lightweight tests exist in `src/test/` (use pytest if desired).

Further work / recommendations
- Add unit tests around `food_classification` and `similar_food` logic.
- Lock dependency versions (pin exact versions) for reproducible builds.
- The Docker image serves the app using `uvicorn` via an ASGI wrapper (`asgiref.wsgi.WsgiToAsgi`).
