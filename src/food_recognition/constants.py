import os

SIMILAR_JINJA2_TEMPLATE: str = 'food_recognition/jinja2_templates/similar_files.jinja'
WAIT_TIME_OPEANAI_API: int =  int(os.getenv("WAIT_TIME_OPEANAI_API", 5))

# Owner assigned to food_register/meal_reminder_log/meal_schedule/
# meal_default_item rows created outside a web session (the Slack bot, the
# reminder scheduler) — those code paths have no logged-in user to read an
# owner from. This is a single-household stopgap: Slack today only ever
# notifies/serves one person (see vault_client.get_slack_secrets()'s
# "user_id"), so every Slack-driven row is attributed to that same person.
# Revisit when Slack becomes multi-user aware.
#
# Read from an env var rather than hardcoded here: this repo is public, and
# the value is a specific person's Authentik user UUID (sub_mode=USER_UUID
# on the "Food Recognition" OAuth2 Provider), matching the identity
# backfilled onto all pre-existing rows by scripts/backfill_owner_user_id.py.
DEFAULT_OWNER_USER_ID: str = os.environ.get("DEFAULT_OWNER_USER_ID", "")
if not DEFAULT_OWNER_USER_ID:
    raise RuntimeError(
        "DEFAULT_OWNER_USER_ID env var must be set — the Authentik user UUID "
        "that Slack/scheduler rows with no logged-in session are attributed to."
    )
