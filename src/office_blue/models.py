from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmailMessage:
    message_id: str
    thread_id: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
    received_at: str = ""
    attachments: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmailMessage":
        required = ("message_id", "sender", "subject", "body")
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Required email fields are empty: {', '.join(missing)}")
        recipients = data.get("recipients", [])
        attachments = data.get("attachments", [])
        if isinstance(recipients, str):
            recipients = [recipients]
        if isinstance(attachments, str):
            attachments = [attachments]
        return cls(
            message_id=str(data["message_id"]),
            thread_id=str(data.get("thread_id") or data["message_id"]),
            sender=str(data["sender"]),
            recipients=[str(value) for value in recipients],
            subject=str(data["subject"]),
            body=str(data["body"]),
            received_at=str(data.get("received_at", "")),
            attachments=[str(value) for value in attachments],
        )


@dataclass(frozen=True)
class MissingField:
    field: str
    reason: str
    question: str


@dataclass(frozen=True)
class ReplyDraft:
    to: str
    subject: str
    body: str


@dataclass(frozen=True)
class ReviewResult:
    message_id: str
    thread_id: str
    classification: str
    status: str
    workflow_state: str
    confirmed_facts: dict[str, str]
    missing_fields: list[MissingField]
    needs_user_confirmation: list[str]
    reply_draft: ReplyDraft | None
    source: str = "normalized Gmail MCP result"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

