"""
Twitch OAuth 2.0 Authentication Flow.

Supports two modes:
1. Direct token: if TWITCH_ACCESS_TOKEN is set in .env, use it immediately.
2. Authorization Code Flow: opens a local HTTP server, redirects user to
   Twitch, captures the authorization code, exchanges it for tokens and
   caches them in .token_cache.json.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN_CACHE = Path(".token_cache.json")
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"

# Required Twitch scopes for reading subscriptions
SCOPES = ["user:read:subscriptions", "user:read:email"]


# ─── Token cache ─────────────────────────────────────────────────────────────

def _load_cached_tokens() -> dict:
    if TOKEN_CACHE.exists():
        return json.loads(TOKEN_CACHE.read_text())
    return {}


def _save_tokens(tokens: dict) -> None:
    TOKEN_CACHE.write_text(json.dumps(tokens, indent=2))
    TOKEN_CACHE.chmod(0o600)  # restrict to owner only


# ─── Validate a token against Twitch ─────────────────────────────────────────

def validate_token(access_token: str) -> bool:
    """Returns True if the token is still valid."""
    resp = httpx.get(
        TWITCH_VALIDATE_URL,
        headers={"Authorization": f"OAuth {access_token}"},
    )
    return resp.status_code == 200


# ─── Refresh token ────────────────────────────────────────────────────────────

def refresh_access_token(refresh_token: str) -> dict:
    """Exchange a refresh token for a new access + refresh token pair."""
    resp = httpx.post(
        TWITCH_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": os.environ["TWITCH_CLIENT_ID"],
            "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
        },
    )
    resp.raise_for_status()
    tokens = resp.json()
    _save_tokens(tokens)
    return tokens


# ─── Authorization Code Flow ──────────────────────────────────────────────────

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the ?code= query parameter."""

    code: Optional[str] = None
    state: Optional[str] = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _OAuthCallbackHandler.code = params.get("code", [None])[0]
        _OAuthCallbackHandler.state = params.get("state", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            b"<h2>Authentication successful! You can close this tab.</h2>"
        )

    def log_message(self, *args):  # silence server logs
        pass


def _run_local_server(port: int) -> Optional[str]:
    """Start a one-shot local server, wait for the OAuth callback, return code."""
    server = HTTPServer(("localhost", port), _OAuthCallbackHandler)
    server.handle_request()
    server.server_close()
    return _OAuthCallbackHandler.code


def _authorization_code_flow() -> dict:
    """Full browser-based OAuth flow. Returns token dict."""
    client_id = os.environ["TWITCH_CLIENT_ID"]
    client_secret = os.environ["TWITCH_CLIENT_SECRET"]
    redirect_uri = os.environ.get("TWITCH_REDIRECT_URI", "http://localhost:3000/callback")

    port = int(urlparse(redirect_uri).port or 3000)
    state = secrets.token_urlsafe(16)

    auth_url = TWITCH_AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "force_verify": "true",
    })

    print(f"[auth] Opening browser for Twitch login...\n  {auth_url}")
    webbrowser.open(auth_url)

    # Start local server in background thread so we can open browser first
    code_holder: list[Optional[str]] = [None]

    def _serve():
        server = HTTPServer(("localhost", port), _OAuthCallbackHandler)
        server.handle_request()
        server.server_close()
        code_holder[0] = _OAuthCallbackHandler.code

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    t.join(timeout=120)

    code = code_holder[0]
    if not code:
        raise RuntimeError("OAuth callback not received within 2 minutes.")

    # Exchange code for tokens
    resp = httpx.post(
        TWITCH_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    resp.raise_for_status()
    tokens = resp.json()
    _save_tokens(tokens)
    print("[auth] Tokens obtained and cached.")
    return tokens


# ─── Public API ───────────────────────────────────────────────────────────────

def get_access_token() -> str:
    """
    Return a valid Twitch access token, using (in order of priority):
    1. TWITCH_ACCESS_TOKEN env var
    2. Cached token (refreshed if expired)
    3. Full Authorization Code Flow (opens browser)
    """
    # 1. Direct env var shortcut
    env_token = os.environ.get("TWITCH_ACCESS_TOKEN", "").strip()
    if env_token and validate_token(env_token):
        return env_token

    # 2. Cached tokens
    cache = _load_cached_tokens()
    if cache.get("access_token") and validate_token(cache["access_token"]):
        return cache["access_token"]

    if cache.get("refresh_token"):
        print("[auth] Access token expired — refreshing...")
        tokens = refresh_access_token(cache["refresh_token"])
        return tokens["access_token"]

    # 3. Full OAuth flow
    tokens = _authorization_code_flow()
    return tokens["access_token"]
