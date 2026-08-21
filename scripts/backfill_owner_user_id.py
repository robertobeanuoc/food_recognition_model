"""One-time backfill: assign every pre-existing food_register/meal_reminder_log/
meal_schedule/meal_default_item row (owner_user_id still NULL, from before
per-user isolation was added) to a single owner. This script has no purpose
once it's been run against production and every row has an owner — delete it
afterwards.

Run against the live app container so it picks up the same Vault-based DB
credentials the app itself uses (see food_recognition/vault_client.py):

    docker compose cp scripts/backfill_owner_user_id.py web:/app/backfill_owner_user_id.py
    docker compose exec web python backfill_owner_user_id.py <owner_user_id>
    docker compose exec web rm /app/backfill_owner_user_id.py

<owner_user_id> is the Authentik `sub` claim to assign — the OAuth2
Provider's User UUID (sub_mode=USER_UUID), e.g. as printed by:

    docker compose exec server ak shell -c \
      "from authentik.core.models import User; print(User.objects.get(username='<username>').uuid)"
"""
import sys

from food_recognition.db import _engine
from sqlalchemy import text


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <owner_user_id>", file=sys.stderr)
        sys.exit(1)
    owner_user_id = sys.argv[1]

    with _engine.begin() as connection:
        results = {
            table_name: connection.execute(
                text(f"UPDATE {table_name} SET owner_user_id = :owner WHERE owner_user_id IS NULL"),
                {"owner": owner_user_id},
            )
            for table_name in ("food_register", "meal_reminder_log", "meal_schedule", "meal_default_item")
        }

    for table_name, result in results.items():
        print(f"{table_name}: {result.rowcount} row(s) assigned to {owner_user_id}")


if __name__ == "__main__":
    main()
