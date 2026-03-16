"""
La Table des Savoirs — Quiz Fetcher
====================================

Fetch questions and correct answers for a given quiz number.

Usage
-----
# Login via browser (first run opens Chromium for Twitch login):
    python -m src.main 49

# Fetch a day range:
    python -m src.main --day-range 48:60 --type facile

# Specify quiz type:
    python -m src.main 49 --type expert

# Save output to a specific JSON file:
    python -m src.main 49 --output output/quiz_49.json

# Fetch both difficulties in one run:
    python -m src.main 49 --all

# Fetch both difficulties for a day range:
    python -m src.main --day-range 48:60 --all

# Clear the cached site JWT (forces re-login):
    rm .site_token_cache.json

# Probe API responses from a browser session (to debug / discover routes):
    python -m src.api.probe 49
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.auth.site_auth import get_site_jwt
from src.api.client import QuizClient


def _normalize_quiz_type_for_cli(quiz_type: str) -> str:
    mapping = {
        "abordable": "facile",
        "expert": "difficile",
        "facile": "facile",
        "difficile": "difficile",
    }
    return mapping[quiz_type]


def _save_quiz_json(quiz, output_path: str) -> None:
    data = {
        "id": quiz.id,
        "type": quiz.quiz_type,
        "date": quiz.date,
        "questions": [
            {
                "position": q.position,
                "theme": q.theme,
                "text": q.text,
                "correct_answer": q.correct_answer,
                "difficulty": q.difficulty,
                "time_limit": q.time_limit,
            }
            for q in quiz.questions
        ],
    }
    Path(output_path).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\n[main] Results saved to {output_path}")


def _parse_day_range(raw: str) -> list[int]:
    """Parse START:END into an inclusive list of day numbers."""
    try:
        start_raw, end_raw = raw.split(":", 1)
        start = int(start_raw)
        end = int(end_raw)
    except Exception as exc:
        raise ValueError("--day-range must be in format START:END, e.g. 48:60") from exc

    if start <= 0 or end <= 0:
        raise ValueError("Day numbers must be positive integers")
    if end < start:
        raise ValueError("--day-range END must be >= START")
    return list(range(start, end + 1))


def _run_single_fetch(client: QuizClient, quiz_id: int, normalized_type: str, output_dir: Path) -> None:
    print(f"[main] Fetching quiz #{quiz_id} ({normalized_type})...")
    quiz = client.fetch_quiz(quiz_id, quiz_type=normalized_type)
    print("\n" + quiz.summary())
    print(f"[main] Fetched {len(quiz.questions)} questions for quiz #{quiz.id} ({quiz.quiz_type})")
    output_path = str(output_dir / f"quiz_{quiz_id}_{normalized_type}.json")
    _save_quiz_json(quiz, output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch questions & answers from latabledessavoirs.fr"
    )
    parser.add_argument(
        "quiz_id",
        type=int,
        nargs="?",
        help="Quiz day number to fetch (e.g. 49)",
    )
    parser.add_argument(
        "--day-range",
        dest="day_range",
        default=None,
        help="Inclusive day range START:END (e.g. 48:60)",
    )
    parser.add_argument(
        "--type",
        dest="quiz_type",
        choices=["abordable", "expert", "facile", "difficile"],
        default="abordable",
        help="Quiz type (aliases: abordable=facile, expert=difficile)",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        default=None,
        help="Save results to this JSON file (single-day mode only)",
    )
    parser.add_argument(
        "--all",
        dest="fetch_all",
        action="store_true",
        help="Fetch both difficulties (facile + difficile) for the same day",
    )
    args = parser.parse_args()

    if args.quiz_id is None and args.day_range is None:
        parser.error("Provide either quiz_id or --day-range START:END")

    if args.quiz_id is not None and args.day_range is not None:
        parser.error("Use either quiz_id or --day-range, not both")

    if args.day_range is not None and args.output_path is not None:
        parser.error("--output is only supported with a single quiz_id")

    # ── 1. Get site JWT (browser login if not cached) ──────────────────────────
    site_jwt = get_site_jwt()

    # ── 2. Fetch quiz ──────────────────────────────────────────────────────────
    client = QuizClient(site_jwt)
    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.day_range is not None:
        day_numbers = _parse_day_range(args.day_range)
        print(f"[main] Fetching day range {day_numbers[0]}..{day_numbers[-1]}")
        types = ["facile", "difficile"] if args.fetch_all else [_normalize_quiz_type_for_cli(args.quiz_type)]
        for day in day_numbers:
            for normalized_type in types:
                _run_single_fetch(client, day, normalized_type, output_dir)
        return

    if args.fetch_all:
        for normalized_type in ["facile", "difficile"]:
            _run_single_fetch(client, args.quiz_id, normalized_type, output_dir)
        return

    normalized_type = _normalize_quiz_type_for_cli(args.quiz_type)
    print(f"[main] Fetching quiz #{args.quiz_id} ({normalized_type})...")
    quiz = client.fetch_quiz(args.quiz_id, quiz_type=normalized_type)

    # ── 3. Display ─────────────────────────────────────────────────────────────
    print("\n" + quiz.summary())
    print(f"[main] Fetched {len(quiz.questions)} questions for quiz #{quiz.id} ({quiz.quiz_type})")

    # ── 4. Save JSON ───────────────────────────────────────────────────────────
    output_path = args.output_path
    if output_path is None:
        output_path = str(output_dir / f"quiz_{args.quiz_id}_{normalized_type}.json")

    _save_quiz_json(quiz, output_path)


if __name__ == "__main__":
    main()

