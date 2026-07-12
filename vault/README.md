# Vault secret samples

Sample payloads for the JSON documents this app expects at each Vault KV v2 path
(see "Vault secrets" in the repo root `README.md`/`CLAUDE.md`). Copy one, fill in
real values, and upload it — never commit the filled-in version:

```bash
cp vault/db.example.json db.json      # edit db.json with real values
vault kv put secret/food_recognition/db @db.json
rm db.json
```

`@db.json` uploads the file's top-level JSON keys directly as the secret's
fields (`host`, `port`, ... become the secret's own key/value pairs) — there
is no wrapper field, the secret itself is the JSON object.

| File | Vault path (default) |
|---|---|
| `db.example.json` | `food_recognition/db` (`VAULT_DB_SECRET_PATH`) |
| `openai.example.json` | `food_recognition/openai` (`VAULT_OPENAI_SECRET_PATH`) |
| `slack.example.json` | `food_recognition/slack` (`VAULT_SLACK_SECRET_PATH`) |

Any non-`.example.json` file in this directory is gitignored, so it's safe to
stage a real copy here temporarily while preparing a `vault kv put` — just
remember to delete it afterwards.
