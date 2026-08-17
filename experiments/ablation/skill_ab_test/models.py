from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Attachment:
    attachment_id: str
    file_name: str
    file_type: str = "unknown"
    mime_type: str = "application/octet-stream"
    access_status: str = "unverified"
    summary: str = "unknown"
    extracted_text: str = "unknown"
    source_message_id: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Attachment":
        return cls(**{key: payload[key] for key in cls.__dataclass_fields__ if key in payload})


@dataclass(frozen=True)
class EmailMessage:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipients: list[str]
    cc: list[str]
    sent_at: str
    body_text: str
    attachments: list[Attachment] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        datetime.fromisoformat(self.sent_at.replace("Z", "+00:00"))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EmailMessage":
        values = dict(payload)
        values["attachments"] = [Attachment.from_dict(item) for item in payload.get("attachments", [])]
        return cls(**values)


@dataclass(frozen=True)
class EmailThread:
    thread_id: str
    messages: list[EmailMessage]
    source_type: str = "test_fixture"

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("Email thread must contain at least one message.")
        if any(message.thread_id != self.thread_id for message in self.messages):
            raise ValueError("Every message must use the containing thread_id.")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EmailThread":
        return cls(
            thread_id=str(payload["thread_id"]),
            messages=[EmailMessage.from_dict(item) for item in payload["messages"]],
            source_type=str(payload.get("source_type", "test_fixture")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
