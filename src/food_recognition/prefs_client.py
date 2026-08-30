"""Client for the shared user-prefs service (see
user-management-apps/user-prefs) - the single source of truth for each
user's preferred language across every app in this stack. Called
server-to-server only; never expose these functions to a route that takes
input straight from the browser without going through login_required. Same
shape as strava_to_db's prefs_client.py.
"""
import time

import requests

from food_recognition.utils import app_logger

DEFAULT_LOCALE = "es"
_CACHE_TTL_SECONDS = 30
_REQUEST_TIMEOUT_SECONDS = 5

_base_url: str | None = None
_api_key: str | None = None
_cache: dict[str, tuple[str, float]] = {}


def init_prefs_client(base_url: str, api_key: str) -> None:
    global _base_url, _api_key
    _base_url = base_url.rstrip("/")
    _api_key = api_key


def get_locale(sub: str) -> str:
    """Short-TTL cache (not just per-request) so a language change made in
    one app shows up in the others within a few seconds, without hitting
    user-prefs on every single request.
    """
    cached = _cache.get(sub)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    try:
        response = requests.get(
            f"{_base_url}/locale/{sub}",
            headers={"X-Api-Key": _api_key},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        locale = response.json().get("locale") or DEFAULT_LOCALE
    except Exception:
        app_logger.warning("user-prefs unreachable, falling back to %s", DEFAULT_LOCALE, exc_info=True)
        locale = DEFAULT_LOCALE
    _cache[sub] = (locale, time.monotonic() + _CACHE_TTL_SECONDS)
    return locale


def set_locale(sub: str, locale: str) -> None:
    response = requests.put(
        f"{_base_url}/locale/{sub}",
        json={"locale": locale},
        headers={"X-Api-Key": _api_key},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    _cache[sub] = (locale, time.monotonic() + _CACHE_TTL_SECONDS)
