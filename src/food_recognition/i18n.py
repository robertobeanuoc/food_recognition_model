"""Minimal ES/EN translation helper - no gettext/Babel, since a single
toolchain doesn't fit uniformly across this household's app stacks
(Flask+Jinja here, FastAPI+JS and Streamlit elsewhere). Same shape as
strava_to_db's i18n.py. The preference itself lives in the shared
user-prefs service (see prefs_client.py), not here - this module only
turns a locale string into rendered text.
"""
import json
import os

SUPPORTED_LOCALES = ("es", "en")
DEFAULT_LOCALE = "es"

_LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")
_translations: dict[str, dict[str, str]] = {}


def _load(locale: str) -> dict[str, str]:
    if locale not in _translations:
        path = os.path.join(_LOCALES_DIR, f"{locale}.json")
        with open(path, encoding="utf-8") as f:
            _translations[locale] = json.load(f)
    return _translations[locale]


def translate(locale: str, key: str) -> str:
    return _load(locale).get(key) or _load(DEFAULT_LOCALE).get(key) or key


def js_translations(locale: str) -> dict[str, str]:
    """The "js.*" keys, with that prefix stripped, for exposing to static JS
    files via window.__I18N__ (see base.html) - everything else stays
    server-side only.
    """
    return {key[len("js."):]: value for key, value in _load(locale).items() if key.startswith("js.")}
