from __future__ import annotations

from typing import Any


USER_SUMMARY_FIELDS = (
    "발신자",
    "날짜",
    "Topic",
    "금액",
    "Business Impact",
    "Thread 진행 중 변경된 내용",
    "결정된 내용",
    "Open Item",
)
EXCEL_FIELDS = (
    "발신자",
    "날짜",
    "Topic",
    "금액",
    "통화",
    "Business Impact",
    "Thread 진행 중 변경된 내용",
    "결정된 내용",
    "Open Item",
)
EMPTY_VALUE = "확인되지 않음"
HIDDEN_CHANGE_FIELDS = {"thread_id", "message_id", "승인 상태", "적용 규칙"}


def format_amount(amount: Any, currency: Any) -> str:
    if amount is None:
        return EMPTY_VALUE
    if not isinstance(amount, int) or isinstance(amount, bool):
        return EMPTY_VALUE
    if currency == "KRW":
        return f"{amount:,}원"
    if isinstance(currency, str) and currency:
        return f"{amount:,} {currency}"
    return f"{amount:,}"


def format_summary_field(field: str, result: dict[str, Any]) -> str | list[str]:
    value = result.get(field)
    if field == "금액":
        return format_amount(value, result.get("통화"))
    if field == "Business Impact":
        return _format_business_impact(value)
    if field == "Thread 진행 중 변경된 내용":
        return _format_changes(value)
    if field in ("결정된 내용", "Open Item"):
        return _format_items(value)
    if value is None or value == "":
        return EMPTY_VALUE
    return str(value)


def format_excel_text(field: str, result: dict[str, Any]) -> str:
    value = format_summary_field(field, result)
    if isinstance(value, list):
        return "\n".join(f"• {item}" for item in value) if value else EMPTY_VALUE
    return value


def _format_business_impact(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return _format_items(value)
    items: list[str] = []
    items.extend(str(item) for item in value.get("confirmed", []) if item)
    items.extend(f"확인 필요: {item}" for item in value.get("estimated", []) if item)
    for item in value.get("items", []):
        if not isinstance(item, dict) or not item.get("value"):
            continue
        prefix = "" if item.get("confirmed") is True else "확인 필요: "
        items.append(f"{prefix}{item['value']}")
    return items or [EMPTY_VALUE]


def _format_changes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return _format_items(value)
    items: list[str] = []
    for change in value:
        if not isinstance(change, dict):
            if change:
                items.append(str(change))
            continue
        label = change.get("field")
        if label in HIDDEN_CHANGE_FIELDS:
            continue
        before = _format_scalar(change.get("from"))
        after = _format_scalar(change.get("to"))
        if label:
            items.append(f"{label}: {before} → {after}")
        elif before != EMPTY_VALUE or after != EMPTY_VALUE:
            items.append(f"{before} → {after}")
    return items or [EMPTY_VALUE]


def _format_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return [str(value)] if value not in (None, "") else [EMPTY_VALUE]
    items = [str(item) for item in value if item not in (None, "")]
    return items or [EMPTY_VALUE]


def _format_scalar(value: Any) -> str:
    if value is None or value == "":
        return EMPTY_VALUE
    if isinstance(value, bool):
        return "예" if value else "확인 필요"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)
