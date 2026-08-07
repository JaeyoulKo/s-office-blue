from __future__ import annotations

import re

from .models import EmailMessage, MissingField, ReplyDraft, ReviewResult


CLASSIFICATION_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("구매 승인 요청", ("승인", "approval", "approve", "ariba request", "ariba 승인")),
    ("계약 관련", ("계약", "contract", "renewal", "갱신", "해지", "terms")),
    ("구매 요청", ("구매", "purchase", "발주", "order", "견적", "quotation", "quote", "조달")),
    ("보완 요청 또는 질의", ("보완", "확인 부탁", "질의", "question", "clarif")),
    ("공지", ("공지", "notice", "안내드립니다", "for your information", "fyi")),
)

FIELD_RULES: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    "구매 요청": (
        ("item_or_service", "구매 대상을 확인할 수 없습니다.", ("품목", "아이템", "서비스", "item", "service", "제품")),
        ("purpose", "구매 목적이 없어 필요성을 검토할 수 없습니다.", ("목적", "사유", "필요", "because", "purpose", "위해")),
        ("supplier", "공급사가 없어 견적 및 거래 조건을 확인할 수 없습니다.", ("공급사", "업체", "vendor", "supplier")),
        ("amount", "금액과 통화가 없어 지출 규모를 검토할 수 없습니다.", ("금액", "원", "krw", "usd", "$", "₩", "price", "cost")),
        ("scope_or_quantity", "수량 또는 업무 범위가 없어 견적의 적정성을 검토할 수 없습니다.", ("수량", "개", "명", "quantity", "qty", "범위", "scope", "license", "seat")),
        ("delivery_date", "필요 납기가 없어 일정 영향을 검토할 수 없습니다.", ("납기", "필요일", "delivery", "due", "까지", "일정")),
    ),
    "구매 승인 요청": (
        ("requested_action", "요청된 승인 또는 작업이 명확하지 않습니다.", ("승인", "approval", "approve", "결재")),
        ("item_or_service", "승인 대상 품목 또는 서비스를 확인할 수 없습니다.", ("품목", "아이템", "서비스", "item", "service", "제품")),
        ("supplier", "공급사가 없어 거래 대상을 확인할 수 없습니다.", ("공급사", "업체", "vendor", "supplier")),
        ("amount", "금액과 통화가 없어 승인 규모를 검토할 수 없습니다.", ("금액", "원", "krw", "usd", "$", "₩", "price", "cost")),
        ("purpose", "구매 목적이 없어 승인 필요성을 검토할 수 없습니다.", ("목적", "사유", "필요", "because", "purpose", "위해")),
        ("requester", "요청자를 확인할 수 없습니다.", ("요청자", "requester", "담당자")),
    ),
    "계약 관련": (
        ("supplier", "계약 상대방을 확인할 수 없습니다.", ("공급사", "업체", "vendor", "supplier", "계약 상대")),
        ("contract_subject", "계약 대상을 확인할 수 없습니다.", ("계약 대상", "서비스", "제품", "subject", "scope")),
        ("requested_action", "요청된 계약 작업을 확인할 수 없습니다.", ("검토", "체결", "변경", "갱신", "해지", "review", "sign", "renew")),
        ("contract_period", "계약 기간을 확인할 수 없습니다.", ("계약 기간", "기간", "부터", "까지", "term", "기간:")),
    ),
}

QUESTIONS: dict[str, str] = {
    "item_or_service": "구매하려는 품목 또는 서비스의 명칭과 주요 사양을 알려주시겠어요?",
    "purpose": "구매 목적과 해결하려는 업무 필요를 알려주시겠어요?",
    "supplier": "공급사명과 해당 공급사를 선택한 근거를 알려주시겠어요?",
    "amount": "총금액과 통화, 세금 포함 여부를 알려주시겠어요?",
    "scope_or_quantity": "구매 수량 또는 서비스 범위를 알려주시겠어요?",
    "delivery_date": "필요 납기 또는 서비스 시작일을 알려주시겠어요?",
    "requested_action": "검토자가 수행해야 할 승인 또는 계약 작업을 구체적으로 알려주시겠어요?",
    "requester": "요청자 이름과 담당 부서를 알려주시겠어요?",
    "contract_subject": "계약 대상 제품 또는 서비스와 주요 범위를 알려주시겠어요?",
    "contract_period": "계약 시작일과 종료일을 알려주시겠어요?",
    "cost_breakdown": "총금액을 구성하는 단가·수량·기간 등 비용 산출 근거를 알려주시겠어요?",
    "expected_effects": "구매로 기대하는 정량적 또는 정성적 효과와 근거를 알려주시겠어요?",
}

EXPLICIT_UNKNOWN_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("비용 산출 근거: unknown", "cost_breakdown", "비용 산출 근거가 없어 금액 구성을 검토할 수 없습니다."),
    ("기대효과: unknown", "expected_effects", "기대효과가 없어 구매 필요성과 효과를 검토할 수 없습니다."),
)


def _contains(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def classify_email(message: EmailMessage) -> str:
    text = f"{message.subject}\n{message.body}".casefold()
    for classification, signals in CLASSIFICATION_SIGNALS:
        if _contains(text, signals):
            return classification
    return "일반 업무 이메일" if len(message.body.strip()) >= 20 else "분류 불가"


def _extract_facts(text: str, rules: tuple[tuple[str, str, tuple[str, ...]], ...]) -> dict[str, str]:
    facts: dict[str, str] = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for field, _, signals in rules:
        matching_line = next((line for line in lines if _contains(line.casefold(), signals)), None)
        if matching_line:
            facts[field] = matching_line[:300]
    amount_match = re.search(r"(?i)(?:KRW|USD|EUR|JPY|₩|\$|€|¥)?\s*\d[\d,]*(?:\.\d+)?\s*(?:원|만원|억원|KRW|USD|EUR|JPY)?", text)
    if amount_match and any(mark in amount_match.group(0).casefold() for mark in ("원", "krw", "usd", "eur", "jpy", "₩", "$", "€", "¥")):
        facts["amount"] = amount_match.group(0).strip()
    return facts


def _reply_subject(subject: str) -> str:
    clean = re.sub(r"^(?:(?:re|fw|fwd)\s*:\s*)+", "", subject, flags=re.IGNORECASE).strip()
    return f"Re: [보완 요청] {clean}"


def _make_reply(message: EmailMessage, missing: list[MissingField]) -> ReplyDraft:
    questions = "\n".join(f"- {item.question}" for item in missing)
    body = (
        "안녕하세요.\n\n"
        f"'{message.subject}' 건의 검토를 위해 아래 정보를 확인 부탁드립니다.\n\n"
        f"{questions}\n\n"
        "현재 제공된 자료만으로는 구매 요청을 충분히 검토하기 어렵습니다. "
        "회신해 주시면 확인 후 검토를 이어가겠습니다.\n\n감사합니다."
    )
    return ReplyDraft(to=message.sender, subject=_reply_subject(message.subject), body=body)


def review_email(message: EmailMessage) -> ReviewResult:
    classification = classify_email(message)
    rules = FIELD_RULES.get(classification)
    if rules is None:
        state = "USER_CONFIRMATION_NEEDED" if classification == "분류 불가" else "BRIEFING_READY"
        status = "분류 불가" if classification == "분류 불가" else "검토 가능"
        return ReviewResult(
            message_id=message.message_id,
            thread_id=message.thread_id,
            classification=classification,
            status=status,
            workflow_state=state,
            confirmed_facts={},
            missing_fields=[],
            needs_user_confirmation=[],
            reply_draft=None,
        )

    text = f"{message.subject}\n{message.body}"
    facts = _extract_facts(text, rules)
    missing = [
        MissingField(field=field, reason=reason, question=QUESTIONS[field])
        for field, reason, _ in rules
        if field not in facts
    ]
    for marker, field, reason in EXPLICIT_UNKNOWN_FIELDS:
        if marker in text and all(item.field != field for item in missing):
            missing.append(MissingField(field=field, reason=reason, question=QUESTIONS[field]))
    if missing:
        return ReviewResult(
            message_id=message.message_id,
            thread_id=message.thread_id,
            classification=classification,
            status="정보 보완 필요",
            workflow_state="WAITING_FOR_USER_APPROVAL",
            confirmed_facts=facts,
            missing_fields=missing,
            needs_user_confirmation=["보완 요청 답장 초안을 검토하고 발송 여부를 승인해야 합니다."],
            reply_draft=_make_reply(message, missing),
        )

    status = "승인 검토 가능" if classification == "구매 승인 요청" else "검토 가능"
    return ReviewResult(
        message_id=message.message_id,
        thread_id=message.thread_id,
        classification=classification,
        status=status,
        workflow_state="REVIEW_BRIEF_READY",
        confirmed_facts=facts,
        missing_fields=[],
        needs_user_confirmation=[],
        reply_draft=None,
    )
