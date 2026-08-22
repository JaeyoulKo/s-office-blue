from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import EmailThread


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


@dataclass(frozen=True)
class SyntheticScenario:
    scenario_id: str
    difficulty: str
    title: str
    thread: EmailThread
    expected: dict[str, Any]

    @property
    def label(self) -> str:
        return f"[{self.difficulty_group}] {self.scenario_id} · {self.title}"

    @property
    def difficulty_group(self) -> str:
        normalized = self.difficulty.lower().replace("_", " ").replace("-", " ")
        if normalized == "very hard":
            return "Very Hard"
        if normalized == "hard":
            return "Hard"
        return "Standard"


def load_synthetic_scenarios(fixture_root: Path = FIXTURE_ROOT) -> list[SyntheticScenario]:
    scenarios = [load_synthetic_scenario(path) for path in fixture_root.glob("*.json")]
    group_order = {"Standard": 0, "Hard": 1, "Very Hard": 2}
    return sorted(
        scenarios,
        key=lambda item: (group_order[item.difficulty_group], item.scenario_id),
    )


def load_synthetic_scenario(path: Path) -> SyntheticScenario:
    payload = json.loads(path.read_text(encoding="utf-8"))
    thread_payload = payload.get("thread", payload)
    messages = [_normalize_message(item) for item in thread_payload["messages"]]
    thread = EmailThread.from_dict(
        {
            "thread_id": thread_payload.get("thread_id", messages[0]["thread_id"]),
            "source_type": thread_payload.get("source_type", "test_fixture"),
            "messages": messages,
        }
    )
    first_subject = thread.messages[0].subject
    return SyntheticScenario(
        scenario_id=str(payload.get("scenario_id", path.stem)),
        difficulty=str(payload.get("difficulty", "standard")),
        title=str(payload.get("title", first_subject)),
        thread=thread,
        expected=dict(payload.get("expected", {})),
    )


def _normalize_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept both normalized experiment threads and the original synthetic schema."""
    if "sender" in payload:
        return dict(payload)
    return {
        "message_id": payload["message_id"],
        "thread_id": payload["thread_id"],
        "sender": payload["from"],
        "recipients": payload.get("to", []),
        "cc": payload.get("cc", []),
        "sent_at": payload["date"],
        "subject": payload["subject"],
        "body_text": payload["body"],
        "attachments": payload.get("attachments", []),
        "reference_ids": payload.get("reference_ids", []),
    }
