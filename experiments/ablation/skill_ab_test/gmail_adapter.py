from __future__ import annotations

from typing import Any

from .models import EmailThread


class GmailUnavailableError(RuntimeError):
    pass


def normalize_gmail_thread(payload: dict[str, Any]) -> EmailThread:
    """Normalize an already-fetched thread without connecting to Gmail."""
    normalized = dict(payload)
    normalized.setdefault("source_type", "normalized_input")
    return EmailThread.from_dict(normalized)


def fetch_live_thread(_thread_id: str) -> EmailThread:
    raise GmailUnavailableError(
        "Live Gmail is intentionally disabled for this synthetic-only ablation experiment."
    )
