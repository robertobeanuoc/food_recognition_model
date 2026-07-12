import datetime
import json
import uuid as uuid_lib

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from food_recognition import db, vault_client
from food_recognition.utils import app_logger

_MEAL_TYPE_LABEL: dict[str, str] = {
    "breakfast": "breakfast",
    "lunch": "lunch",
    "dinner": "dinner",
    "other": "this meal",
}

# Sentinel food_type value for the "not in the catalog yet" option — never a
# real food_type (those come from food_characteristics), so it's safe to
# distinguish from an actual selection.
_OTHER_FOOD_TYPE_VALUE = "__other__"
_OTHER_OPTION: dict = {
    "text": {"type": "plain_text", "text": "Other (new food)"},
    "value": _OTHER_FOOD_TYPE_VALUE,
}
# Slack's hard limit on how many options a static_select can carry; -1 to
# always leave room for _OTHER_OPTION appended at the end.
_MAX_STATIC_SELECT_OPTIONS = 100

_app: App | None = None


def _get_app() -> App:
    """Bolt App is created lazily (not at import time) so importing this
    module — e.g. from tests that monkeypatch send_reminder() — doesn't
    require Slack/Vault credentials to be configured.
    """
    global _app
    if _app is None:
        secrets = vault_client.get_slack_secrets()
        _app = App(token=secrets["bot_token"])
        _register_handlers(_app)
    return _app


def start_bot() -> None:
    """Blocking call — run in a background daemon thread (see main.py)."""
    secrets = vault_client.get_slack_secrets()
    app = _get_app()
    handler = SocketModeHandler(app, secrets["app_token"])
    app_logger.info("Starting Slack bot (Socket Mode)")
    handler.start()


def send_reminder(meal_type: str, meal_date: datetime.date, escalation: bool = False) -> None:
    secrets = vault_client.get_slack_secrets()
    app = _get_app()
    meal_label = _MEAL_TYPE_LABEL.get(meal_type, meal_type)
    text = (
        f"You still haven't logged {meal_label} today ({meal_date.isoformat()})."
        if escalation
        else f"You haven't logged {meal_label} today ({meal_date.isoformat()})."
    )
    value = json.dumps({"meal_type": meal_type, "meal_date": meal_date.isoformat()})
    app.client.chat_postMessage(
        channel=secrets["user_id"],
        text=text,
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Log now"},
                        "action_id": "open_meal_form",
                        "value": value,
                    }
                ],
            },
        ],
    )


def _food_type_options(catalog: list[dict], current_food_type: str | None) -> list[dict]:
    """static_select options from the ranked catalog, plus the "Otro" sentinel.

    Ensures `current_food_type` is present as an option even if it fell
    outside the catalog/cap (e.g. a habitual preset item rarely logged
    recently) — Slack requires initial_option to match one of the provided
    options exactly, or the modal fails to render.
    """
    options = [
        {
            "text": {"type": "plain_text", "text": (row["food_type_es"] or row["food_type"])[:75]},
            "value": row["food_type"],
        }
        for row in catalog
    ]
    known_values = {option["value"] for option in options}
    if current_food_type and current_food_type != _OTHER_FOOD_TYPE_VALUE and current_food_type not in known_values:
        options.insert(0, {"text": {"type": "plain_text", "text": current_food_type}, "value": current_food_type})
    return options[: _MAX_STATIC_SELECT_OPTIONS - 1] + [_OTHER_OPTION]


def _food_item_blocks(
    index: int,
    catalog: list[dict],
    food_type: str | None = None,
    weight_grams: int = None,
    custom_food_type: str = "",
    removable: bool = False,
) -> list[dict]:
    number_element: dict = {"type": "number_input", "action_id": "weight_grams", "is_decimal_allowed": False}
    if weight_grams is not None:
        number_element["initial_value"] = str(weight_grams)

    options = _food_type_options(catalog, food_type)
    select_element: dict = {
        "type": "static_select",
        "action_id": "food_type_select",
        "placeholder": {"type": "plain_text", "text": "Search for a food..."},
        "options": options,
    }
    if food_type:
        initial_option = next((option for option in options if option["value"] == food_type), None)
        if initial_option:
            select_element["initial_option"] = initial_option

    blocks: list[dict] = [
        {
            "type": "input",
            "block_id": f"food_{index}",
            # Fires a block_actions payload on selection so the modal can be
            # rebuilt to reveal/hide the "custom name" field below.
            "dispatch_action": True,
            "optional": True,
            "label": {"type": "plain_text", "text": f"Food item {index + 1}"},
            "element": select_element,
        },
    ]

    if food_type == _OTHER_FOOD_TYPE_VALUE:
        blocks.append(
            {
                "type": "input",
                "block_id": f"food_custom_{index}",
                "optional": True,
                "label": {"type": "plain_text", "text": "New food name"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "food_type_custom",
                    "initial_value": custom_food_type or "",
                },
            }
        )

    blocks.append(
        {
            "type": "input",
            "block_id": f"grams_{index}",
            "label": {"type": "plain_text", "text": "Amount (g)"},
            "optional": True,
            "element": number_element,
        }
    )

    # Only offer to remove a row when it's not the last one left — with a
    # single row, submit still requires at least one non-empty food_type, so
    # the way to "empty" it is just leaving the picker unselected.
    if removable:
        blocks.append(
            {
                "type": "actions",
                "block_id": f"remove_actions_{index}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Remove food item"},
                        "action_id": "remove_food_item",
                        "value": str(index),
                        "style": "danger",
                    }
                ],
            }
        )
    return blocks


def _build_modal_view(meal_type: str, meal_date: datetime.date, items: list[dict]) -> dict:
    if not items:
        items = [{"food_type": None, "weight_grams": None}]

    catalog = db.get_food_types_ranked_by_usage(meal_type)

    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{_MEAL_TYPE_LABEL.get(meal_type, meal_type).capitalize()}* — {meal_date.isoformat()}",
            },
        }
    ]
    for index, item in enumerate(items):
        blocks.extend(
            _food_item_blocks(
                index,
                catalog,
                item.get("food_type"),
                item.get("weight_grams"),
                item.get("custom_food_type", ""),
                removable=len(items) > 1,
            )
        )
    blocks.append(
        {
            "type": "actions",
            "block_id": "add_item_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "+ Add food item"},
                    "action_id": "add_food_item",
                }
            ],
        }
    )

    private_metadata = json.dumps(
        {"meal_type": meal_type, "meal_date": meal_date.isoformat(), "item_count": len(items)}
    )
    return {
        "type": "modal",
        "callback_id": "meal_log_modal",
        "private_metadata": private_metadata,
        "title": {"type": "plain_text", "text": "Log meal"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def _parse_state_items(state_values: dict, item_count: int) -> list[dict]:
    items = []
    for index in range(item_count):
        selected_option = state_values.get(f"food_{index}", {}).get("food_type_select", {}).get("selected_option")
        food_type = selected_option["value"] if selected_option else None
        custom_food_type = (
            state_values.get(f"food_custom_{index}", {}).get("food_type_custom", {}).get("value") or ""
        )
        grams_raw = state_values.get(f"grams_{index}", {}).get("weight_grams", {}).get("value")
        items.append(
            {
                "food_type": food_type,
                "custom_food_type": custom_food_type,
                "weight_grams": int(grams_raw) if grams_raw not in (None, "") else None,
            }
        )
    return items


def _resolve_food_type(item: dict) -> str:
    """The actual food_type string an item resolves to: the free-typed name
    when "Other (new food)" was picked, otherwise the dropdown value."""
    if item["food_type"] == _OTHER_FOOD_TYPE_VALUE:
        return item["custom_food_type"].strip()
    return (item["food_type"] or "").strip()


def _register_handlers(app: App) -> None:
    @app.action("open_meal_form")
    def handle_open_meal_form(ack, body, client):
        ack()
        payload = json.loads(body["actions"][0]["value"])
        meal_type = payload["meal_type"]
        meal_date = datetime.date.fromisoformat(payload["meal_date"])
        items = db.get_next_default_preset(meal_type, meal_date)
        client.views_open(
            trigger_id=body["trigger_id"],
            view=_build_modal_view(meal_type, meal_date, items),
        )

    @app.action("add_food_item")
    def handle_add_food_item(ack, body, client):
        ack()
        view = body["view"]
        metadata = json.loads(view["private_metadata"])
        meal_type = metadata["meal_type"]
        meal_date = datetime.date.fromisoformat(metadata["meal_date"])

        items = _parse_state_items(view["state"]["values"], metadata["item_count"])
        items.append({"food_type": None, "weight_grams": None})

        client.views_update(view_id=view["id"], view=_build_modal_view(meal_type, meal_date, items))

    @app.action("food_type_select")
    def handle_food_type_select(ack, body, client):
        # Just re-renders the modal from current state: picking "Other (new
        # food)" needs to reveal the free-text block below it, and picking
        # anything else needs to hide it again if it was showing.
        ack()
        view = body["view"]
        metadata = json.loads(view["private_metadata"])
        meal_type = metadata["meal_type"]
        meal_date = datetime.date.fromisoformat(metadata["meal_date"])

        items = _parse_state_items(view["state"]["values"], metadata["item_count"])
        client.views_update(view_id=view["id"], view=_build_modal_view(meal_type, meal_date, items))

    @app.action("remove_food_item")
    def handle_remove_food_item(ack, body, client):
        ack()
        view = body["view"]
        metadata = json.loads(view["private_metadata"])
        meal_type = metadata["meal_type"]
        meal_date = datetime.date.fromisoformat(metadata["meal_date"])

        items = _parse_state_items(view["state"]["values"], metadata["item_count"])
        remove_index = int(body["actions"][0]["value"])
        if 0 <= remove_index < len(items):
            items.pop(remove_index)

        client.views_update(view_id=view["id"], view=_build_modal_view(meal_type, meal_date, items))

    @app.view("meal_log_modal")
    def handle_meal_log_submission(ack, view, client):
        metadata = json.loads(view["private_metadata"])
        meal_type = metadata["meal_type"]
        meal_date = datetime.date.fromisoformat(metadata["meal_date"])

        items = _parse_state_items(view["state"]["values"], metadata["item_count"])
        for item in items:
            item["resolved_food_type"] = _resolve_food_type(item)
        parsed_items = [item for item in items if item["resolved_food_type"]]

        if not parsed_items:
            ack(response_action="errors", errors={"food_0": "Add at least one food item"})
            return

        ack()

        file_uid = str(uuid_lib.uuid4())
        # Backdate to the meal's habitual start_time (not "now") so a meal
        # logged late (e.g. via the escalation nudge, hours after it should
        # have happened) still lands in its own meal_schedule window instead
        # of whatever window the actual submission time falls into.
        is_weekend = meal_date.weekday() >= 5
        start_time = db.get_meal_schedule_start_time(meal_type, is_weekend)
        created_at = datetime.datetime.combine(meal_date, start_time or db.utcnow().time())
        for item in parsed_items:
            food_type = item["resolved_food_type"]
            weight_grams = item["weight_grams"]

            # Carry over the full food_characteristics row (if this food_type
            # is already known) instead of just the glycemic_index, same
            # fields the photo-upload flow gets from GPT-4o — otherwise
            # carbohydrate_percentage/carbohydrate_weight_grams/absorption_type
            # are silently left NULL on the food_register row.
            characteristics = db.get_food_characteristics(food_type) or {}
            glycemic_index = characteristics.get("glycemic_index") or 0
            carbohydrate_percentage = characteristics.get("carbohydrate_percentage")
            absorption_type = characteristics.get("absorption_type")
            carbohydrate_weight_grams = (
                carbohydrate_percentage * weight_grams / 100
                if carbohydrate_percentage is not None and weight_grams is not None
                else None
            )

            db.insert_food_type(
                file_uid=file_uid,
                food_type=food_type,
                glycemic_index=glycemic_index,
                weight_grams=weight_grams,
                meal_type=meal_type,
                carbohydrate_percentage=carbohydrate_percentage,
                carbohydrate_weight_grams=carbohydrate_weight_grams,
                absorption_type=absorption_type,
                created_at=created_at,
            )
        db.mark_meal_reminder_resolved(meal_type, meal_date)

        secrets = vault_client.get_slack_secrets()
        meal_label = _MEAL_TYPE_LABEL.get(meal_type, meal_type)
        client.chat_postMessage(
            channel=secrets["user_id"],
            text=f"✅ Logged {meal_label} for {meal_date.isoformat()} ({len(parsed_items)} item(s)).",
        )
