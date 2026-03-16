import json
import csv
import argparse
from pathlib import Path


def first_answer(correct_answer: str) -> str:
    if not isinstance(correct_answer, str):
        return ""
    return correct_answer.split("|", 1)[0].strip()


def main():
    parser = argparse.ArgumentParser(description="Convert quiz JSON files to Anki TSV.")
    parser.add_argument(
        "--input-dir",
        default="output",
        help="Directory containing quiz JSON files (default: output)",
    )
    parser.add_argument(
        "--output",
        default="anki_cards.tsv",
        help="Output TSV file for Anki import (default: anki_cards.tsv)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    files = sorted(input_dir.glob("*.json"))

    rows = []
    for file_path in files:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for q in data.get("questions", []):
            front = str(q.get("text", "")).strip()
            back = first_answer(q.get("correct_answer", ""))
            if front and back:
                rows.append([front, back])

    with Path(args.output).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        writer.writerows(rows)

    print(f"Created {args.output} with {len(rows)} cards.")


if __name__ == "__main__":
    main()