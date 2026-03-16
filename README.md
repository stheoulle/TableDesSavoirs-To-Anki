# Table des Savoirs — Quiz Fetcher

Fetch questions and **correct answers** from [latabledessavoirs.fr](https://latabledessavoirs.fr) for any quiz number.

---

## How it works

The site is an Angular SPA backed by a real JSON API at `https://api.latabledessavoirs.fr`.
Authentication uses the **site's own Twitch OAuth app** — not yours. The flow:

1. Playwright opens a Chromium browser pointed at the site.
2. The user logs in once via the Twitch popup (credentials are saved in a persistent browser profile at `.playwright_profile/`).
3. The resulting JWT (`ltds-auth`) is extracted from `localStorage` and cached in `.site_token_cache.json`.
4. All subsequent runs reuse the cached JWT (no re-login until it expires).

---

## Project Structure

```bash
TableSavoir/
├── .env                       ← config (never commit this)
├── .env.example               ← config template
├── .gitignore
├── requirements.txt           ← httpx, python-dotenv, playwright
├── README.md
├── output/                    ← saved JSON results (gitignored)
├── .site_token_cache.json     ← cached site JWT (gitignored, created on first login)
├── .playwright_profile/       ← Playwright browser session (gitignored, reuse across runs)
└── src/
    ├── main.py                ← entry point
    ├── auth/
    │   ├── twitch.py          ← Twitch OAuth helpers (for reference)
    │   └── site_auth.py       ← Playwright login → extracts & caches ltds-auth JWT
    ├── api/
    │   ├── client.py          ← httpx client calling api.latabledessavoirs.fr
    │   └── probe.py           ← Playwright probe to intercept live API calls
    └── models/
        └── quiz.py            ← Quiz / Question dataclasses
```

---

## Setup

```bash
# 1. Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browser
python -m playwright install chromium

# 4. Configure (optional — defaults work out of the box)
cp .env.example .env
```

No Twitch developer account needed. The first run opens a browser for you to log in.

---

## Usage

### Fetch a quiz (opens browser for first-time login)

```bash
python -m src.main 49
```

### Specify quiz type

```bash
python -m src.main 49 --type expert
```

### Save to a specific path

```bash
python -m src.main 49 --output output/quiz_49.json
```

### Fetch both difficulties at once

```bash
python -m src.main 49 --all
```

### Fetch a day range

```bash
python -m src.main --day-range 48:60 --type facile
```

### Fetch a day range for both difficulties

```bash
python -m src.main --day-range 48:60 --all
```

### Skip the browser: paste your JWT directly

Open Chrome DevTools on the site after logging in:
**Application → Local Storage → `https://latabledessavoirs.fr` → `ltds-auth`**

Copy the value and set it in `.env`:

```bash
SITE_JWT={"token":"eyJ...","expiresAt":1234567890000}
```

### Force re-login (if JWT expired)

```bash
rm .site_token_cache.json
python -m src.main 49
```

---

## Output format

```json
{
  "id": 49,
  "type": "abordable",
  "date": "2026-03-15T11:00:00.000Z",
  "questions": [
    {
      "position": 1,
      "theme": "Histoire",
      "text": "Quelle bataille a eu lieu en 1815 ?",
      "correct_answer": "Waterloo",
      "difficulty": null,
      "time_limit": null
    }
  ]
}
```

---

## Notes

- Per the site's rules, use of this tool for **live play assistance** is against their fair-play policy. Intended for post-game review only.
- The `.playwright_profile/` directory saves Twitch login cookies — you only need to log in once until the Twitch session expires.
