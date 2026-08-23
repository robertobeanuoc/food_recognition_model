import functools
from urllib.parse import urlencode, urlsplit

import requests
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from authlib.jose import jwt as jose_jwt
from authlib.jose.errors import JoseError
from flask import Blueprint, g, jsonify, redirect, request, session, url_for

from food_recognition.utils import app_logger
from food_recognition.vault_client import get_oidc_secrets

auth_bp = Blueprint('auth', __name__)

oauth = OAuth()

_issuer: str | None = None

# Cached JWKS for verifying Bearer access tokens (see _verify_bearer_token
# below) — deliberately independent of `oauth`/`init_oauth()`, which isn't
# set up at all outside a real running app (see main.py's WERKZEUG_RUN_MAIN
# guard), so Bearer-token verification stays testable on its own.
_jwks_cache: dict | None = None


def init_oauth(app) -> None:
    """Register the Authentik OIDC client. Call once at app startup."""
    global _issuer
    secrets: dict = get_oidc_secrets()
    _issuer = secrets['issuer'].rstrip('/')
    oauth.init_app(app)
    oauth.register(
        name='authentik',
        client_id=secrets['client_id'],
        client_secret=secrets['client_secret'],
        server_metadata_url=f"{_issuer}/.well-known/openid-configuration",
        client_kwargs={'scope': 'openid profile email'},
    )


def _get_jwks(issuer: str, force_refresh: bool = False) -> dict:
    """JWKS for `issuer`, cached at module level after the first fetch.
    Refetched once by _decode_bearer_claims() below if a token's kid isn't
    found in the cached set — covers Authentik's signing key rotating
    without requiring an app restart here.
    """
    global _jwks_cache
    if _jwks_cache is None or force_refresh:
        response = requests.get(f"{issuer}/jwks/", timeout=5)
        response.raise_for_status()
        _jwks_cache = response.json()
    return _jwks_cache


def _decode_bearer_claims(token: str, issuer: str):
    """Verify `token`'s RS256 signature against `issuer`'s JWKS and its
    `iss`/`exp` claims. Raises JoseError/ValueError on any failure — the
    caller (_verify_bearer_token) is responsible for turning that into a
    401, never a 500: an untrusted client-supplied token failing validation
    is expected, ordinary traffic, not a server error.
    """
    claims_options = {
        'iss': {'essential': True, 'values': [issuer]},
        'exp': {'essential': True},
    }
    jwks = _get_jwks(issuer)
    try:
        claims = jose_jwt.decode(token, jwks, claims_options=claims_options)
    except ValueError:
        # Authlib raises ValueError("Invalid JSON Web Key Set") when the
        # token's kid isn't in our cached JWKS.
        jwks = _get_jwks(issuer, force_refresh=True)
        claims = jose_jwt.decode(token, jwks, claims_options=claims_options)
    claims.validate()
    return claims


def _verify_bearer_token(token: str) -> dict | None:
    """Validate an OIDC access token issued by Authentik for this app: an
    RS256 JWT, verified locally against its JWKS (no per-request round-trip
    to Authentik — Authentik issues self-contained JWT access tokens, not
    opaque reference tokens). Returns the same {'sub', 'email', 'name'}
    shape /auth/callback stores in session['user'], or None if the token is
    missing/expired/mis-signed, for a different issuer, or issued to a
    different OIDC client than this app's own.

    This is what lets a future API client (mobile app, SPA) call the same
    routes a browser session already can, without ever holding this app's
    session cookie.
    """
    try:
        secrets: dict = get_oidc_secrets()
        claims = _decode_bearer_claims(token, secrets['issuer'].rstrip('/'))
    except (JoseError, ValueError, requests.RequestException) as e:
        app_logger.warning(f"Bearer token rejected: {e}")
        return None

    # azp ("authorized party") is the client_id Authentik issued this token
    # to. Checked separately from claims_options above because a correctly
    # signed, non-expired token from ANY OTHER Authentik-registered client
    # (e.g. one of the other apps in this ecosystem) must still be rejected
    # here — trusted_client_ids is a set (not a single value) so a future
    # second client_id (e.g. a public/PKCE mobile client) can be added
    # later without changing this logic.
    trusted_client_ids = {secrets['client_id']}
    if claims.get('azp') not in trusted_client_ids:
        app_logger.warning(f"Bearer token rejected: untrusted client '{claims.get('azp')}'")
        return None

    return {
        'sub': claims.get('sub'),
        'email': claims.get('email'),
        'name': claims.get('name') or claims.get('preferred_username'),
    }


def _authenticate_request() -> dict | None:
    """Resolve who this request is from: a Bearer access token (API
    clients) takes priority if the header is present, otherwise the browser
    session (session['user'], set at /auth/callback). Cached on flask.g so
    a request is only authenticated once no matter how many times
    current_user()/login_required run during it.
    """
    if 'current_user' not in g:
        auth_header: str = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            g.current_user = _verify_bearer_token(auth_header[len('Bearer '):])
        else:
            g.current_user = session.get('user')
    return g.current_user


def current_user() -> dict | None:
    """The authenticated identity for this request — {'sub', 'email', 'name'},
    from either a Bearer token or the browser session — or None if
    unauthenticated. Routes should read this instead of session['user']
    directly, so the same code path works for both."""
    return _authenticate_request()


@auth_bp.route('/login')
def login():
    redirect_uri: str = url_for('auth.callback', _external=True)
    return oauth.authentik.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/callback')
def callback():
    try:
        token: dict = oauth.authentik.authorize_access_token()
    except OAuthError as e:
        # Cancelled consent, a stale/replayed callback URL, or an expired
        # `state` all land here — without this, Authlib's exception would
        # otherwise hit Flask's debug-mode error page unhandled.
        app_logger.warning(f"OIDC callback rejected: {e}")
        return redirect(url_for('auth.login'))
    userinfo: dict = token.get('userinfo') or oauth.authentik.userinfo(token=token)
    session['user'] = {
        'sub': userinfo.get('sub'),
        'email': userinfo.get('email'),
        'name': userinfo.get('name') or userinfo.get('preferred_username'),
    }
    # Needed at /logout to also end the Authentik-side SSO session (id_token_hint) —
    # without it, Authentik's own session cookie survives our local logout and the
    # next /login silently re-authenticates instead of prompting again.
    session['id_token'] = token.get('id_token')
    app_logger.info(f"User {session['user'].get('email')} logged in")
    next_url: str | None = session.pop('next_url', None)
    return redirect(next_url or url_for('index'))


@auth_bp.route('/logout')
def logout():
    id_token: str | None = session.pop('id_token', None)
    session.pop('user', None)
    session.pop('next_url', None)
    end_session_url: str = f"{_issuer}/end-session/"
    if id_token:
        end_session_url += f"?{urlencode({'id_token_hint': id_token})}"
    return redirect(end_session_url)


def unauthenticated_response():
    """Shared 401 JSON response for any endpoint gating on `'user' in session`
    outside of `login_required` itself (e.g. a blueprint's before_request)."""
    return jsonify({"error": "unauthenticated"}), 401


def login_required(view_func=None, *, api: bool = False):
    """Guard a route behind an authenticated request — a browser session
    (session['user']) or a Bearer access token (see _verify_bearer_token),
    checked via current_user().

    Plain page routes redirect to /login (remembering the originally
    requested URL to return to afterwards) — meaningless for a token-bearing
    API client, but such a client should only ever call api=True endpoints
    in practice. Pass api=True for JSON/DELETE endpoints, which get a 401
    JSON response instead of a redirect.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            if current_user() is None:
                if api:
                    return unauthenticated_response()
                # Path + query only (never the scheme/host request.url would
                # include) so a spoofed/forwarded Host header can't turn this
                # into a post-login redirect off the app's own routes.
                split = urlsplit(request.url)
                session['next_url'] = split.path + (f"?{split.query}" if split.query else "")
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return wrapped

    if view_func is not None:
        return decorator(view_func)
    return decorator
