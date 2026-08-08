from __future__ import annotations

from typing import Any

from .codex_runner import CodexResult, run_codex
from .skill_registry import PROJECT_ROOT


def _taxonomy() -> str:
    return (PROJECT_ROOT / "shared" / "taxonomy.md").read_text(encoding="utf-8")


def classify_email(email: dict[str, Any], model: str | None = None) -> CodexResult:
    return run_codex(
        prompt=(
            "input.json의 이메일을 제공된 국문 taxonomy로 분류하고 "
            "분류 근거와 다음 단계를 JSON으로 반환하세요."
        ),
        payload={"email": email, "taxonomy": _taxonomy()},
        skill="email-classifier",
        model=model,
    )


def review_purchase_email(
    email: dict[str, Any], classification: Any, model: str | None = None
) -> CodexResult:
    return run_codex(
        prompt=(
            "input.json의 구매·승인·계약 이메일을 검토하세요. 필요한 경우 Skill의 국문 "
            "템플릿으로 회신 초안을 포함하고 외부 작업은 하지 마세요."
        ),
        payload={"email": email, "classification": classification},
        skill="purchase-email-review",
        model=model,
    )


def review_discussion_email(
    email: dict[str, Any], classification: Any, model: str | None = None
) -> CodexResult:
    return run_codex(
        prompt=(
            "input.json의 논의·질의 이메일과 스레드를 검토하세요. 결정, 미결 사항, 담당자, "
            "기한을 구분하고 필요한 경우 국문 회신 초안을 포함하세요."
        ),
        payload={"email": email, "classification": classification},
        skill="discussion-email-review",
        model=model,
    )
