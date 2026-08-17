"""이메일 목록을 읽고, 정규화하고, 순위를 매기는 순수 로직.

Streamlit도 Codex도 import하지 않는다. 이 모듈의 모든 함수는 같은 입력에 같은 출력을
내므로 API 호출 없이 단위 테스트할 수 있다.

정렬은 모델이 아니라 여기서 결정한다. 모델은 판단(`urgency`)을 제공하고, 순서 자체는
결정론적인 비교자가 만든다. 그래야 같은 입력이 항상 같은 화면이 된다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .skill_registry import PROJECT_ROOT

EMAIL_DIR = PROJECT_ROOT / "data" / "synthetic" / "emails"

# shared/taxonomy.md 및 skills/email-classifier/references/decision-rules.md와 같아야 한다.
# tests/test_emails.py::test_taxonomy_labels_match_decision_rules 가 이를 강제한다.
LABELS: tuple[str, ...] = (
    "구매 승인 요청",
    "구매 요청",
    "계약 관련",
    "보완 요청 또는 질의",
    "공지",
    "일반 업무 이메일",
    "분류 불가",
)

# decision-rules.md "분류 후 처리"의 라우팅을 그대로 옮긴 것이다.
PURCHASE_LABELS = frozenset({"구매 승인 요청", "구매 요청", "계약 관련"})
DISCUSSION_LABELS = frozenset({"보완 요청 또는 질의", "분류 불가"})
REPLY_LABELS = PURCHASE_LABELS | DISCUSSION_LABELS

URGENCY_RANK = {"high": 0, "medium": 1, "low": 2}
URGENCY_ORDER = ("low", "medium", "high")

# docs/storyboard/05_bottom.png 의 "구매승인 요청 이메일 우선순위 판별" 규칙.
TOP_AMOUNT_COUNT = 5
TAX_PATTERN = re.compile(r"세금|세액|부가세|계산서|tax|VAT", re.IGNORECASE)
OVERDUE_PATTERN = re.compile(
    r"지급\s*기일|지급기한|납기\s*초과|연체|미지급|기한\s*초과|납부\s*지연|overdue|past\s*due",
    re.IGNORECASE,
)
# 규칙이 아니라 모델이 잡아야 하는 표현이지만, 모델이 필드를 빠뜨렸을 때의 하한으로 둔다.
DEADLINE_PATTERN = re.compile(
    r"오늘까지|내일까지|금일\s*중|독촉|[0-9]\s*차\s*요청|긴급|즉시|ASAP|urgent",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- 금액


@dataclass(frozen=True)
class Amount:
    """이메일에서 읽어낸 금액.

    `value`는 원화 정수일 때만 채운다. 환율 근거가 없으므로 외화는 환산하지 않고
    `value=None`으로 두며, 화면에는 `raw`를 그대로 보여준다.
    """

    value: int | None = None
    currency: str = ""
    raw: str = ""

    @property
    def known(self) -> bool:
        return self.value is not None

    def display(self) -> str:
        if self.value is not None:
            return f"{self.value:,}원"
        if self.raw:
            return f"통화 상이 ({self.raw})"
        return "금액 미상"


_KRW_TOKENS = ("KRW", "₩", "원", "만원", "억원")
_UNIT_FACTORS = (("억", 100_000_000), ("천만", 10_000_000), ("백만", 1_000_000), ("만", 10_000))
_CURRENCY_ALIASES = {
    "krw": "KRW", "₩": "KRW", "원": "KRW", "만원": "KRW", "억원": "KRW",
    "usd": "USD", "$": "USD", "달러": "USD",
    "eur": "EUR", "€": "EUR",
    "jpy": "JPY", "¥": "JPY", "엔": "JPY",
}

# 숫자 옆에 통화 토큰이 붙어 있을 때만 금액으로 인정한다. 맨 숫자를 읽으면
# "PR10293", "센서 500개", "12개월", "8/01" 이 전부 금액이 되어 정렬이 조용히 틀어진다.
_CURRENCY = r"KRW|USD|EUR|JPY|₩|\$|€|¥|원|달러|엔"
_NUMBER = r"[0-9][0-9,\.]*"
_KOREAN_UNITS = r"(?:억|천만|백만|만)"

_AMOUNT_PATTERNS = (
    # 1억 2천만원 / 3억원 — 한국어 단위가 붙은 형태를 먼저 본다.
    # 끝의 `(?:...)?`는 반드시 그룹으로 감싼다. `{_NUMBER}?`로 쓰면 마지막 `*`에 `?`가 붙어
    # 선택이 아니라 lazy 수량자가 되고, 이 분기가 통째로 죽는다.
    re.compile(
        rf"(?P<body>(?:{_NUMBER}\s*{_KOREAN_UNITS}\s*)+(?:{_NUMBER})?)\s*(?P<cur>{_CURRENCY})"
    ),
    # 60,000,000 KRW
    re.compile(rf"(?P<body>{_NUMBER})\s*(?P<cur>{_CURRENCY})"),
    # $40,000 / ₩60,000,000
    re.compile(rf"(?P<cur>{_CURRENCY})\s*(?P<body>{_NUMBER})"),
)


def _parse_korean_units(text: str) -> int | None:
    """`1억 2천만` 같은 한국어 단위 표기를 정수로 바꾼다."""
    remainder = text.replace(",", "").replace(" ", "")
    if not remainder:
        return None
    total = 0
    matched = False
    for unit, factor in _UNIT_FACTORS:
        match = re.search(rf"([0-9]+(?:\.[0-9]+)?){unit}", remainder)
        if not match:
            continue
        matched = True
        total += int(float(match.group(1)) * factor)
        remainder = remainder.replace(match.group(0), "", 1)
    if not matched:
        return None
    leftover = re.fullmatch(r"[0-9]+", remainder)
    if leftover:
        total += int(leftover.group(0))
    return total


def _parse_one(text: str) -> Amount | None:
    for pattern in _AMOUNT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        body = match.group("body").strip()
        currency = _CURRENCY_ALIASES.get(match.group("cur").strip().lower(), "")
        value = _parse_korean_units(body)
        if value is None:
            digits = body.replace(",", "")
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", digits):
                continue
            value = int(float(digits))
        raw = match.group(0).strip()
        if currency != "KRW":
            return Amount(value=None, currency=currency, raw=raw)
        return Amount(value=value, currency="KRW", raw=raw)
    return None


def parse_amount(*candidates: object) -> Amount:
    """지정된 출처에서만, 통화 토큰이 붙은 숫자만 금액으로 읽는다.

    호출자가 넘긴 순서가 신뢰 순서다: `total_amount`(구조화된 필드) → 제목 → 본문.
    어디에서도 통화가 붙은 숫자를 찾지 못하면 금액 미상으로 둔다.
    """
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if not text:
            continue
        parsed = _parse_one(text)
        if parsed is not None:
            return parsed
    return Amount()


# --------------------------------------------------------------------- 정규화·적재


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# 메일 클라이언트가 흔히 걷어내는 접두사만 뗀다. 특정 시스템에 맞춘 규칙은 두지 않는다.
SUBJECT_PREFIX = re.compile(
    r"^(?:\s*(?:re|fw|fwd|답장|전달|회신)\s*:\s*|\s*action required\s*:\s*)+", re.IGNORECASE
)


def subject_title(subject: str, limit: int = 60) -> str:
    """폴딩 헤더에 쓸 짧은 제목. 제목 외의 정보는 쓰지 않는다."""
    return _clip(SUBJECT_PREFIX.sub("", str(subject or "")), limit) or "(제목 없음)"


def _ariba_record_to_email(data: dict[str, Any]) -> dict[str, Any]:
    """Ariba 테스트 레코드를 실제 알림 메일처럼 펼친다.

    테스트 JSON에는 `total_amount`, `cost_breakdown.has_data` 같이 **이미 파싱된** 필드가
    들어 있다. 실제 메일함에는 그런 게 없으므로 여기서 한 번만 본문 텍스트로 풀어놓고,
    이후 파이프라인은 제목·발신·날짜·본문만 본다. 그래야 Gmail에서도 같은 코드가 돈다.

    `has_data`가 거짓인 항목은 플래그로 넘기지 않고 본문에 "기재되지 않음"이라고 적는다.
    누락 판단은 우리가 미리 계산해 주는 게 아니라 모델이 본문을 읽고 내려야 한다.
    """
    cost = data.get("cost_breakdown") if isinstance(data.get("cost_breakdown"), dict) else {}
    effects = data.get("expected_effects") if isinstance(data.get("expected_effects"), dict) else {}
    requester = str(data.get("requester") or "").strip()
    pr_number = str(data.get("pr_number") or "").strip()
    missing = "기재되지 않음"

    lines = [
        "안녕하세요,",
        "",
        f"{requester or '요청자'}님이 제출한 구매 요청({pr_number or '번호 미상'})에 대한 "
        "승인 검토가 필요합니다.",
        "",
        f"- 공급업체: {data.get('vendor') or missing}",
        f"- 구매 유형: {data.get('type') or missing}",
        f"- 총액: {data.get('total_amount') or missing}",
        f"- 요청 내용: {data.get('description') or missing}",
        "",
        f"비용 산출 근거: {cost.get('details') or missing}",
        f"예상 정량 효과: {effects.get('details') or missing}",
    ]
    if data.get("recent_comments"):
        lines += ["", "[최근 의견]", str(data["recent_comments"])]
    lines += ["", "감사합니다.", "Ariba 구매 시스템"]

    return {
        "case_id": pr_number or str(data.get("id") or "email"),
        "message_id": f"ariba-{data.get('id')}" if data.get("id") else "",
        "thread_id": f"ariba-{pr_number}" if pr_number else "",
        "sender": f"{requester} (Ariba)" if requester else "Ariba 구매 시스템",
        "recipients": [],
        "subject": str(data.get("email_subject") or ""),
        "body": "\n".join(lines),
        # 실제 메일에는 항상 날짜가 있다. 테스트 데이터가 주면 쓰고, 없으면 비워 둔다.
        # 없는 날짜를 지어내지 않는다.
        "received_at": str(data.get("received_at") or ""),
        "attachments": data.get("attachments") or [],
        "thread": data.get("thread") or [],
    }


# 실제 메일이 실제로 갖는 것만 쓴다. 테스트 JSON의 특수 필드는 여기까지 오지 않는다.
ARIBA_MARKERS = ("pr_number", "total_amount", "cost_breakdown", "expected_effects")


def normalize_email(data: dict[str, Any]) -> dict[str, Any]:
    """어떤 입력이든 하나의 이메일 형태로 맞춘다.

    Ariba 테스트 레코드는 먼저 알림 메일로 펼친 뒤 처리한다. 결과 레코드에는 제목, 발신,
    수신, 날짜, 본문, 첨부, 스레드만 남고 파생값은 `title`과 `amount`뿐이다.
    """
    if any(key in data for key in ARIBA_MARKERS):
        data = _ariba_record_to_email(data)

    subject = str(data.get("subject") or data.get("email_subject") or "")
    body = str(data.get("body") or data.get("email_body") or "")
    return {
        "case_id": str(
            data.get("case_id") or data.get("message_id") or data.get("id") or "email"
        ),
        "message_id": str(data.get("message_id") or ""),
        "thread_id": str(data.get("thread_id") or ""),
        "sender": str(data.get("sender") or data.get("from") or ""),
        "recipients": data.get("recipients") or data.get("to") or [],
        "subject": subject,
        "title": subject_title(subject),
        "body": body,
        "received_at": str(data.get("received_at") or ""),
        "attachments": data.get("attachments") or [],
        "thread": data.get("thread") or [],
        # 실제 메일에는 금액 필드가 없다. 제목과 본문에서만 읽는다.
        "amount": parse_amount(subject, body),
    }


CODEX_FIELDS = (
    "case_id", "message_id", "thread_id", "sender", "recipients",
    "subject", "body", "received_at", "attachments", "thread",
)


def for_codex(email: dict[str, Any]) -> dict[str, Any]:
    """모델에 보낼 이메일 형태로 줄인다.

    실제 메일이 갖는 필드만 넘긴다. 우리가 파싱해둔 `amount`나 화면용 `title`은 보내지
    않는다 — 모델이 판단해야 할 것을 우리가 미리 답해 주는 셈이 되고, 테스트 데이터에만
    있는 필드에 모델이 기대게 만들면 Gmail에서 그대로 무너진다.
    """
    if "amount" not in email:
        # 정규화를 거치지 않은 원본 dict다. 기존 단건 흐름이 쓰던 형태이므로 건드리지 않는다.
        return email
    return {key: email[key] for key in CODEX_FIELDS if email.get(key) not in (None, "", [])}


def load_sources() -> list[tuple[Path, str, int]]:
    """`data/synthetic/emails/` 아래 모든 JSON을 찾는다.

    `rglob`인 것이 중요하다. 기존 UI는 비재귀 `glob`을 써서 30건짜리
    `purchase-email-review/purchase-review-email-sample.json`이 목록에 아예 없었다.
    """
    sources: list[tuple[Path, str, int]] = []
    if not EMAIL_DIR.is_dir():
        return sources
    for path in sorted(EMAIL_DIR.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        count = len(data) if isinstance(data, list) else 1
        label = f"{path.relative_to(EMAIL_DIR).as_posix()} ({count}건)"
        sources.append((path, label, count))
    return sources


def load_inbox(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """JSON 파일 하나를 정규화된 이메일 목록으로 읽는다. 객체 하나도, 배열도 받는다."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else [data]
    if limit is not None:
        records = records[:limit]
    inbox: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        email = normalize_email(record)
        # case_id는 화면 선택 상태의 키라서 중복되면 안 된다.
        case_id = email["case_id"]
        if case_id in seen:
            seen[case_id] += 1
            email["case_id"] = f"{case_id}#{seen[case_id]}"
        else:
            seen[case_id] = 0
        email["index"] = index
        inbox.append(email)
    return inbox


# ------------------------------------------------------------------------- 긴급도


def amount_ranks(inbox: Sequence[dict[str, Any]]) -> dict[str, int]:
    """금액이 확인된 건에 대해 큰 순으로 0부터 순위를 매긴다.

    동점이 있다. 이 데이터셋만 해도 90,000,000원이 두 건(id 10, 15)이고 그 지점이
    정확히 top5 경계다. `index`를 tiebreak으로 써서 경계를 결정론적으로 만든다.
    """
    ranked = sorted(
        (email for email in inbox if email["amount"].known),
        key=lambda email: (-(email["amount"].value or 0), email.get("index", 0)),
    )
    return {email["case_id"]: rank for rank, email in enumerate(ranked)}


def rule_urgency(
    email: dict[str, Any],
    *,
    amount_rank: int | None,
    is_purchase: bool,
    amount_pool: int = 0,
) -> tuple[str, list[str]]:
    """규칙만으로 정할 수 있는 긴급도 하한.

    docs/storyboard/05_bottom.png 의 판별 규칙을 그대로 옮겼다. 모델이 `urgency`를
    빠뜨리거나 데이터에 긴급도 표현이 하나도 없어도 순서가 평평해지지 않게 하는 바닥이다.

    금액 순위 규칙은 후보가 `TOP_AMOUNT_COUNT`보다 많을 때만 적용한다. 후보가 5건 이하면
    "상위 5건"이 곧 전체라 아무것도 구분하지 못하면서 목록만 전부 빨갛게 만든다.
    """
    reasons: list[str] = []
    urgency = "low"
    # 제목과 본문만 본다. 실제 메일에 있는 게 그것뿐이다.
    haystack = f"{email.get('subject') or ''} {email.get('body') or ''}"

    ranks_discriminate = amount_pool > TOP_AMOUNT_COUNT
    if ranks_discriminate and is_purchase and amount_rank is not None and amount_rank < TOP_AMOUNT_COUNT:
        urgency = "high"
        reasons.append(f"[규칙] 금액순 상위 {amount_rank + 1}위")
    if OVERDUE_PATTERN.search(haystack):
        urgency = "high"
        reasons.append("[규칙] 지급기일 초과 표현")
    if TAX_PATTERN.search(haystack):
        urgency = _raise(urgency, "medium")
        reasons.append("[규칙] 세금 관련 표현")
    if DEADLINE_PATTERN.search(haystack):
        urgency = _raise(urgency, "medium")
        reasons.append("[규칙] 기한·독촉 표현")
    return urgency, reasons


def _raise(current: str, floor: str) -> str:
    return current if URGENCY_ORDER.index(current) >= URGENCY_ORDER.index(floor) else floor


def merge_urgency(
    rule: tuple[str, list[str]], model_urgency: object
) -> tuple[str, list[str]]:
    """규칙을 하한, 모델을 상한으로 합친다.

    모델이 필드를 안 주거나 모르는 값을 주면 규칙 값만 쓴다. 근거는 출처를 붙여
    남겨서 화면에서 왜 이 순서인지 확인할 수 있게 한다.
    """
    rule_value, reasons = rule
    reasons = list(reasons)
    candidate = str(model_urgency or "").strip().lower()
    if candidate in URGENCY_RANK:
        if URGENCY_ORDER.index(candidate) > URGENCY_ORDER.index(rule_value):
            reasons.append(f"[AI] {candidate}로 판단")
            return candidate, reasons
        # 규칙이 실제로 무언가를 올렸을 때만 "규칙이 우선"이라고 말한다.
        reasons.append(f"[AI] {candidate}로 판단" + (" (규칙이 우선)" if reasons else ""))
    elif not reasons:
        reasons.append("[규칙] 해당 신호 없음")
    return rule_value, reasons


# --------------------------------------------------------------------- 브리핑·정렬


def build_briefing(
    email: dict[str, Any],
    record: dict[str, Any] | None,
    *,
    amount_rank: int | None,
    amount_pool: int = 0,
) -> dict[str, Any]:
    """정규화된 이메일 + 분류 결과를 화면이 쓰는 한 줄로 만든다.

    `record`가 없으면(아직 분류 안 함) 라벨 없이 규칙 긴급도만으로 채운다.
    """
    classification = (record or {}).get("classification") or {}
    if not isinstance(classification, dict):
        classification = {}
    label = str(classification.get("label") or "")
    is_purchase = label in PURCHASE_LABELS
    urgency, reasons = merge_urgency(
        rule_urgency(
            email, amount_rank=amount_rank, is_purchase=is_purchase, amount_pool=amount_pool
        ),
        classification.get("urgency"),
    )
    status = (record or {}).get("status") or ("ok" if record else "pending")
    return {
        # 분류 전에는 받은편지함 한 줄이 아는 것만 안다: 제목, 발신, 날짜, 첨부.
        # 금액은 본문을 읽어야 나오는 값이라 분류가 끝난 뒤에만 노출한다.
        "classified": status == "ok",
        "case_id": email["case_id"],
        "index": email.get("index", 0),
        "email": email,
        "title": email["title"],
        "subject": email["subject"],
        "sender": email["sender"],
        "received_at": email["received_at"],
        "received_ts": _received_ts(email["received_at"]),
        "amount": email["amount"],
        "label": label,
        "is_purchase": is_purchase,
        "needs_reply": label in REPLY_LABELS,
        "urgency": urgency,
        "urgency_reasons": reasons,
        "classification": classification,
        "status": status,
        "error": (record or {}).get("error"),
        "text": (record or {}).get("text", ""),
    }


def _received_ts(value: str) -> float | None:
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _balanced_key(item: dict[str, Any]) -> tuple:
    amount = item["amount"].value
    purchase = item["is_purchase"]
    return (
        URGENCY_RANK.get(item["urgency"], 1),                  # 1) 긴급건 우선
        0 if purchase else 1,                                  # 2) 같은 긴급도면 구매 관련 먼저
        0 if (not purchase or amount is not None) else 1,      # 3) 금액 미상은 0원보다 뒤
        -(amount or 0) if purchase else 0,                     # 4) 구매 건은 금액 큰 순
        -(item["received_ts"] or 0),                           # 5) 최근 수신 먼저
        item["index"],                                         # 6) 입력 순서 — 완전 결정성
    )


def _urgency_key(item: dict[str, Any]) -> tuple:
    return (
        URGENCY_RANK.get(item["urgency"], 1),
        -(item["received_ts"] or 0),
        item["index"],
    )


def _amount_key(item: dict[str, Any]) -> tuple:
    amount = item["amount"].value if item["classified"] else None
    return (0 if amount is not None else 1, -(amount or 0), item["index"])


SORT_MODES = {"균형": _balanced_key, "긴급도": _urgency_key, "금액순": _amount_key}


def rank_briefings(items: Iterable[dict[str, Any]], *, mode: str = "균형") -> list[dict[str, Any]]:
    """정렬하고 `rank`를 매긴다. 실패 건은 순위에서 뺀다.

    실패 건은 라벨도 긴급도도 없어 어디에 끼워도 의미가 없으므로 화면 아래 별도
    섹션으로 보낸다.
    """
    key = SORT_MODES.get(mode, _balanced_key)
    ordered = sorted((item for item in items if item["status"] != "error"), key=key)
    for rank, item in enumerate(ordered):
        item["rank"] = rank
    return ordered


def summarize(inbox: Sequence[dict[str, Any]], items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """분류 결과에서 나오는 집계.

    "필수 구성항목 충족" 같은 검토 판정은 여기서 세지 않는다. 그건 `purchase-email-review`가
    본문을 읽고 내리는 판단이지 입력 데이터에서 읽어올 값이 아니다. 실제 메일함에는 그런
    플래그가 아예 없다.
    """
    counts = {label: 0 for label in LABELS}
    unclassified = 0
    for item in items:
        if item["label"] in counts:
            counts[item["label"]] += 1
        else:
            unclassified += 1

    urgent = sum(1 for item in items if item["classified"] and item["urgency"] == "high")
    needs_reply = sum(1 for item in items if item["needs_reply"])
    # 금액 합계도 분류가 끝난 건에서만 센다. 분류 전에 총액을 보여주면 아직 읽지도 않은
    # 본문에서 값을 꺼내 온 셈이 된다.
    known = [item for item in items if item["classified"] and item["amount"].known]
    top = sorted(
        (item for item in items if item["is_purchase"] and item["amount"].known),
        key=lambda item: (-(item["amount"].value or 0), item["index"]),
    )[:TOP_AMOUNT_COUNT]
    return {
        "total": len(inbox),
        "classified": sum(1 for item in items if item["classified"]),
        "label_counts": {label: count for label, count in counts.items() if count},
        "unclassified": unclassified,
        "urgent": urgent,
        "needs_reply": needs_reply,
        "amount_total": sum(item["amount"].value or 0 for item in known),
        "amount_known": len(known),
        "top_amounts": top,
    }
