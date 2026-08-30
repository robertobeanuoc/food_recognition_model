import main as main_module

_OWNER_A = "test-owner-a"


def _client_with_session():
    client = main_module.app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"sub": _OWNER_A, "email": "test@example.com", "name": "Test Owner"}
    return client


def test_profile_requires_login():
    client = main_module.app.test_client()

    response = client.get("/profile", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_shows_the_current_language(monkeypatch):
    monkeypatch.setattr(main_module, "get_locale", lambda sub: "en")
    client = _client_with_session()

    response = client.get("/profile")

    assert response.status_code == 200
    assert b'value="en" selected' in response.data


def test_profile_post_saves_the_chosen_language(monkeypatch):
    saved = {}
    monkeypatch.setattr(main_module, "set_locale", lambda sub, locale: saved.update(sub=sub, locale=locale))
    client = _client_with_session()

    response = client.post("/profile", data={"locale": "en"}, follow_redirects=False)

    assert response.status_code == 302
    assert saved == {"sub": _OWNER_A, "locale": "en"}


def test_profile_post_ignores_an_unsupported_language(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "set_locale", lambda sub, locale: calls.append(locale))
    client = _client_with_session()

    response = client.post("/profile", data={"locale": "fr"}, follow_redirects=False)

    assert response.status_code == 302
    assert calls == []


def test_index_renders_in_english_when_the_user_prefers_it(monkeypatch):
    monkeypatch.setattr(main_module, "get_locale", lambda sub: "en")
    client = _client_with_session()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Capture a meal" in response.data
