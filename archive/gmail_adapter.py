from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .models import Attachment, EmailMessage, EmailThread, UNKNOWN


class GmailUnavailableError(RuntimeError):
    pass


class GmailAttachmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str = UNKNOWN
    file_name: str
    mime_type: str = UNKNOWN
    content_text: str = UNKNOWN
    access_status: str = "unverified"


class GmailMessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    thread_id: str
    subject: str = UNKNOWN
    sender: str = UNKNOWN
    recipients: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    sent_at: datetime
    body_text: str = UNKNOWN
    attachments: list[GmailAttachmentPayload] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)


class GmailGateway(Protocol):
    """Read-only boundary that supplies one complete Gmail thread."""

    def fetch_thread(self, thread_id: str) -> list[GmailMessagePayload]: ...


class UnavailableGmailGateway:
    def fetch_thread(self, thread_id: str) -> list[GmailMessagePayload]:
        raise GmailUnavailableError(
            "No Gmail MCP message/thread/attachment capability is available in this environment."
        )


class CodexGmailGateway:
    """Use the team's existing read-only Codex Gmail bridge for Archive threads."""

    def __init__(
        self,
        thread_fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        if thread_fetcher is None:
            from office_blue.codex_gmail_bridge import fetch_gmail_thread

            thread_fetcher = fetch_gmail_thread
        self.thread_fetcher = thread_fetcher

    def fetch_thread(self, thread_id: str) -> list[GmailMessagePayload]:
        raw_messages = self.thread_fetcher(thread_id)
        if not raw_messages:
            raise GmailUnavailableError("The selected Gmail thread contains no accessible messages.")
        payloads = [self._payload(item) for item in raw_messages]
        if any(payload.thread_id != thread_id for payload in payloads):
            raise ValueError("Gmail thread result contains a different thread ID.")
        return payloads

    @staticmethod
    def _payload(data: dict[str, Any]) -> GmailMessagePayload:
        message_id = data.get("message_id") or data.get("id")
        thread_id = data.get("thread_id") or data.get("threadId")
        if not str(message_id or "").strip() or not str(thread_id or "").strip():
            raise ValueError("Gmail message ID and thread ID are required.")
        received_at = data.get("received_at") or data.get("timestamp") or data.get("date")
        if not str(received_at or "").strip():
            raise ValueError("Gmail message timestamp is unavailable; it cannot be guessed.")
        recipients = data.get("recipients") or data.get("to") or []
        if isinstance(recipients, str):
            recipients = [recipients]
        attachments = data.get("attachments") or []
        return GmailMessagePayload(
            message_id=str(message_id),
            thread_id=str(thread_id),
            subject=str(data.get("subject") or UNKNOWN),
            sender=str(data.get("sender") or data.get("from") or UNKNOWN),
            recipients=[str(value) for value in recipients],
            sent_at=received_at,
            body_text=str(data.get("body") or data.get("body_text") or UNKNOWN),
            attachments=[
                GmailAttachmentPayload(file_name=str(file_name))
                for file_name in attachments
                if str(file_name).strip()
            ],
        )


class GmailAdapter:
    def __init__(self, gateway: GmailGateway) -> None:
        self.gateway = gateway

    def fetch_normalized_thread(self, thread_id: str) -> EmailThread:
        payloads = self.gateway.fetch_thread(thread_id)
        messages = [self._normalize_message(payload) for payload in payloads]
        return EmailThread(thread_id=thread_id, messages=messages, source_type="gmail_mcp")

    @staticmethod
    def _normalize_message(payload: GmailMessagePayload) -> EmailMessage:
        attachments = [
            Attachment(
                attachment_id=item.attachment_id,
                file_name=item.file_name,
                file_type=_file_type(item.file_name, item.mime_type),
                mime_type=item.mime_type,
                access_status=(
                    "analyzed" if item.access_status == "analyzed" and item.content_text != UNKNOWN else "unverified"
                ),
                summary=UNKNOWN,
                extracted_text=item.content_text,
                source_message_id=payload.message_id,
            )
            for item in payload.attachments
        ]
        return EmailMessage(
            message_id=payload.message_id,
            thread_id=payload.thread_id,
            subject=payload.subject,
            sender=payload.sender,
            recipients=payload.recipients,
            cc=payload.cc,
            sent_at=payload.sent_at,
            body_text=payload.body_text,
            attachments=attachments,
            reference_ids=payload.reference_ids,
        )


def _file_type(file_name: str, mime_type: str) -> str:
    lowered = file_name.lower()
    if mime_type == "application/pdf" or lowered.endswith(".pdf"):
        return "pdf"
    if "spreadsheet" in mime_type or lowered.endswith((".xlsx", ".xls", ".csv")):
        return "spreadsheet"
    if mime_type.startswith("image/") or lowered.endswith((".png", ".jpg", ".jpeg", ".gif")):
        return "image"
    if "document" in mime_type or lowered.endswith((".doc", ".docx", ".txt")):
        return "document"
    return "other"
