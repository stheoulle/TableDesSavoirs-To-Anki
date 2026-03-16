"""
Site authentication for latabledessavoirs.fr.

The site uses its own Twitch OAuth application (client_id: jjvu3jl5hfptlfsp0n53ldrbio3lj7).
After OAuth the backend returns a JWT that is stored in localStorage under the
key "ltds-auth" as: { "token": "<jwt>", "expiresAt": <epoch_ms> }

Authentication flow:
  1. If SITE_JWT env var is set and not expired  →  use it directly (fastest)
  2. If .site_token_cache.json exists and not expired  →  use cached JWT
  3. Playwright browser login:
       a. Open site in a persistent Chromium context (Twitch login state is
          preserved across runs in .playwright_profile/)
       b. If already logged in, extract JWT from localStorage and return
       c. Otherwise click the login button, handle the Twitch OAuth popup,
          wait for the JWT to appear in localStorage, then cache it

The Playwright profile directory ensures that after the user logs in once
with their Twitch credentials in the browser, subsequent runs are instant
(the Twitch session cookie is saved).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://latabledessavoirs.fr")
API_BASE_URL = "https://api.latabledessavoirs.fr"

SITE_TOKEN_CACHE = Path(".site_token_cache.json")
PLAYWRIGHT_PROFILE = Path(".playwright_profile")
LOCALSTORAGE_KEY = "ltds-auth"


# ─── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cached_site_token() -> str | None:
    """Return a valid cached site JWT, or None if missing/expired."""
    # 1. Env var override
    env_jwt = os.environ.get("SITE_JWT", "").strip()
    if env_jwt:
        data = _decode_ltds_auth(env_jwt)
        if data and data.get("expiresAt", 0) > _now_ms():
            return data["token"]

    # 2. File cache
    if SITE_TOKEN_CACHE.exists():
        try:
            cached = json.loads(SITE_TOKEN_CACHE.read_text())
            if cached.get("expiresAt", 0) > _now_ms():
                return cached["token"]
        except Exception:
            pass
    return None


def _save_site_token(ltds_auth: dict) -> None:
    """Persist the ltds-auth dict to disk."""
    SITE_TOKEN_CACHE.write_text(json.dumps(ltds_auth, indent=2))
    SITE_TOKEN_CACHE.chmod(0o600)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _decode_ltds_auth(raw: str) -> dict | None:
    """Parse raw localStorage value (JSON string or already a dict)."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


# ─── Playwright login ──────────────────────────────────────────────────────────

def _playwright_get_jwt() -> str:
    """
    Open a persistent Playwright browser session, log into the site via
    Twitch OAuth if needed, and return the site JWT.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    except ImportError:
        raise ImportError(
            "Playwright is required for browser-based login.\n"
            "Install it with: pip install playwright && python -m playwright install chromium"
        )

    PLAYWRIGHT_PROFILE.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PLAYWRIGHT_PROFILE),
            headless=False,    # show browser so user can log in
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )

        page = context.new_page()
        print(f"[site_auth] Opening {SITE_BASE_URL} ...")
        page.goto(SITE_BASE_URL, wait_until="networkidle", timeout=30_000)

        # ── Check if already logged in (JWT present in localStorage) ──────────
        raw = page.evaluate(f"() => localStorage.getItem('{LOCALSTORAGE_KEY}')")
        auth = _decode_ltds_auth(raw) if raw else None

        if auth and auth.get("expiresAt", 0) > _now_ms():
            print("[site_auth] Already logged in — reusing localStorage JWT.")
            _save_site_token(auth)
            context.close()
            return auth["token"]

        # ── Trigger login ──────────────────────────────────────────────────────
        print("[site_auth] Not logged in — triggering Twitch OAuth...")
        print("[site_auth] Please log in with Twitch in the browser window.")

        # Click the first button / link that looks like a login trigger
        try:
            # Try common selectors used by the site
            for selector in [
                "button:has-text('Connexion')",
                "button:has-text('Se connecter')",
                "button:has-text('Login')",
                "[data-testid='login-button']",
                "a:has-text('Connexion')",
            ]:
                if page.locator(selector).count() > 0:
                    page.click(selector)
                    break
        except Exception:
            pass  # user can click manually

        # Wait up to 3 minutes for the JWT to appear in localStorage
        print("[site_auth] Waiting for authentication (up to 3 minutes)...")
        deadline = time.time() + 180

        while time.time() < deadline:
            page.wait_for_timeout(1_500)
            raw = page.evaluate(f"() => localStorage.getItem('{LOCALSTORAGE_KEY}')")
            auth = _decode_ltds_auth(raw) if raw else None
            if auth and auth.get("token") and auth.get("expiresAt", 0) > _now_ms():
                print("[site_auth] JWT obtained from localStorage!")
                _save_site_token(auth)
                context.close()
                return auth["token"]

        context.close()
        raise RuntimeError(
            "Timed out waiting for Twitch login. Please try again and complete "
            "the login in the browser window within 3 minutes."
        )


# ─── Public API ────────────────────────────────────────────────────────────────

def get_site_jwt() -> str:
    """
    Return a valid site JWT, obtaining it via browser login if necessary.

    Returns the JWT string to use as: Authorization: Bearer <jwt>
    """
    cached = _load_cached_site_token()
    if cached:
        print("[site_auth] Using cached site JWT.")
        return cached

    return _playwright_get_jwt()

