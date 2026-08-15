from __future__ import annotations

import json

import streamlit as st

from main_service.codex_runner import CodexResult
from main_service.service import (
    classify_email,
    load_gmail_inbox,
    review_discussion_email,
    review_purchase_email,
)
from main_service.skill_registry import PROJECT_ROOT


DATA_DIR = PROJECT_ROOT / "data" / "synthetic" / "emails"


def show_result(result: CodexResult | None) -> None:
    if result is None:
        st.caption("아직 실행하지 않았습니다.")
    elif result.parsed is not None:
        st.json(result.parsed)
    else:
        st.code(result.text, language="text")


def main() -> None:
    st.set_page_config(page_title="Office Blue", layout="wide")
    st.title("Office Blue")
    st.caption("기존 구매 이메일 규칙을 기능별 국문 Skill로 나눈 Streamlit 템플릿")

    samples = sorted(DATA_DIR.glob("*.json"))
    if not samples:
        st.error("data/synthetic/emails에 JSON 샘플이 없습니다.")
        return

    with st.sidebar:
        source = st.radio("입력 소스", ("합성 데이터", "Gmail 받은편지함"))
        if source == "Gmail 받은편지함":
            gmail_query = st.text_input(
                "Gmail 검색어", value="in:inbox is:unread newer_than:7d"
            )
            if st.button("Gmail 새로고침", use_container_width=True):
                with st.spinner("Gmail을 읽고 있습니다..."):
                    try:
                        st.session_state.gmail_messages = load_gmail_inbox(gmail_query)
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
            gmail_messages = st.session_state.get("gmail_messages", [])
            if not gmail_messages:
                st.info("새로고침을 눌러 Gmail을 불러오세요.")
                return
            selected_index = st.selectbox(
                "Gmail 이메일",
                range(len(gmail_messages)),
                format_func=lambda index: gmail_messages[index].get("subject") or "(제목 없음)",
            )
            email = gmail_messages[selected_index]
            selected_key = f"gmail:{email.get('message_id', selected_index)}"
        else:
            selected = st.selectbox("합성 이메일", samples, format_func=lambda path: path.stem)
            email = json.loads(selected.read_text(encoding="utf-8"))
            selected_key = f"synthetic:{selected}"
        model_text = st.text_input("Codex 모델(선택)", value="")
        st.caption("비워 두면 로컬 Codex 기본 모델을 사용합니다.")

    if st.session_state.get("sample_key") != selected_key:
        st.session_state.sample_key = selected_key
        st.session_state.classification = None
        st.session_state.purchase_review = None
        st.session_state.discussion_review = None

    st.subheader("입력")
    st.json(email)
    model = model_text.strip() or None
    actions = st.columns(3)

    if actions[0].button("1. 메일 분류", use_container_width=True):
        with st.spinner("메일 분류 Skill 실행 중"):
            try:
                st.session_state.classification = classify_email(email, model)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")

    classification = st.session_state.get("classification")
    if actions[1].button("2. 구매·계약 검토", use_container_width=True):
        if classification is None:
            st.warning("먼저 메일을 분류하세요.")
        else:
            with st.spinner("구매 이메일 검토 Skill 실행 중"):
                try:
                    st.session_state.purchase_review = review_purchase_email(
                        email, classification.display_value(), model
                    )
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}")

    if actions[2].button("3. 논의·질의 검토", use_container_width=True):
        if classification is None:
            st.warning("먼저 메일을 분류하세요.")
        else:
            with st.spinner("논의 이메일 검토 Skill 실행 중"):
                try:
                    st.session_state.discussion_review = review_discussion_email(
                        email, classification.display_value(), model
                    )
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}")

    columns = st.columns(3)
    with columns[0]:
        st.subheader("분류")
        show_result(st.session_state.get("classification"))
    with columns[1]:
        st.subheader("구매·계약 검토")
        show_result(st.session_state.get("purchase_review"))
    with columns[2]:
        st.subheader("논의·질의 검토")
        show_result(st.session_state.get("discussion_review"))


if __name__ == "__main__":
    main()
