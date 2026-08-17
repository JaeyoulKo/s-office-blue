"""분류 결과에 따라 어떤 회신 Skill을 쓸지 정하는 라우팅 표.

분기를 코드 곳곳의 if 문에 흩어놓지 않고 여기 한 곳에 모은다. 새 회신 Skill이 승격되면
`REPLY_ROUTES`에 한 줄을 추가하는 것으로 끝나야 하고, 그 외의 파일은 건드릴 일이 없어야 한다.

라벨이 표에 없으면 회신을 만들지 않는다. "아직 지원하지 않는다"와 "빈 초안을 만든다"는
다르고, 후자는 사용자가 검토하지 않은 문장을 보낼 위험을 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplyRoute:
    """분류 라벨 하나가 어떤 Skill로 가는지."""

    label: str
    skill: str
    prompt: str
    action: str          # 버튼과 안내 문구에 쓰는 이름
    draft_key: str       # Skill 출력에서 초안이 들어 있는 키
    status_key: str = "" # 초안을 만들지 말지 판단하는 키 (있으면)


PURCHASE_APPROVAL = ReplyRoute(
    label="구매 승인 요청",
    skill="purchase-email-review",
    prompt=(
        "input.json의 구매·승인·계약 이메일을 검토하세요. 필요한 경우 Skill의 국문 "
        "템플릿으로 회신 초안을 포함하고 외부 작업은 하지 마세요."
    ),
    action="보완 요청 초안",
    draft_key="reply_draft",
    status_key="review_status",
)

# 라벨 → 회신 Skill. 지원하는 것만 명시적으로 적는다.
REPLY_ROUTES: dict[str, ReplyRoute] = {
    PURCHASE_APPROVAL.label: PURCHASE_APPROVAL,
    # 다음에 붙일 것들. Skill이 `skills/`로 승격되고 출력 계약이 확정되면 주석을 푼다.
    #
    # "보완 요청 또는 질의": ReplyRoute(
    #     label="보완 요청 또는 질의",
    #     skill="discussion-email-review",
    #     prompt="input.json의 논의·질의 이메일과 스레드를 검토하고 국문 회신 초안을 포함하세요.",
    #     action="논의 회신 초안",
    #     draft_key="reply_draft",
    # ),
    #
    # `구매 요청`과 `계약 관련`은 purchase-email-review의 검토 대상이지만, 승인 요청과
    # 회신 성격이 달라서 같은 경로로 묶지 않는다. 전용 Skill이 생기면 각각 추가한다.
}


# 메일 한 건이 지금 어느 단계에 있는지. 화면은 이 값으로 묶어서 보여준다.
STAGE_PENDING = "pending"          # 아직 분류하지 않음
STAGE_TODO = "todo"                # 회신을 만들어야 함
STAGE_UNSUPPORTED = "unsupported"  # 후속 처리가 필요하지만 아직 Skill이 없음
STAGE_NONE = "none"                # 처리할 내용이 없음 (공지·일반 업무 메일)
STAGE_DONE = "done"                # 처리 완료
STAGE_ERROR = "error"              # 처리하다 실패

# decision-rules.md "분류 후 처리": 공지와 일반 업무 이메일은 브리핑에서 끝난다.
TERMINAL_LABELS = frozenset({"공지", "일반 업무 이메일"})


def mail_stage(
    *, classified: bool, label: str, follow_up: bool, draft_record: dict[str, Any] | None
) -> str:
    """메일 한 건의 처리 단계를 정한다.

    `follow_up`은 분류 규칙상 후속 조치가 필요한 라벨인지(`emails.REPLY_LABELS`)다.
    회신을 만든 뒤에는 보낼 초안이 없더라도 `done`이다 — "검토했고 보낼 게 없다"는
    결론도 처리 결과이지 미처리가 아니다.
    """
    if not classified:
        return STAGE_PENDING
    if draft_record is not None:
        return STAGE_DONE if draft_record.get("status") == "ok" else STAGE_ERROR
    if label in TERMINAL_LABELS or not follow_up:
        return STAGE_NONE
    return STAGE_TODO if can_reply(label) else STAGE_UNSUPPORTED


def reply_route(label: str) -> ReplyRoute | None:
    """이 라벨에 쓸 회신 Skill. 지원하지 않으면 None."""
    return REPLY_ROUTES.get(str(label or "").strip())


def can_reply(label: str) -> bool:
    return reply_route(label) is not None


def supported_labels() -> list[str]:
    return list(REPLY_ROUTES)


def extract_draft(route: ReplyRoute, output: Any) -> dict[str, str] | None:
    """Skill 출력에서 회신 초안을 꺼낸다.

    `purchase-email-review`는 보완이 필요할 때만 `reply_draft`를 채우고 승인 가능하면
    `null`을 준다. 그건 실패가 아니라 "보낼 초안이 없다"는 판단이므로 그대로 존중한다.
    """
    if not isinstance(output, dict):
        return None
    draft = output.get(route.draft_key)
    if not isinstance(draft, dict):
        return None
    body = str(draft.get("body") or "").strip()
    if not body:
        return None
    return {
        "to": str(draft.get("to") or ""),
        "subject": str(draft.get("subject") or ""),
        "body": body,
    }
