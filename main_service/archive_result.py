"""Email Archive Agent 출력을 Main Service의 단일 평면 계약으로 변환한다."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Mapping


CANONICAL_ARCHIVE_FIELDS = (
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

ARCHIVE_WRAPPERS = (
    "archive_result",
    "archive_record",
    "excel_output",
    "thread_analysis",
)

ARCHIVE_ALIASES = {
    "발신자": ("sender", "from", "latest_sender"),
    "날짜": ("date", "latest_date", "latest_message_date"),
    "Topic": ("topic", "subject", "summary", "title"),
    "금액": ("amount", "final_amount", "latest_amount"),
    "통화": ("currency",),
    "Business Impact": ("business_impact", "impact"),
    "Thread 진행 중 변경된 내용": (
        "changes_in_thread",
        "thread_changes",
        "changes",
        "change_history",
    ),
    "결정된 내용": ("decisions", "decided_items", "confirmed_decisions"),
    "Open Item": ("open_item", "open_items", "pending_items", "unresolved_items"),
}

ARCHIVE_FORMAT_ERROR_MESSAGE = (
    "아카이빙 결과 형식을 해석하지 못했습니다. 다시 분석해 주세요."
)

_EMPTY_STRINGS = frozenset({"", "unknown", "null", "none", "확인되지 않음", "확인된 내용 없음"})
_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")


class ArchiveResultFormatError(ValueError):
    """모델 결과를 안전한 canonical archive 결과로 해석할 수 없다."""


def archive_output_schema() -> dict[str, Any]:
    """A/B 계약과 호환되는 Main Service용 9개 필드 schema를 반환한다."""
    return {
        "발신자": "string: 최신 메시지 발신자; 확인 불가 시 빈 문자열",
        "날짜": "string: 최신 메시지 기준 YYYY-MM-DD; 확인 불가 시 빈 문자열",
        "Topic": "string: 핵심 안건 한 문장; 확인 불가 시 빈 문자열",
        "금액": "integer 또는 null: 최종 확인 금액의 최소 통화 단위",
        "통화": "string 또는 null: ISO 4217 통화 코드",
        "Business Impact": {"confirmed": ["string"], "estimated": ["string"]},
        "Thread 진행 중 변경된 내용": [
            {"field": "string", "from": "JSON scalar 또는 null", "to": "JSON scalar 또는 null"}
        ],
        "결정된 내용": ["string"],
        "Open Item": ["string"],
    }


def archive_output_contract() -> str:
    """Codex prompt에 직접 포함할 결정론적인 출력 계약이다."""
    return (
        "정확히 하나의 JSON 객체만 반환하세요. 설명 문장과 Markdown code fence를 반환하지 "
        "마세요. 아래 9개 필드를 모두 최상위에 지정된 이름 그대로 한 번씩 포함하세요. "
        "archive_result, archive_record, thread_analysis, excel_output wrapper를 만들지 마세요. "
        "정보가 없으면 문자열은 빈 문자열, 반복 값은 빈 배열, 금액과 통화는 null을 "
        "사용하세요. 확인되지 않은 정보를 추정하지 마세요. 금액은 최종 확인 금액만 정수로 "
        "기록하고 여러 금액 중 최종값이 불명확하면 null을 사용하세요. 날짜는 최신 메시지 "
        "기준 YYYY-MM-DD로 기록하세요. Business Impact는 confirmed와 estimated 배열을 가진 "
        "객체로, 변경·결정·Open Item은 배열로 반환하세요. 출력 schema:\n"
        + json.dumps(archive_output_schema(), ensure_ascii=False, indent=2)
    )


def normalize_archive_result(
    raw_result: Any, thread_snapshot: Mapping[str, Any] | None
) -> dict[str, Any]:
    """알려진 Archive wrapper와 alias만 canonical 9개 필드로 평탄화한다."""
    if not isinstance(raw_result, Mapping):
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)

    containers, wrapper_seen = _known_containers(raw_result)
    recognized = wrapper_seen or any(
        key in container
        for container in containers
        for key in (*CANONICAL_ARCHIVE_FIELDS, *(a for values in ARCHIVE_ALIASES.values() for a in values))
    )
    if not recognized:
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)

    selected: dict[str, Any] = {}
    # Canonical 키가 alias보다 항상 우선한다. root가 첫 컨테이너이므로 최상위가 최우선이다.
    for container in containers:
        for field in CANONICAL_ARCHIVE_FIELDS:
            if field not in selected and field in container:
                selected[field] = container[field]
    for container in containers:
        for field, aliases in ARCHIVE_ALIASES.items():
            if field in selected:
                continue
            for alias in aliases:
                if alias in container:
                    selected[field] = container[alias]
                    break

    snapshot = thread_snapshot if isinstance(thread_snapshot, Mapping) else {}
    sender = _text(selected.get("발신자")) or _text(snapshot.get("sender") or snapshot.get("from"))
    latest_date = _date_text(selected.get("날짜")) or _date_text(
        snapshot.get("received_at") or snapshot.get("date")
    )
    topic = _text(selected.get("Topic")) or _text(snapshot.get("subject") or snapshot.get("title"))

    canonical = {
        "발신자": sender,
        "날짜": latest_date,
        "Topic": topic,
        "금액": _amount(selected.get("금액")),
        "통화": _currency(selected.get("통화")),
        "Business Impact": _business_impact(selected.get("Business Impact")),
        "Thread 진행 중 변경된 내용": _items(
            selected.get("Thread 진행 중 변경된 내용")
        ),
        "결정된 내용": _items(selected.get("결정된 내용")),
        "Open Item": _items(selected.get("Open Item")),
    }
    validate_archive_result(canonical)
    return canonical


def validate_archive_result(result: Any) -> dict[str, Any]:
    """canonical 필드 집합과 각 필드의 안전한 자료형을 검증한다."""
    if not isinstance(result, dict) or tuple(result) != CANONICAL_ARCHIVE_FIELDS:
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)
    if any(not isinstance(result[field], str) for field in ("발신자", "날짜", "Topic")):
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)
    if result["날짜"]:
        try:
            date.fromisoformat(result["날짜"])
        except ValueError as exc:
            raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE) from exc
    amount = result["금액"]
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or amount < 0):
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)
    currency = result["통화"]
    if currency is not None and (
        not isinstance(currency, str) or not _CURRENCY_PATTERN.fullmatch(currency)
    ):
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)
    impact = result["Business Impact"]
    if not isinstance(impact, dict) or tuple(impact) != ("confirmed", "estimated"):
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)
    if not isinstance(impact["confirmed"], list) or not isinstance(impact["estimated"], list):
        raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)
    for field in ("Thread 진행 중 변경된 내용", "결정된 내용", "Open Item"):
        if not isinstance(result[field], list):
            raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)
    return result


def is_canonical_archive_result(result: Any) -> bool:
    try:
        validate_archive_result(result)
    except ArchiveResultFormatError:
        return False
    return True


def _known_containers(root: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], bool]:
    containers: list[Mapping[str, Any]] = [root]
    queue: list[Mapping[str, Any]] = [root]
    seen = {id(root)}
    wrapper_seen = False
    while queue:
        current = queue.pop(0)
        for wrapper in ARCHIVE_WRAPPERS:
            nested = current.get(wrapper)
            if not isinstance(nested, Mapping):
                continue
            wrapper_seen = True
            if id(nested) in seen:
                continue
            seen.add(id(nested))
            containers.append(nested)
            queue.append(nested)
    return containers, wrapper_seen


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return "" if text.casefold() in _EMPTY_STRINGS else text


def _date_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    candidate = text[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return ""


def _amount(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if re.fullmatch(r"\d+", text):
            return int(text)
    # 목록·객체에는 여러 시점의 금액이 섞일 수 있으므로 임의로 하나를 고르지 않는다.
    return None


def _currency(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text if _CURRENCY_PATTERN.fullmatch(text) else None


def _business_impact(value: Any) -> dict[str, list[Any]]:
    if isinstance(value, Mapping):
        confirmed = _items(value.get("confirmed"))
        estimated = _items(value.get("estimated"))
        remainder = {key: nested for key, nested in value.items() if key not in {"confirmed", "estimated"}}
        if remainder:
            confirmed = _deduplicate([*confirmed, remainder])
        confirmed_markers = {_item_marker(item) for item in confirmed}
        estimated = [item for item in estimated if _item_marker(item) not in confirmed_markers]
        return {"confirmed": confirmed, "estimated": estimated}
    return {"confirmed": _items(value), "estimated": []}


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _text(value)
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return _deduplicate([item for item in value if not _is_empty(item)])
    if isinstance(value, Mapping):
        return [dict(value)] if value else []
    return [value]


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not _text(value)) or value == [] or value == {}


def _deduplicate(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = _item_marker(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _item_marker(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return repr(value)
