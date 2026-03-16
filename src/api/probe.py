"""
Network probe: intercepts all XHR/fetch calls made by the Angular app.

Useful to inspect the real JSON payload for any given endpoint, especially
when the site is updated and field names change.

Usage:
    python -m src.api.probe 49
    python -m src.api.probe 49 expert

Requires: pip install playwright && python -m playwright install chromium
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://latabledessavoirs.fr")
API_BASE_URL = "https://api.latabledessavoirs.fr"


def run_probe(quiz_id: int = 49, quiz_type: str = "abordable"):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium")
        sys.exit(1)

    intercepted: list[dict] = []

    def on_response(response):
        url = response.url
        if API_BASE_URL in url:
            try:
                body = response.json()
            except Exception:
                body = response.text()[:500]
            record = {"method": response.request.method, "url": url, "status": response.status, "body": body}
            intercepted.append(record)
            print(f"\n[probe] {response.request.method} {response.status} {url}")
            print(json.dumps(body, indent=2, ensure_ascii=False)[:1000])

    from pathlib import Path
    profile_dir = Path(".playwright_profile")
    profile_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.on("response", on_response)

        url = f"{SITE_BASE_URL}/{quiz_type}/{quiz_id}"
        print(f"[probe] Navigating to {url}")
        print("[probe] Log in with Twitch if prompted. Press Ctrl+C when done.\n")
        page.goto(url, wait_until="networkidle")

        try:
            page.wait_for_timeout(300_000)  # wait 5 minutes
        except KeyboardInterrupt:
            pass

        context.close()

    print("\n─── Summary of intercepted API calls ───")
    for r in intercepted:
        print(f"  {r['method']} {r['status']}  {r['url']}")


if __name__ == "__main__":
    quiz_id = int(sys.argv[1]) if len(sys.argv) > 1 else 49
    quiz_type = sys.argv[2] if len(sys.argv) > 2 else "abordable"
    run_probe(quiz_id, quiz_type)



if __name__ == "__main__":
    quiz_id = int(sys.argv[1]) if len(sys.argv) > 1 else 49
    quiz_type = sys.argv[2] if len(sys.argv) > 2 else "abordable"
    run_probe(quiz_id, quiz_type)
