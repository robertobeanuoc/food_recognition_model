import os

import hvac

from food_recognition.utils import app_logger

_DB_SECRET_KEYS = ("host", "port", "user", "password", "name")
_SLACK_SECRET_KEYS = ("bot_token", "app_token", "user_id")
_OPENAI_SECRET_KEYS = ("api_key",)

_db_secrets_cache: dict | None = None
_slack_secrets_cache: dict | None = None
_openai_secrets_cache: dict | None = None


def _vault_configured() -> bool:
    return bool(os.getenv("VAULT_ADDR")) and bool(os.getenv("VAULT_TOKEN"))


def _read_kv_secret(path: str) -> dict:
    """Read a Vault KV v2 secret.

    A KV v2 secret's data is already a JSON object (that's what `vault kv get
    -format=json` / the UI's "JSON" view show) — each top-level key here is
    one credential field. Secrets are authored as a JSON file and uploaded
    with `vault kv put <path> @file.json`, which loads the file's top-level
    keys directly as that object; there is no extra wrapper field to unwrap.
    """
    client = hvac.Client(url=os.getenv("VAULT_ADDR"), token=os.getenv("VAULT_TOKEN"))
    mount_point = os.getenv("VAULT_MOUNT_POINT", "secret")
    response = client.secrets.kv.v2.read_secret_version(path=path, mount_point=mount_point)
    return response["data"]["data"]


def get_db_secrets() -> dict:
    """MySQL connection credentials: host/port/user/password/name.

    Read from Vault KV v2 at VAULT_DB_SECRET_PATH when VAULT_ADDR/VAULT_TOKEN
    are set. Falls back to the plain DB_HOST/PORT/USER/PASSWORD/NAME env vars
    otherwise, so local dev/tests don't require a running Vault instance.
    """
    global _db_secrets_cache
    if _db_secrets_cache is not None:
        return _db_secrets_cache

    if _vault_configured():
        path = os.getenv("VAULT_DB_SECRET_PATH", "food_recognition/db")
        secrets = _read_kv_secret(path)
        missing = [key for key in _DB_SECRET_KEYS if key not in secrets]
        if missing:
            raise ValueError(f"Vault secret at '{path}' is missing keys: {missing}")
        app_logger.info("Loaded DB credentials from Vault path '%s'", path)
        _db_secrets_cache = {key: secrets[key] for key in _DB_SECRET_KEYS}
    else:
        app_logger.info("VAULT_ADDR/VAULT_TOKEN not set — reading DB credentials from env vars")
        _db_secrets_cache = {
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "name": os.getenv("DB_NAME"),
        }
    return _db_secrets_cache


def get_openai_secrets() -> dict:
    """OpenAI credentials: api_key.

    Read from Vault KV v2 at VAULT_OPENAI_SECRET_PATH when VAULT_ADDR/VAULT_TOKEN
    are set. Falls back to the plain OPENAI_API_KEY env var otherwise, same
    pattern as get_db_secrets().
    """
    global _openai_secrets_cache
    if _openai_secrets_cache is not None:
        return _openai_secrets_cache

    if _vault_configured():
        path = os.getenv("VAULT_OPENAI_SECRET_PATH", "food_recognition/openai")
        secrets = _read_kv_secret(path)
        missing = [key for key in _OPENAI_SECRET_KEYS if key not in secrets]
        if missing:
            raise ValueError(f"Vault secret at '{path}' is missing keys: {missing}")
        app_logger.info("Loaded OpenAI credentials from Vault path '%s'", path)
        _openai_secrets_cache = {key: secrets[key] for key in _OPENAI_SECRET_KEYS}
    else:
        app_logger.info("VAULT_ADDR/VAULT_TOKEN not set — reading OpenAI credentials from env vars")
        _openai_secrets_cache = {"api_key": os.getenv("OPENAI_API_KEY")}
    return _openai_secrets_cache


def get_slack_secrets() -> dict:
    """Slack credentials: bot_token/app_token/user_id, read from Vault KV v2
    at VAULT_SLACK_SECRET_PATH. Unlike DB credentials there is no env-var
    fallback — Slack integration is opt-in and only makes sense with Vault
    configured.
    """
    global _slack_secrets_cache
    if _slack_secrets_cache is not None:
        return _slack_secrets_cache

    if not _vault_configured():
        raise RuntimeError("VAULT_ADDR/VAULT_TOKEN must be set to read Slack credentials")

    path = os.getenv("VAULT_SLACK_SECRET_PATH", "food_recognition/slack")
    secrets = _read_kv_secret(path)
    missing = [key for key in _SLACK_SECRET_KEYS if key not in secrets]
    if missing:
        raise ValueError(f"Vault secret at '{path}' is missing keys: {missing}")
    app_logger.info("Loaded Slack credentials from Vault path '%s'", path)
    _slack_secrets_cache = {key: secrets[key] for key in _SLACK_SECRET_KEYS}
    return _slack_secrets_cache
