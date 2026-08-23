import main as main_module

from food_recognition.db import create_chat_link_code, upsert_slack_installation, verify_chat_link

_OWNER_A = "test-owner-a"


def _client_with_session():
    client = main_module.app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"sub": _OWNER_A, "email": "test@example.com", "name": "Test Owner"}
    return client


def test_chat_settings_renders_when_not_linked():
    client = _client_with_session()

    response = client.get("/settings/chat")

    assert response.status_code == 200
    assert b"Not linked yet" in response.data


def test_chat_settings_renders_when_linked():
    upsert_slack_installation(team_id="T1", team_name="Test Workspace", bot_token="xoxb-test", installed_by=_OWNER_A)
    verify_chat_link(
        create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", provider_chat_id="U1", provider_workspace_id="T1"
    )
    client = _client_with_session()

    response = client.get("/settings/chat")

    assert response.status_code == 200
    assert b"Linked" in response.data
    assert b"Test Workspace" in response.data


def test_generate_link_code_endpoint_returns_a_code():
    client = _client_with_session()

    response = client.post("/settings/chat/link-code")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["link_code"]) == 8


def test_unlink_endpoint_removes_the_link():
    verify_chat_link(
        create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", provider_chat_id="U1", provider_workspace_id="T1"
    )
    client = _client_with_session()

    response = client.post("/settings/chat/unlink")

    assert response.status_code == 200
    from food_recognition.db import get_chat_link

    assert get_chat_link(_OWNER_A) is None


def test_slack_install_redirects_to_slack_oauth_authorize():
    client = _client_with_session()

    response = client.get("/slack/install", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("https://slack.com/oauth/v2/authorize")


def test_index_banner_appears_when_not_linked_and_hides_after_linking():
    client = _client_with_session()

    response = client.get("/")
    assert b"Set it up" in response.data

    upsert_slack_installation(team_id="T1", team_name="Test Workspace", bot_token="xoxb-test", installed_by=_OWNER_A)
    verify_chat_link(
        create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", provider_chat_id="U1", provider_workspace_id="T1"
    )
    client = _client_with_session()  # fresh client/session so `g` isn't cached from the previous request
    response = client.get("/")
    assert b"Set it up" not in response.data
