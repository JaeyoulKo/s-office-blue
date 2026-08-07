from __future__ import annotations

from datetime import datetime
from typing import Protocol

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
    """Boundary implemented only after a real Gmail MCP schema is available."""

    def fetch_thread(self, thread_id: str) -> list[GmailMessagePayload]: ...


class UnavailableGmailGateway:
    def fetch_thread(self, thread_id: str) -> list[GmailMessagePayload]:
        raise GmailUnavailableError(
            "No Gmail MCP message/thread/attachment capability is available in this environment."
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
