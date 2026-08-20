import functools
from urllib.parse import urlencode, urlsplit

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, jsonify, redirect, request, session, url_for

from food_recognition.utils import app_logger
from food_recognition.vault_client import get_oidc_secrets

auth_bp = Blueprint('auth', __name__)

oauth = OAuth()

_issuer: str | None = None


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
    """Guard a route behind an authenticated session.

    Plain page routes redirect to /login (remembering the originally
    requested URL to return to afterwards). Pass api=True for JSON/DELETE
    endpoints, which get a 401 JSON response instead of a redirect.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            if 'user' not in session:
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
