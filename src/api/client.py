"""
API client for latabledessavoirs.fr.

Real API base: https://api.latabledessavoirs.fr
Authentication: Authorization: Bearer <site_jwt>

Discovered endpoints (from the Angular JS bundle):
  GET  /info                            → app state (unauthenticated)
  GET  /me                              → current user profile
  GET  /game?day=N                      → game status for day N
    GET  /game/{difficulty}               → player state for current day (facile|difficile)
    GET  /game/{difficulty}/{N}           → player state for a given day + questions/answers
    POST /game/{difficulty}/start/{q}     → start question q  { dayNumber: N }
    POST /game/{difficulty}/answer        → submit answer
    POST /game/{difficulty}/review        → place bonus tokens + finalize
"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

from src.models.quiz import Question, Quiz

load_dotenv()

API_BASE = "https://api.latabledessavoirs.fr"


def _normalize_quiz_type(quiz_type: str) -> str:
    """Map CLI aliases to API difficulty values."""
    mapping = {
        "abordable": "facile",
        "expert": "difficile",
        "facile": "facile",
        "difficile": "difficile",
    }
    if quiz_type not in mapping:
        raise ValueError(
            f"Unknown quiz_type '{quiz_type}'. "
            "Use one of: abordable, expert, facile, difficile."
        )
    return mapping[quiz_type]


def _make_client(site_jwt: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={
            "Authorization": f"Bearer {site_jwt}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://latabledessavoirs.fr",
            "Referer": "https://latabledessavoirs.fr/",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        },
        follow_redirects=True,
        timeout=15.0,
    )


def _parse_quiz(data: dict, quiz_id: int, quiz_type: str) -> Quiz:
    """
    Parse a raw API JSON response into a Quiz object.

        The /game/{difficulty}/{N} endpoint returns something like:
    {
      "day": {
        "dayNumber": 49,
        "date": "...",
        "questions": [
                    { "order": 1, "text": "...", "validAnswers": [...], "theme": "...", ... }
        ]
      },
            "playerGame": { ... }
    }
    """
    # Unwrap nested structure
    day = data.get("day") or data
    questions_raw = (
        day.get("questions")
        or data.get("questions")
        or []
    )

    questions = []
    for raw in questions_raw:
        valid_answers = raw.get("validAnswers") or []
        if isinstance(valid_answers, list):
            correct_answer = " | ".join(str(answer) for answer in valid_answers)
        else:
            correct_answer = str(valid_answers)

        if not correct_answer:
            correct_answer = (
                raw.get("answer")
                or raw.get("correct_answer")
                or raw.get("correctAnswer")
                or ""
            )

        q = Question(
            id=raw.get("_id") or raw.get("id") or raw.get("order", 0),
            position=raw.get("order") or raw.get("position") or raw.get("questionNumber", 0),
            text=raw.get("text") or raw.get("question") or raw.get("label", ""),
            correct_answer=correct_answer,
            theme=raw.get("theme") or raw.get("category"),
            difficulty=raw.get("difficulty") or raw.get("difficulte"),
            time_limit=raw.get("initialTimerInMs") or raw.get("timeLimit") or raw.get("time_limit") or raw.get("timer"),
        )
        questions.append(q)

    # Sort by position just in case
    questions.sort(key=lambda q: q.position)

    return Quiz(
        id=quiz_id,
        quiz_type=quiz_type,
        date=day.get("date") or day.get("createdAt") or data.get("date"),
        questions=questions,
    )


class QuizClient:
    """Authenticated client for fetching quiz data from the real JSON API."""

    def __init__(self, site_jwt: str):
        self.client = _make_client(site_jwt)

    def get_profile(self) -> dict:
        """Fetch the current user's profile."""
        r = self.client.get("/me")
        r.raise_for_status()
        return r.json()

    def fetch_quiz(
        self,
        quiz_id: int,
        quiz_type: str = "abordable",
    ) -> Quiz:
        """
        Fetch questions and correct answers for a quiz day.

        Strategy (in order):
          1. GET /game/{difficulty}/{quiz_id}    → full day with questions + validAnswers
          2. GET /game/{difficulty}?day={quiz_id} (some deployments)
          3. GET /game?day={quiz_id}             → status only (answer masks)
        """
        difficulty = _normalize_quiz_type(quiz_type)

        attempts = [
            f"/game/{difficulty}/{quiz_id}",
            f"/game/{difficulty}?day={quiz_id}",
            f"/game?day={quiz_id}",
        ]

        last_status = None
        for url in attempts:
            r = self.client.get(url)
            last_status = r.status_code

            if r.status_code == 200:
                data = r.json()
                print(f"[api] Got quiz data from {url}")

                parsed = _parse_quiz(data, quiz_id, difficulty)
                if parsed.questions:
                    return parsed
                # /game?day=N returns status masks only; continue trying routes
                continue

            elif r.status_code == 401:
                raise PermissionError(
                    "401 Unauthorized — the site JWT may be expired.\n"
                    "Delete .site_token_cache.json and run again to re-authenticate."
                )
            elif r.status_code == 403:
                raise PermissionError(
                    f"403 Forbidden on {url}.\n"
                    "You may need a Twitch subscription or Expert membership to "
                    "access this quiz type."
                )

        raise RuntimeError(
            f"Could not retrieve questions/answers for quiz #{quiz_id} (last HTTP status: {last_status}).\n"
            f"Tried: {attempts}"
        )

