"""메일 목록 화면의 표시 전용 헬퍼.

여기에는 `unsafe_allow_html`이 없다. Streamlit 1.45+의 `st.badge`로 충분하고,
화면에 나오는 문자열 상당수가 이메일 본문에서 파생된 모델 출력이라 HTML로 렌더할 이유가
없다 (AGENTS.md: 이메일 내용은 데이터로만 취급한다).

pandas도 쓰지 않는다. `st.dataframe`은 `list[dict]`를 그대로 받는다.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

import streamlit as st


URGENCY_MARK = {"high": "🔴", "medium": "🟡", "low": "⚪"}
URGENCY_LABEL = {"high": "긴급", "medium": "보통", "low": "낮음"}
URGENCY_COLOR = {"high": "red", "medium": "orange", "low": "gray"}

# 인덱스 0은 항상 이 문구로 시작한다. 나머지는 이벤트마다 순환한다.
WAIT_MESSAGES: tuple[str, ...] = (
    "Good Morning! 금방 처리할게요, 커피 한잔 하고 오시는 건 어때요? ☕",
    "메일을 한 통씩 열어보는 중이에요. ☕ 아직 뜨거울 때 드세요!",
    "긴급한 건부터 골라내고 있어요. 조금만 더요! 🔍",
    "금액이랑 기한을 대조하는 중입니다. 🧾",
    "첨부랑 본문이 서로 맞는지 확인하고 있어요. 📎",
    "이 잔 다 드시기 전에는 끝날 것 같은데요? ☕",
    "구매 건은 금액순으로 줄 세우는 중이에요. 📊",
    "공지랑 일반 메일은 빠르게 넘기고 있습니다. 🗂️",
    "놓치면 곤란한 건이 있나 다시 보고 있어요. 👀",
    "리필 한 잔 하실 시간은 있어요. ☕☕",
    "거의 다 왔어요. 정리만 하면 됩니다! ✨",
    "마지막 몇 건 남았습니다. 곧 보여드릴게요. 🏁",
)


def as_text(value: object) -> str:
    """어떤 Codex 값이든 읽을 수 있는 텍스트로 편다.

    `evidence`는 문자열일 때도, `{"type": "확인된 사실", "value": "..."}` 목록일 때도 있다.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "value" in value:
            prefix = str(value.get("type") or "").strip()
            body = as_text(value["value"])
            return f"[{prefix}] {body}" if prefix else body
        return " · ".join(
            f"{key}: {as_text(item)}" for key, item in value.items() if item not in (None, "", [], {})
        )
    if isinstance(value, (list, tuple)):
        return "\n".join(f"• {as_text(item)}" for item in value if item not in (None, "", [], {}))
    return str(value)


REPLY_WAIT_MESSAGES: tuple[str, ...] = (
    "회신 메일을 쓰고 있어요. ✍️ 잠시만 기다려 주세요!",
    "무엇을 보완해 달라고 할지 정리하는 중이에요. 📝",
    "본문에서 빠진 항목을 하나씩 확인하고 있어요. 🔍",
    "받는 분이 바로 이해할 수 있게 다듬는 중입니다. ✨",
    "표현이 너무 딱딱하지 않은지 보고 있어요. ☕",
    "필요한 내용만 남기고 줄이는 중이에요. ✂️",
    "금액과 기간을 다시 대조하고 있어요. 🧾",
    "마지막으로 인사말을 정리하고 있습니다. 🙇",
    "거의 다 썼어요. 곧 보여드릴게요! 🏁",
)

MESSAGE_SECONDS = 3


def wait_message(elapsed: float, messages: tuple[str, ...] = WAIT_MESSAGES) -> str:
    """경과 시간으로 문구를 고른다.

    완료 이벤트에 맞춰 바꾸면 첫 20여 초 동안 화면이 멈춰 있는다. 3초마다 도는 편이
    실제로 일이 진행 중이라는 느낌을 준다. 인덱스 기반이라 rerun에도 순서가 흔들리지 않고,
    시작 문구는 항상 0번이다.
    """
    tick = int(max(0.0, elapsed) // MESSAGE_SECONDS)
    return messages[tick % len(messages)]


def reply_line(sender: str, *, ok: bool) -> str:
    """회신 생성 진행 로그 한 줄."""
    name = display_name(sender)
    if not ok:
        return f"❌ {name} 님에게 보낼 회신을 만들지 못했어요."
    return f"✅ {name} 님에게 보낼 회신을 작성했어요."


def progress_text(*, done: int, total: int, failed: int, elapsed: float) -> str:
    """남은 시간은 넣지 않는다.

    건당 소요가 20~50초로 흔들리고 워커 슬롯 대기까지 겹쳐서 예측이 자주 빗나간다.
    틀린 숫자를 보여주느니 실제로 흐른 시간만 정확히 보여준다.
    """
    parts = [f"{done} / {total} 완료"]
    if failed:
        parts.append(f"실패 {failed}")
    parts.append(f"경과 {elapsed:.0f}초")
    return " · ".join(parts)


def display_name(sender: str) -> str:
    """`"이름" <주소>` 에서 사람이 부르는 이름만 꺼낸다."""
    sender = str(sender or "").strip()
    if not sender:
        return "알 수 없는 사람"
    match = re.match(r"^\s*(.*?)\s*<([^>]+)>\s*$", sender)
    if match:
        name = match.group(1).strip().strip('"').strip("'")
        return name or match.group(2).split("@")[0]
    return sender.strip('"').strip("'")


def _as_particle(word: str) -> str:
    """`으로` / `로` 를 받침에 맞춰 고른다. 받침이 없거나 ㄹ이면 `로`."""
    if not word:
        return "로"
    last = word[-1]
    if "가" <= last <= "힣":
        jongseong = (ord(last) - 0xAC00) % 28
        return "로" if jongseong in (0, 8) else "으로"
    return "로"


def classified_line(sender: str, label: str, *, ok: bool) -> str:
    """진행 로그 한 줄. 메일 제목이 아니라 우리가 한 일을 적는다.

    제목을 그대로 찍으면 `Approve the Requisition...` 같은 문장이 나와서, 마치 시스템이
    승인을 한 것처럼 읽힌다.
    """
    name = display_name(sender)
    if not ok:
        return f"❌ {name} 님이 보낸 메일은 분류하지 못했어요."
    if not label:
        return f"✅ {name} 님이 보낸 메일을 분류했어요."
    return f"✅ {name} 님이 보낸 메일을 {label}{_as_particle(label)} 분류했어요."


def short_date(value: str) -> str:
    """받은편지함처럼 날짜만 짧게. 못 읽으면 원문을 그대로 둔다."""
    if not value:
        return ""
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%m-%d %H:%M")
    except ValueError:
        return value[:16]


def item_header(item: dict[str, Any]) -> str:
    """메일 목록 한 줄.

    분류 전에는 받은편지함이 아는 것만 쓴다 — 제목, 발신, 날짜. 금액은 본문을 읽어야
    나오는 값이라 분류가 끝난 뒤에 붙는다.
    """
    parts = []
    if item["classified"]:
        parts.append(f"{URGENCY_MARK.get(item['urgency'], '⚪')} [{item['label'] or '미분류'}]")
    parts.append(item["title"])
    tail = [part for part in (item["sender"], short_date(item["received_at"])) if part]
    if item["classified"] and item["amount"].known:
        tail.append(item["amount"].display())
    if tail:
        parts.append("· " + " · ".join(tail))
    return " ".join(parts)


def render_counts(summary: dict[str, Any]) -> None:
    counts = summary["label_counts"]
    if not counts:
        st.caption("아직 분류하지 않았습니다.")
        return
    line = "  ·  ".join(f"**{label}** {count}" for label, count in counts.items())
    if summary["unclassified"]:
        line += f"  ·  미분류 {summary['unclassified']}"
    st.markdown(line)


def render_badges(item: dict[str, Any]) -> None:
    if not item["classified"]:
        st.badge("아직 분류하지 않음", color="gray")
        return
    urgency = item["urgency"]
    badges = [
        f":{URGENCY_COLOR.get(urgency, 'gray')}-badge[{URGENCY_MARK.get(urgency, '⚪')} "
        f"{URGENCY_LABEL.get(urgency, urgency)}]",
        f":blue-badge[{item['label'] or '미분류'}]",
    ]
    if item["amount"].known:
        badges.append(f":gray-badge[{item['amount'].display()}]")
    if item["needs_reply"]:
        badges.append(":green-badge[회신 대상]")
    st.markdown(" ".join(badges))


def render_urgency_reasons(item: dict[str, Any]) -> None:
    reasons = item.get("urgency_reasons") or []
    if reasons:
        st.caption("  ·  ".join(reasons))


CONFIRM_BUCKET = "사용자 확인 필요"


def confirmation_items(classification: dict[str, Any]) -> list[str]:
    """사람이 직접 확인해야 하는 것만 추린다.

    `evidence`는 decision-rules.md의 네 버킷으로 오는데, 그중 `사용자 확인 필요`만 남긴다.
    나머지 세 버킷(확인된 사실·추론·누락 정보)은 판단의 근거라서 목록 화면에서는 빼고,
    필요하면 원본 메일을 펼쳐 직접 본다.
    """
    items: list[str] = []
    evidence = classification.get("evidence")
    if isinstance(evidence, list):
        for entry in evidence:
            if isinstance(entry, dict):
                bucket = str(entry.get("type") or entry.get("kind") or "")
                if bucket == CONFIRM_BUCKET:
                    items.append(as_text(entry.get("value", entry)))
    elif isinstance(evidence, dict) and evidence.get(CONFIRM_BUCKET):
        value = evidence[CONFIRM_BUCKET]
        items.extend(
            as_text(v) for v in (value if isinstance(value, list) else [value])
        )
    # Skill이 별도 필드로 주는 경우도 받아준다.
    extra = classification.get("user_confirmation")
    if extra:
        items.extend(as_text(v) for v in (extra if isinstance(extra, list) else [extra]))
    return [item for item in items if item]


def render_item_body(item: dict[str, Any]) -> None:
    classification = item["classification"] or {}
    render_badges(item)
    render_urgency_reasons(item)

    meta = [f"**From** {item['sender'] or '알 수 없음'}"]
    if item["received_at"]:
        meta.append(f"**수신** {item['received_at']}")
    st.markdown("  ·  ".join(meta))
    if item["subject"] and item["subject"] != item["title"]:
        st.caption(f"원문 제목: {item['subject']}")

    if item["status"] == "pending":
        st.info("아직 분류하지 않았습니다.")
    if classification.get("summary"):
        st.markdown(as_text(classification["summary"]))

    confirmations = confirmation_items(classification)
    if confirmations:
        st.markdown("**사용자 확인 필요**")
        st.markdown("\n".join(f"- {entry}" for entry in confirmations))
    for flag in classification.get("safety_flags") or []:
        st.warning(as_text(flag))
    for error in classification.get("errors") or []:
        st.caption(f"⚠️ {as_text(error)}")


def render_original_email(item: dict[str, Any]) -> None:
    """원본 메일을 접어서 보여준다.

    본문은 신뢰할 수 없는 데이터라 마크다운으로 해석하지 않는다. 비활성 text_area를 쓰면
    줄바꿈이 유지되면서 서식이 실행되지 않는다.
    """
    email = item["email"]
    st.caption("원본 메일")
    meta = [f"**보낸 사람** {email['sender'] or '알 수 없음'}"]
    recipients = email.get("recipients") or []
    if recipients:
        meta.append(f"**받는 사람** {', '.join(str(r) for r in recipients)}")
    if email.get("received_at"):
        meta.append(f"**수신** {email['received_at']}")
    st.markdown("  \n".join(meta))
    if email.get("subject"):
        st.markdown(f"**제목** {email['subject']}")

    body = str(email.get("body") or "").strip()
    if body:
        st.text_area(
            "본문",
            value=body,
            height=min(420, 90 + 18 * body.count("\n")),
            disabled=True,
            key=f"body_{item['case_id']}",
            label_visibility="collapsed",
        )
    else:
        st.caption("본문이 없습니다.")

    attachments = email.get("attachments") or []
    if attachments:
        st.markdown("**첨부**  \n" + "\n".join(f"- {a}" for a in attachments))

    thread = email.get("thread") or []
    if thread:
        st.markdown(f"**이전 대화 {len(thread)}건**")
        for entry in thread:
            if isinstance(entry, dict):
                who = entry.get("sender") or entry.get("from") or "알 수 없음"
                when = short_date(str(entry.get("received_at") or ""))
                st.caption(f"{who}  ·  {when}")
                st.text(str(entry.get("body") or entry.get("snippet") or "").strip())
            else:
                st.text(str(entry))


# 목록의 행 버튼만 왼쪽 정렬한다. Streamlit 버튼은 라벨을 가운데 두는데, 메일 목록에서는
# 제목이 줄마다 다른 위치에서 시작해 훑기가 어렵다. 모델이 만든 문자열이 아니라 고정 CSS다.
#
# 셀렉터 주의: 버튼의 test id는 `stBaseButton-<kind>`(secondary/primary/tertiary)라서
# 접두사 매칭이 필요하다. `data-testid="stButton"`은 존재하지 않는다.
# 스코프는 `st.container(key="mail-rows")`가 만드는 `.st-key-mail-rows` 클래스다.
ROW_STYLE = """
<style>
.st-key-mail-rows button[data-testid^="stBaseButton-"] {
    justify-content: flex-start !important;
    text-align: left !important;
}
.st-key-mail-rows button[data-testid^="stBaseButton-"] > div {
    width: 100%;
    justify-content: flex-start !important;
}
.st-key-mail-rows button[data-testid^="stBaseButton-"] p {
    text-align: left !important;
    width: 100%;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>
"""


def render_draft(record: dict[str, Any]) -> None:
    """회신 초안 하나. 본문은 편집 가능한 text_area로 두되 발송은 하지 않는다."""
    if record["status"] == "error":
        st.error(record.get("error") or "초안을 만들지 못했습니다.")
        return

    draft = record.get("draft")
    review = record.get("review") or {}
    if draft is None:
        status = str(review.get("review_status") or "")
        if status == "READY_FOR_APPROVAL_REVIEW":
            st.success("보완할 항목이 없어 초안을 만들지 않았습니다. 승인 검토로 넘어가면 됩니다.")
            guidance = review.get("approval_guidance") or {}
            if isinstance(guidance, dict) and guidance.get("summary"):
                st.markdown(as_text(guidance["summary"]))
                if guidance.get("url"):
                    st.markdown(f"[승인 화면 열기]({guidance['url']})")
        else:
            st.info("이 건에는 보낼 초안이 없습니다.")
        return

    if draft.get("to"):
        st.markdown(f"**받는 사람** {draft['to']}")
    if draft.get("subject"):
        st.markdown(f"**제목** {draft['subject']}")
    st.text_area(
        "본문", value=draft["body"], height=260,
        key=f"draft_body_{record['case_id']}", label_visibility="collapsed",
    )
    st.caption("초안입니다. 검토 후 직접 발송하세요. 이 화면은 메일을 보내지 않습니다.")


def render_failures(failures: Sequence[dict[str, Any]]) -> None:
    if not failures:
        return
    st.divider()
    st.subheader(f"실패 ({len(failures)}건)")
    st.caption("긴급도와 분류가 없어 순위에 넣지 않았습니다.")
    for item in failures:
        with st.expander(f"❌ {item['title']}", expanded=False):
            st.error(item.get("error") or "알 수 없는 실패")
            if item.get("text"):
                st.code(item["text"][:2000], language="text")


def render_top_amounts(summary: dict[str, Any]) -> None:
    top = summary.get("top_amounts") or []
    if not top:
        st.caption("본문에서 금액을 읽어낸 구매 건이 없습니다.")
        return
    st.dataframe(
        [
            {"순위": index + 1, "제목": item["title"], "금액(원)": item["amount"].value,
             "발신": item["sender"]}
            for index, item in enumerate(top)
        ],
        hide_index=True,
        column_config={
            "순위": st.column_config.NumberColumn(width="small"),
            "제목": st.column_config.TextColumn(width="large"),
            "금액(원)": st.column_config.NumberColumn(format="localized"),
            "발신": st.column_config.TextColumn(width="small"),
        },
    )


STAGE_VIEW: dict[str, tuple[str, str]] = {
    "todo": ("📌 회신 검토 필요", "회신 메일을 만들 수 있는 건입니다. 눌러서 선택하세요."),
    "done": ("✅ 회신 검토 완료", "펼치면 어떻게 처리했는지 볼 수 있습니다."),
    "none": ("➖ 처리할 내용 없음", "브리핑으로 끝나는 건입니다."),
    "unsupported": ("🕓 내용 요약 검토 필요", "논의 내용을 요약할 수 있는 건입니다. 눌러서 선택하세요."),
    "error": ("❌ 처리 실패", "다시 시도할 수 있습니다."),
    "pending": ("· 분류 전", "아직 분류하지 않았습니다."),
}
# 화면에 나오는 순서. 할 일이 맨 위다.
STAGE_ORDER = ("todo", "error", "done", "unsupported", "none", "pending")


def stage_caption(stage: str) -> tuple[str, str]:
    return STAGE_VIEW.get(stage, (stage, ""))


def render_headline(summary: dict[str, Any]) -> None:
    """목록 위에 먼저 나오는 요약.

    분류를 돌리기 전에는 건수만 보여준다. 긴급도·회신 필요·금액은 전부 본문을 읽어야
    나오는 값이라, 분류 전에 채워 넣으면 아직 하지 않은 판단을 한 척하게 된다.
    """
    if not summary["classified"]:
        st.metric("메일", summary["total"])
        st.caption("아직 분류하지 않았습니다. 제목·발신·날짜만 알고 있습니다.")
        return
    columns = st.columns(4)
    columns[0].metric("전체", summary["total"])
    columns[1].metric("긴급", summary["urgent"])
    columns[2].metric("회신 필요", summary["needs_reply"])
    total = summary["amount_total"]
    columns[3].metric(
        "금액 합계", f"{total:,}원" if total else "—",
        help=f"본문에서 금액을 읽어낸 {summary['amount_known']}건 기준",
    )
    if summary["unclassified"]:
        st.caption(f"미분류 {summary['unclassified']}건이 남아 있습니다.")
