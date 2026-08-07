from __future__ import annotations

from typing import Any

from .models import EmailMessage


def message_from_ariba_sample(data: dict[str, Any]) -> EmailMessage:
    pr_number = str(data.get("pr_number") or "unknown")
    requester = str(data.get("requester") or "unknown")
    cost = data.get("cost_breakdown") or {}
    effects = data.get("expected_effects") or {}
    body_lines = [
        f"요청자: {requester}",
        f"구매 유형: {data.get('type') or 'unknown'}",
        f"품목/서비스 및 목적: {data.get('description') or 'unknown'}",
        f"공급사: {data.get('vendor') or 'unknown'}",
        f"금액: {data.get('total_amount') or 'unknown'}",
        f"최근 의견: {data.get('recent_comments') or 'unknown'}",
        f"비용 산출 근거: {cost.get('details') if cost.get('has_data') else 'unknown'}",
        f"기대효과: {effects.get('details') if effects.get('has_data') else 'unknown'}",
    ]
    return EmailMessage.from_dict(
        {
            "message_id": f"ariba-sample-{data.get('id', pr_number)}",
            "thread_id": f"ariba-{pr_number}",
            "sender": requester,
            "recipients": [],
            "subject": data.get("email_subject") or f"Ariba request {pr_number}",
            "body": "\n".join(body_lines),
            "attachments": [],
        }
    )


def is_ariba_sample_list(data: Any) -> bool:
    return isinstance(data, list) and all(
        isinstance(item, dict) and "pr_number" in item and "email_subject" in item for item in data
    )
