import datetime

from food_recognition import slack_bot
from food_recognition.db import create_chat_link_code, upsert_slack_installation, verify_chat_link

_OWNER_A = "test-owner-a"


def test_send_reminder_returns_false_when_owner_has_no_link():
    sent = slack_bot.send_reminder(_OWNER_A, "breakfast", datetime.date(2026, 3, 2))
    assert sent is False


def test_send_reminder_returns_false_when_installation_is_gone(monkeypatch):
    # Linked to a workspace that was never (or no longer) installed.
    verify_chat_link(
        create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", provider_chat_id="U1", provider_workspace_id="T-missing"
    )

    sent = slack_bot.send_reminder(_OWNER_A, "breakfast", datetime.date(2026, 3, 2))

    assert sent is False


def test_send_reminder_posts_to_the_linked_chat_using_that_workspaces_token(monkeypatch):
    upsert_slack_installation(team_id="T1", team_name="Test Workspace", bot_token="xoxb-test", installed_by=_OWNER_A)
    verify_chat_link(
        create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", provider_chat_id="U1", provider_workspace_id="T1"
    )

    calls = []

    def _fake_chat_postMessage(self, **kwargs):
        calls.append({"token": self.token, **kwargs})
        return {"ok": True}

    monkeypatch.setattr(slack_bot.WebClient, "chat_postMessage", _fake_chat_postMessage)

    sent = slack_bot.send_reminder(_OWNER_A, "breakfast", datetime.date(2026, 3, 2))

    assert sent is True
    assert len(calls) == 1
    assert calls[0]["token"] == "xoxb-test"
    assert calls[0]["channel"] == "U1"


def test_owner_from_command_body_resolves_flat_team_and_user_ids():
    verify_chat_link(
        create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", provider_chat_id="U1", provider_workspace_id="T1"
    )

    body = {"team_id": "T1", "user_id": "U1"}
    assert slack_bot._owner_from_command_body(body) == _OWNER_A
    assert slack_bot._owner_from_command_body({"team_id": "T1", "user_id": "U-unknown"}) is None


def test_owner_from_interaction_body_resolves_nested_team_and_user_ids():
    verify_chat_link(
        create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", provider_chat_id="U1", provider_workspace_id="T1"
    )

    body = {"team": {"id": "T1"}, "user": {"id": "U1"}}
    assert slack_bot._owner_from_interaction_body(body) == _OWNER_A
    assert slack_bot._owner_from_interaction_body({"team": {"id": "T2"}, "user": {"id": "U1"}}) is None


def test_build_install_url_carries_state_and_scopes():
    url = slack_bot.build_install_url("random-state-123")

    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "state=random-state-123" in url
    assert "chat%3Awrite" in url or "chat:write" in url


def test_slack_authorize_returns_none_for_an_uninstalled_team():
    assert slack_bot._slack_authorize("T-never-installed") is None


def test_slack_authorize_returns_the_installations_bot_token():
    upsert_slack_installation(team_id="T2", team_name="Another", bot_token="xoxb-another", installed_by=_OWNER_A)

    result = slack_bot._slack_authorize("T2")

    assert result.bot_token == "xoxb-another"
    assert result.team_id == "T2"
