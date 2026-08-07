from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from office_blue.models import EmailMessage  # noqa: E402
from office_blue.reviewer import review_email  # noqa: E402


st.set_page_config(page_title="Office Blue", page_icon="✉️", layout="wide")
st.title("Ariba 이메일 보완 검토")
st.caption("구매 이메일의 미비 항목을 찾고 사용자 검토용 답장 초안을 만듭니다.")

with st.form("email_review"):
    left, right = st.columns(2)
    with left:
        sender = st.text_input("발신자", placeholder="requester@example.com")
        subject = st.text_input("제목", placeholder="노트북 구매 요청")
    with right:
        message_id = st.text_input("Gmail 메시지 ID", value="manual-input")
        thread_id = st.text_input("Gmail 스레드 ID", value="manual-thread")
    body = st.text_area(
        "이메일 본문",
        height=260,
        placeholder="품목: 개발용 노트북\n목적: 신규 입사자 업무용\n수량: 3개",
    )
    submitted = st.form_submit_button("미비 항목 검토", type="primary")

if submitted:
    try:
        message = EmailMessage.from_dict(
            {
                "message_id": message_id,
                "thread_id": thread_id,
                "sender": sender,
                "subject": subject,
                "body": body,
            }
        )
    except ValueError as exc:
        st.error(str(exc))
    else:
        result = review_email(message)
        st.subheader("검토 결과")
        col1, col2, col3 = st.columns(3)
        col1.metric("분류", result.classification)
        col2.metric("검토 상태", result.status)
        col3.metric("업무 상태", result.workflow_state)

        if result.confirmed_facts:
            st.markdown("#### 확인된 정보")
            st.json(result.confirmed_facts)

        if result.missing_fields:
            st.markdown("#### 미비 항목")
            for item in result.missing_fields:
                with st.container(border=True):
                    st.markdown(f"**{item.field}**")
                    st.write(item.reason)
                    st.caption(item.question)

        if result.reply_draft:
            st.markdown("#### 자동 답장 초안")
            st.info("초안만 생성되었습니다. 검토 및 명시적 승인 전에는 발송되지 않습니다.")
            st.text_input("받는 사람", value=result.reply_draft.to, disabled=True)
            st.text_input("답장 제목", value=result.reply_draft.subject, disabled=True)
            st.text_area("답장 본문", value=result.reply_draft.body, height=280)
            st.warning("현재 상태: WAITING_FOR_USER_APPROVAL")
        elif result.status in {"검토 가능", "승인 검토 가능"}:
            st.success("필수 정보가 확인되어 보완 요청 초안이 필요하지 않습니다.")
