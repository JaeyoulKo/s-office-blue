from __future__ import annotations

import json

import streamlit as st

from main_service.codex_runner import CodexResult
from main_service.service import classify_email, draft_clarification, review_purchase_email
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
    st.caption("합성 이메일로 분리된 Skill과 Codex 실행 흐름을 확인하는 Streamlit 템플릿")

    samples = sorted(DATA_DIR.glob("*.json"))
    if not samples:
        st.error("data/synthetic/emails에 JSON 샘플이 없습니다.")
        return

    with st.sidebar:
        selected = st.selectbox("합성 이메일", samples, format_func=lambda path: path.stem)
        model_text = st.text_input("Codex model (선택)", value="")
        st.caption("비워 두면 로컬 Codex 기본 모델을 사용합니다.")

    email = json.loads(selected.read_text(encoding="utf-8"))
    sample_key = str(selected)
    if st.session_state.get("sample_key") != sample_key:
        st.session_state.sample_key = sample_key
        st.session_state.classification = None
        st.session_state.review = None
        st.session_state.draft = None

    st.subheader("입력")
    st.json(email)
    model = model_text.strip() or None

    actions = st.columns(3)
    if actions[0].button("1. 분류 실행", use_container_width=True):
        with st.spinner("email-classifier 실행 중"):
            try:
                st.session_state.classification = classify_email(email, model)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")

    if actions[1].button("2. 구매 검토", use_container_width=True):
        classification = st.session_state.get("classification")
        if classification is None:
            st.warning("먼저 분류를 실행하세요.")
        else:
            with st.spinner("purchase-email-review 실행 중"):
                try:
                    st.session_state.review = review_purchase_email(
                        email, classification.display_value(), model
                    )
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}")

    if actions[2].button("3. 보완 초안", use_container_width=True):
        review = st.session_state.get("review")
        if review is None:
            st.warning("먼저 구매 검토를 실행하세요.")
        else:
            with st.spinner("clarification-draft 실행 중"):
                try:
                    st.session_state.draft = draft_clarification(
                        review.display_value(), model
                    )
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}")

    columns = st.columns(3)
    with columns[0]:
        st.subheader("분류")
        show_result(st.session_state.get("classification"))
    with columns[1]:
        st.subheader("구매 검토")
        show_result(st.session_state.get("review"))
    with columns[2]:
        st.subheader("보완 초안")
        show_result(st.session_state.get("draft"))


if __name__ == "__main__":
    main()
