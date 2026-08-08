from __future__ import annotations

from typing import Any

from .codex_runner import CodexResult, run_codex
from .skill_registry import PROJECT_ROOT


def _taxonomy() -> str:
    return (PROJECT_ROOT / "shared" / "taxonomy.md").read_text(encoding="utf-8")


def classify_email(email: dict[str, Any], model: str | None = None) -> CodexResult:
    return run_codex(
        prompt=(
            "Read input.json and classify its email with the supplied taxonomy. "
            "Return only the JSON fields required by the classification workflow."
        ),
        payload={"email": email, "taxonomy": _taxonomy()},
        skill="email-classifier",
        model=model,
    )


def review_purchase_email(
    email: dict[str, Any],
    classification: Any,
    model: str | None = None,
) -> CodexResult:
    return run_codex(
        prompt=(
            "Read input.json and review the already-classified purchase email. "
            "Return only concise JSON and do not reclassify or take external action."
        ),
        payload={"email": email, "classification": classification},
        skill="purchase-email-review",
        model=model,
    )


def draft_clarification(review: Any, model: str | None = None) -> CodexResult:
    return run_codex(
        prompt=(
            "Read input.json and draft an unsent clarification email using only the "
            "explicit missing-information questions. Return only concise JSON."
        ),
        payload={"review": review},
        skill="clarification-draft",
        model=model,
    )
