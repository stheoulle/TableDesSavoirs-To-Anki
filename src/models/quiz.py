"""
Data models for quiz responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Question:
    id: int
    position: int                  # 1-based position in the quiz
    text: str                      # The question text
    correct_answer: str            # The accepted correct answer
    theme: Optional[str] = None    # e.g. "Histoire", "Sciences", ...
    difficulty: Optional[int] = None   # 1–5 if available
    time_limit: Optional[int] = None   # seconds

    def display(self) -> str:
        parts = [f"Q{self.position}"]
        if self.theme:
            parts.append(f"[{self.theme}]")
        parts.append(self.text)
        return " ".join(parts)


@dataclass
class Quiz:
    id: int
    quiz_type: str                 # "abordable" or "expert"
    date: Optional[str] = None     # ISO date string
    questions: List[Question] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Quiz #{self.id}  ({self.quiz_type.upper()})  {self.date or ''}",
            "─" * 60,
        ]
        for q in self.questions:
            lines.append(f"  {q.display()}")
            lines.append(f"  → {q.correct_answer}")
            lines.append("")
        return "\n".join(lines)
