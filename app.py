from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from office_blue.models import EmailMessage  # noqa: E402
from office_blue.ariba_sample_adapter import is_ariba_sample_list, message_from_ariba_sample  # noqa: E402
from office_blue.codex_gmail_bridge import fetch_gmail_snapshot  # noqa: E402
from office_blue.gmail_adapter import message_from_gmail_mcp  # noqa: E402
from office_blue.reviewer import review_email  # noqa: E402


st.set_page_config(page_title="Office Blue", page_icon="✉️", layout="wide")
st.title("Ariba 이메일 보완 검토")
st.caption("구매 이메일의 미비 항목을 찾고 사용자 검토용 답장 초안을 만듭니다.")

with st.expander("Gmail MCP 받은편지함", expanded=True):
    gmail_query = st.text_input(
        "Gmail 검색어",
        value="in:inbox is:unread newer_than:7d (Ariba OR 구매 OR 승인 OR purchase OR approval)",
    )
    if st.button("Gmail 새로고침"):
        with st.spinner("Gmail MCP에서 메일을 읽고 있습니다..."):
            try:
                st.session_state.gmail_messages = fetch_gmail_snapshot(gmail_query)
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
            else:
                st.success(f"{len(st.session_state.gmail_messages)}개 메일을 불러왔습니다.")

gmail_messages = st.session_state.get("gmail_messages", [])
imported = None
if gmail_messages:
    selected_index = st.selectbox(
        "검토할 Gmail 메시지",
        range(len(gmail_messages)),
        format_func=lambda index: gmail_messages[index].get("subject") or "(제목 없음)",
    )
    try:
        imported = message_from_gmail_mcp(gmail_messages[selected_index])
    except (ValueError, TypeError) as exc:
        st.error(f"Gmail MCP 메시지를 변환할 수 없습니다: {exc}")

uploaded = st.file_uploader("Gmail MCP 메시지 JSON 가져오기", type="json")
if uploaded is not None:
    try:
        uploaded_data = json.load(uploaded)
        if is_ariba_sample_list(uploaded_data):
            sample_index = st.selectbox(
                "검토할 Ariba 샘플",
                range(len(uploaded_data)),
                format_func=lambda index: (
                    f"{uploaded_data[index].get('pr_number')} · "
                    f"{uploaded_data[index].get('email_subject', '(제목 없음)')}"
                ),
            )
            imported = message_from_ariba_sample(uploaded_data[sample_index])
            st.success(f"Ariba 샘플 {len(uploaded_data)}건을 불러왔습니다.")
        elif isinstance(uploaded_data, dict):
            imported = message_from_gmail_mcp(uploaded_data)
            st.success("Gmail MCP 메시지를 불러왔습니다.")
        else:
            raise ValueError("지원하지 않는 JSON 구조입니다.")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        st.error(f"JSON 메시지를 불러올 수 없습니다: {exc}")

with st.form("email_review"):
    left, right = st.columns(2)
    with left:
        sender = st.text_input("발신자", value=imported.sender if imported else "", placeholder="requester@example.com")
        subject = st.text_input("제목", value=imported.subject if imported else "", placeholder="노트북 구매 요청")
    with right:
        message_id = st.text_input("Gmail 메시지 ID", value=imported.message_id if imported else "manual-input")
        thread_id = st.text_input("Gmail 스레드 ID", value=imported.thread_id if imported else "manual-thread")
    body = st.text_area(
        "이메일 본문",
        value=imported.body if imported else "",
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
