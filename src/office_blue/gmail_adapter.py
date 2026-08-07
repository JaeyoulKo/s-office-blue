from __future__ import annotations

from typing import Any

from .models import EmailMessage


def message_from_gmail_mcp(data: dict[str, Any]) -> EmailMessage:
    """Normalize a Gmail connector message without persisting OAuth credentials."""
    sender = data.get("sender") or data.get("from") or data.get("from_address")
    recipients = data.get("recipients") or data.get("to") or data.get("to_addresses") or []
    body = data.get("body") or data.get("body_text") or data.get("text") or data.get("snippet")
    normalized = {
        "message_id": data.get("message_id") or data.get("id"),
        "thread_id": data.get("thread_id") or data.get("threadId"),
        "sender": sender,
        "recipients": recipients,
        "subject": data.get("subject"),
        "body": body,
        "received_at": data.get("received_at") or data.get("timestamp") or data.get("date") or "",
        "attachments": data.get("attachments") or [],
    }
    return EmailMessage.from_dict(normalized)
