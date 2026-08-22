from __future__ import annotations

from datetime import date, datetime
from html import escape

import streamlit as st

from experiments.ablation.skill_ab_test.excel_export import build_with_skill_workbook
from experiments.ablation.skill_ab_test.presentation import USER_SUMMARY_FIELDS, format_summary_field
from experiments.ablation.skill_ab_test.runner import run_ab_test
from experiments.ablation.skill_ab_test.synthetic_fixtures import load_synthetic_scenarios


def _render_thread(scenario: object) -> None:
    with st.expander("이메일 Thread 보기", expanded=False):
        messages = sorted(scenario.thread.messages, key=lambda item: datetime.fromisoformat(item.sent_at))
        for index, message in enumerate(messages, start=1):
            title = message.subject or f"이메일 {index}"
            with st.expander(f"{index}. {title}", expanded=index == len(messages)):
                if message.sender:
                    st.markdown("**발신자**")
                    st.write(message.sender)
                if message.sent_at:
                    st.markdown("**날짜**")
                    st.write(message.sent_at)
                if message.body_text:
                    st.markdown("**본문**")
                    st.markdown(message.body_text.replace("\n", "  \n"))
                file_names = [item.file_name for item in message.attachments if item.file_name]
                if file_names:
                    st.markdown("**첨부파일**")
                    for file_name in file_names:
                        st.write(f"📎 {file_name}")


def _value_html(value: str | list[str]) -> str:
    if isinstance(value, list):
        items = "".join(f"<li>{escape(item)}</li>" for item in value)
        return f'<ul class="ab-value-list">{items}</ul>'
    return f'<div class="ab-value-text">{escape(value).replace(chr(10), "<br>")}</div>'


def _render_comparison(with_skill: dict[str, object], without_skill: dict[str, object]) -> None:
    cells = [
        '<div class="ab-title ab-a-title">A · WITH SKILL</div>',
        '<div class="ab-title ab-b-title">B · WITHOUT SKILL</div>',
        '<div class="ab-column-head ab-a-cell ab-a-label">항목</div>',
        '<div class="ab-column-head ab-a-cell ab-a-content">내용</div>',
        '<div class="ab-column-head ab-b-cell ab-b-label">항목</div>',
        '<div class="ab-column-head ab-b-cell ab-b-content">내용</div>',
    ]
    for field in USER_SUMMARY_FIELDS:
        cells.extend([
            f'<div class="ab-cell ab-a-cell ab-a-label">{escape(field)}</div>',
            '<div class="ab-cell ab-a-cell ab-a-content">'
            f'{_value_html(format_summary_field(field, with_skill))}</div>',
            f'<div class="ab-cell ab-b-cell ab-b-label">{escape(field)}</div>',
            '<div class="ab-cell ab-b-cell ab-b-content">'
            f'{_value_html(format_summary_field(field, without_skill))}</div>',
        ])
    st.markdown(
        """
        <style>
        .ab-comparison-grid {
            display: grid;
            grid-template-columns: minmax(7.5rem, 0.34fr) minmax(0, 1fr)
                                   2rem
                                   minmax(7.5rem, 0.34fr) minmax(0, 1fr);
            align-items: stretch;
            width: 100%;
            margin: 1rem 0 1.25rem;
        }
        .ab-title {
            padding: 0.85rem 1rem;
            border: 1px solid;
            border-radius: 0.6rem 0.6rem 0 0;
            font-weight: 700;
            font-size: 1.05rem;
        }
        .ab-a-title { grid-column: 1 / 3; background: #eaf3ff; border-color: #b9d3ef; }
        .ab-b-title { grid-column: 4 / 6; background: #f1f3f5; border-color: #cfd4da; }
        .ab-cell, .ab-column-head {
            min-width: 0;
            padding: 0.75rem;
            border-style: solid;
            border-width: 0 1px 1px 0;
            background: #ffffff;
            overflow-wrap: anywhere;
            word-break: normal;
            white-space: normal;
        }
        .ab-column-head { font-weight: 700; text-align: center; }
        .ab-a-cell { border-color: #c9ddf2; }
        .ab-b-cell { border-color: #d9dde2; }
        .ab-a-label, .ab-b-label {
            border-left-width: 1px;
            font-weight: 650;
        }
        .ab-a-label { grid-column: 1; background: #f6faff; }
        .ab-a-content { grid-column: 2; }
        .ab-b-label { grid-column: 4; background: #f7f8f9; }
        .ab-b-content { grid-column: 5; }
        .ab-value-list { margin: 0; padding-left: 1.2rem; }
        .ab-value-list li + li { margin-top: 0.35rem; }
        .ab-value-text { margin: 0; }
        </style>
        <div class="ab-comparison-grid">
        """ + "".join(cells) + "</div>",
        unsafe_allow_html=True,
    )


def _store_result(scenario: object, result: dict[str, object]) -> None:
    st.session_state.email_archive_ab_result = result
    st.session_state.email_archive_ab_scenario = scenario.scenario_id
    st.session_state.email_archive_ab_excel = build_with_skill_workbook(result["with_skill"])
    st.session_state.email_archive_ab_excel_name = (
        f"{scenario.scenario_id}_with_skill_{date.today().isoformat()}.xlsx"
    )


def main() -> None:
    st.set_page_config(page_title="Email Archive A/B 비교", page_icon="✉️", layout="wide")
    st.title("Email Archive A/B 비교")
    st.caption("같은 이메일 Thread를 Skill 적용 여부에 따라 비교합니다.")

    scenarios = load_synthetic_scenarios()
    if not scenarios:
        st.error("표시할 이메일 Thread가 없습니다.")
        return
    scenario_by_label = {item.label: item for item in scenarios}
    selected_label = st.selectbox("비교할 이메일 Thread", list(scenario_by_label))
    scenario = scenario_by_label[selected_label]

    _render_thread(scenario)

    if st.button("A/B 분석 실행", type="primary"):
        with st.spinner("이메일 Thread 분석 중..."):
            try:
                _store_result(scenario, run_ab_test(scenario.thread.to_dict()))
            except Exception as exc:
                st.error(f"A/B 분석에 실패했습니다: {exc}")

    if st.session_state.get("email_archive_ab_scenario") != scenario.scenario_id:
        return
    result = st.session_state.get("email_archive_ab_result")
    if not result:
        return
    _render_comparison(result["with_skill"], result["without_skill"])

    st.download_button(
        "A 결과 Excel 다운로드",
        data=st.session_state.email_archive_ab_excel,
        file_name=st.session_state.email_archive_ab_excel_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


if __name__ == "__main__":
    main()
