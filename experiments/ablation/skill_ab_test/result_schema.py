from __future__ import annotations

import json
import re
from typing import Any


RESULT_FIELDS = (
    "thread_id",
    "발신자",
    "날짜",
    "Topic",
    "금액",
    "통화",
    "Business Impact",
    "Thread 진행 중 변경된 내용",
    "결정된 내용",
    "Open Item",
    "승인 상태",
    "적용 규칙",
)
APPROVAL_STATUSES = (
    "APPROVED",
    "REAPPROVAL_REQUIRED",
    "PENDING",
    "REJECTED",
    "NOT_APPLICABLE",
    "UNKNOWN",
)
COMPLEX_FIELDS = (
    "Business Impact",
    "Thread 진행 중 변경된 내용",
    "결정된 내용",
    "Open Item",
    "적용 규칙",
)


def output_schema() -> dict[str, Any]:
    return {
        "thread_id": "string: input email_thread.thread_id를 그대로 기록",
        "발신자": "string: 최근 메시지 발신자",
        "날짜": "string: YYYY-MM-DD 형식의 최근 메시지 날짜",
        "Topic": "string: 핵심 안건 한 문장",
        "금액": "integer 또는 null: 최신 유효 금액의 최소 통화 단위",
        "통화": "string 또는 null: ISO 4217 통화 코드",
        "Business Impact": {"confirmed": ["string"], "estimated": ["string"]},
        "Thread 진행 중 변경된 내용": [
            {"field": "string", "from": "JSON scalar 또는 null", "to": "JSON scalar 또는 null"}
        ],
        "결정된 내용": ["string"],
        "Open Item": ["string"],
        "승인 상태": f"string enum: {' | '.join(APPROVAL_STATUSES)} 중 하나",
        "적용 규칙": ["string: 확인된 company rule ID; 규칙이 제공되지 않았으면 빈 배열"],
    }


def validate_result(payload: Any, expected_thread_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or tuple(payload) != RESULT_FIELDS:
        raise ValueError("result fields or field order do not match the A/B schema")
    if payload["thread_id"] != expected_thread_id:
        raise ValueError("result thread_id does not match the input thread")
    for field in ("thread_id", "발신자", "날짜", "Topic"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["날짜"]):
        raise ValueError("날짜 must use YYYY-MM-DD")
    amount = payload["금액"]
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or amount < 0):
        raise ValueError("금액 must be a non-negative integer or null")
    currency = payload["통화"]
    if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
        raise ValueError("통화 must be an ISO-style uppercase code or null")
    impact = payload["Business Impact"]
    if not isinstance(impact, dict) or tuple(impact) != ("confirmed", "estimated"):
        raise ValueError("Business Impact must contain confirmed and estimated lists")
    _validate_string_list(impact["confirmed"], "Business Impact.confirmed")
    _validate_string_list(impact["estimated"], "Business Impact.estimated")
    changes = payload["Thread 진행 중 변경된 내용"]
    if not isinstance(changes, list):
        raise ValueError("Thread 진행 중 변경된 내용 must be a list")
    for change in changes:
        if not isinstance(change, dict) or tuple(change) != ("field", "from", "to"):
            raise ValueError("each change must contain field, from, and to in order")
        if not isinstance(change["field"], str) or not change["field"].strip():
            raise ValueError("change field must be a non-empty string")
        for key in ("from", "to"):
            if isinstance(change[key], (dict, list)):
                raise ValueError(f"change {key} must be a JSON scalar or null")
    _validate_string_list(payload["결정된 내용"], "결정된 내용")
    _validate_string_list(payload["Open Item"], "Open Item")
    if payload["승인 상태"] not in APPROVAL_STATUSES:
        raise ValueError("승인 상태 is not an allowed enum")
    rules = payload["적용 규칙"]
    _validate_string_list(rules, "적용 규칙")
    if rules != sorted(set(rules)) or any(not re.fullmatch(r"AR-\d{2}", rule) for rule in rules):
        raise ValueError("적용 규칙 must be a sorted unique list of AR-nn IDs")
    return payload


def serialize_csv_value(field: str, value: Any) -> str | int:
    if value is None:
        return ""
    if field in COMPLEX_FIELDS:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return value


def _validate_string_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
