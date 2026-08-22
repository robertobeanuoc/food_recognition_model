import datetime

from food_recognition import db
from food_recognition.db import (
    create_chat_link_code,
    get_all_verified_chat_links,
    get_chat_link,
    get_owner_for_chat_identity,
    get_pending_chat_link_request,
    get_slack_installation,
    unlink_chat,
    upsert_slack_installation,
    utcnow,
    verify_chat_link,
)
from food_recognition.db_models import ChatLinkRequest

_OWNER_A = "test-owner-a"
_OWNER_B = "test-owner-b"


def test_create_chat_link_code_returns_a_usable_code_and_expiry():
    result = create_chat_link_code(_OWNER_A, "slack")

    assert len(result["link_code"]) == 8
    assert result["expires_at"] > utcnow()

    pending = get_pending_chat_link_request(_OWNER_A)
    assert pending["link_code"] == result["link_code"]
    assert pending["provider"] == "slack"
    assert pending["is_expired"] is False


def test_verify_chat_link_creates_link_and_consumes_the_code():
    result = create_chat_link_code(_OWNER_A, "slack")

    owner_user_id = verify_chat_link(
        result["link_code"], "slack", provider_chat_id="U123", provider_workspace_id="T1"
    )

    assert owner_user_id == _OWNER_A
    link = get_chat_link(_OWNER_A)
    assert link == {
        "provider": "slack",
        "provider_workspace_id": "T1",
        "provider_chat_id": "U123",
        "verified_at": link["verified_at"],
    }
    assert get_pending_chat_link_request(_OWNER_A) is None


def test_verify_chat_link_rejects_unknown_or_wrong_provider_code():
    result = create_chat_link_code(_OWNER_A, "slack")

    assert verify_chat_link("NOTREAL1", "slack", "U123", "T1") is None
    # right code, wrong provider — must not match across providers.
    assert verify_chat_link(result["link_code"], "telegram", "U123", None) is None


def test_verify_chat_link_rejects_expired_code():
    create_chat_link_code(_OWNER_A, "slack")
    with db._SessionFactory() as session:
        request = session.query(ChatLinkRequest).filter(ChatLinkRequest.owner_user_id == _OWNER_A).first()
        code = request.link_code
        request.expires_at = utcnow() - datetime.timedelta(minutes=1)
        session.commit()

    assert verify_chat_link(code, "slack", "U123", "T1") is None
    assert get_chat_link(_OWNER_A) is None


def test_regenerating_a_code_does_not_break_an_existing_verified_link():
    first = create_chat_link_code(_OWNER_A, "slack")
    verify_chat_link(first["link_code"], "slack", "U123", "T1")

    # Owner requests a new code (e.g. curiosity, or planning to re-link
    # later) but never uses it — the working link must survive untouched.
    create_chat_link_code(_OWNER_A, "slack")

    assert get_chat_link(_OWNER_A)["provider_chat_id"] == "U123"


def test_relinking_replaces_the_previous_link():
    first = create_chat_link_code(_OWNER_A, "slack")
    verify_chat_link(first["link_code"], "slack", "U123", "T1")

    second = create_chat_link_code(_OWNER_A, "slack")
    verify_chat_link(second["link_code"], "slack", "U456", "T2")

    link = get_chat_link(_OWNER_A)
    assert link["provider_chat_id"] == "U456"
    assert link["provider_workspace_id"] == "T2"


def test_get_all_verified_chat_links_scoped_by_provider():
    verify_chat_link(create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", "U1", "T1")
    verify_chat_link(create_chat_link_code(_OWNER_B, "slack")["link_code"], "slack", "U2", "T1")

    links = get_all_verified_chat_links("slack")
    owners = {link["owner_user_id"] for link in links}
    assert _OWNER_A in owners and _OWNER_B in owners
    assert get_all_verified_chat_links("telegram") == []


def test_get_owner_for_chat_identity_resolves_known_and_returns_none_for_unknown():
    verify_chat_link(create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", "U1", "T1")

    assert get_owner_for_chat_identity("slack", "U1", "T1") == _OWNER_A
    assert get_owner_for_chat_identity("slack", "U1", "T2") is None  # different workspace
    assert get_owner_for_chat_identity("slack", "U-unknown", "T1") is None


def test_unlink_chat_removes_the_link():
    verify_chat_link(create_chat_link_code(_OWNER_A, "slack")["link_code"], "slack", "U1", "T1")

    unlink_chat(_OWNER_A)

    assert get_chat_link(_OWNER_A) is None


def test_slack_installation_upsert_and_get():
    upsert_slack_installation(team_id="T1", team_name="Roberto y Lydia", bot_token="xoxb-1", installed_by=_OWNER_A)

    installation = get_slack_installation("T1")
    assert installation["team_name"] == "Roberto y Lydia"
    assert installation["bot_token"] == "xoxb-1"
    assert get_slack_installation("T-unknown") is None

    # Re-installing (e.g. token rotated) updates the same row rather than duplicating it.
    upsert_slack_installation(team_id="T1", team_name="Roberto y Lydia", bot_token="xoxb-2", installed_by=_OWNER_B)
    assert get_slack_installation("T1")["bot_token"] == "xoxb-2"
