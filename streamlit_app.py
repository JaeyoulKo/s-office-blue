from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st

from archive.analyzer import FixtureArchiveAnalyzer
from archive.models import ArchiveResult, EmailThread, ThreadAnalysis
from archive.service import ArchiveService
from archive.storage import ExcelRecordRepository


PROJECT_ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures"
FIXTURES = {
    "Project Blue · initial request": ("thread_initial.json", "analysis_initial.json"),
    "Project Blue · thread update": ("thread_update.json", "analysis_update.json"),
    "Project Blue · ambiguous candidate": ("thread_ambiguous.json", "analysis_initial.json"),
}


def repository() -> ExcelRecordRepository:
    root = Path(os.environ.get("ARCHIVE_REPOSITORY_ROOT", PROJECT_ROOT)).resolve()
    configured = os.environ.get("ARCHIVE_WORKBOOK", "artifacts/email_archive_streamlit.xlsx")
    workbook = Path(configured)
    if not workbook.is_absolute():
        workbook = root / workbook
    return ExcelRecordRepository(workbook, root)


def fixture_service(selection: str) -> tuple[EmailThread, ArchiveService]:
    thread_name, analysis_name = FIXTURES[selection]
    thread = EmailThread.model_validate_json(
        (FIXTURE_ROOT / thread_name).read_text(encoding="utf-8")
    )
    analysis = ThreadAnalysis.model_validate_json(
        (FIXTURE_ROOT / analysis_name).read_text(encoding="utf-8")
    )
    service = ArchiveService(FixtureArchiveAnalyzer(analysis), repository())
    return thread, service


def render_list(title: str, values: list[str]) -> None:
    st.subheader(title)
    if values:
        for value in values:
            st.markdown(f"- {value}")
    else:
        st.caption("확인된 항목이 없습니다.")


def render_match(result: ArchiveResult) -> None:
    match = result.record_match
    st.subheader("Archive Record Match")
    columns = st.columns(3)
    columns[0].metric("Decision", match.decision)
    columns[1].metric("Search", match.search_status)
    columns[2].metric("Record ID", match.selected_record_id)

    if match.decision == "ambiguous":
        st.warning("additional confirmation required — 자동 신규 생성 및 merge가 차단되었습니다.")
    elif match.decision == "same_record":
        st.info(f"Existing Record: {match.selected_record_id}")
    else:
        st.success("새 Archive Record 후보입니다.")

    for candidate in match.candidates:
        with st.expander(f"Candidate {candidate.record_id} · {candidate.confidence}"):
            if candidate.matching_evidence:
                st.markdown("**Matching evidence**")
                st.dataframe(
                    [item.model_dump(mode="json") for item in candidate.matching_evidence],
                    width="stretch",
                    hide_index=True,
                )
            if candidate.conflicting_evidence:
                st.markdown("**Conflicting evidence**")
                st.dataframe(
                    [item.model_dump(mode="json") for item in candidate.conflicting_evidence],
                    width="stretch",
                    hide_index=True,
                )


def render_record(result: ArchiveResult, archive_repository: ExcelRecordRepository) -> None:
    record = result.archive_record
    if record is None:
        st.info("표시할 Archive Record가 없습니다.")
        return

    st.header(record.title)
    st.caption(
        f"Requester: {record.requester} · Status: {record.current_status} · "
        f"Updated: {record.latest_update_date}"
    )
    st.markdown("**Participants**")
    st.write(", ".join(record.participants) if record.participants else "확인되지 않음")

    st.subheader("Thread Summary")
    st.write(record.thread_summary)

    left, right = st.columns(2)
    with left:
        render_list("Key Points", record.key_points)
        render_list("Decisions", record.decisions)
    with right:
        render_list("Open Items", record.open_items)
        render_list("Due Dates", record.due_dates)

    st.subheader("Action Items")
    if record.action_items:
        st.dataframe(
            [item.model_dump(mode="json") for item in record.action_items],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("확인된 Action Item이 없습니다.")

    st.subheader("Important Numbers")
    if record.important_numbers:
        st.dataframe(
            [item.model_dump(mode="json") for item in record.important_numbers],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("확인된 주요 수치가 없습니다.")

    st.subheader("Attachments")
    if record.attachments:
        st.dataframe(
            [item.model_dump(mode="json", exclude={"extracted_text"}) for item in record.attachments],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("첨부파일이 없습니다.")

    changes = result.record_update.field_changes if result.record_update else []
    stored_history = []
    if result.record_match.decision == "same_record":
        stored_history = archive_repository.list_change_history(result.record_match.selected_record_id)
    history = _unique_changes([*changes, *stored_history])
    if history:
        st.subheader("Change History")
        st.dataframe(
            [item.model_dump(mode="json") for item in history],
            width="stretch",
            hide_index=True,
        )

    if result.conflicts:
        st.error("Conflicts\n\n" + "\n".join(f"- {item}" for item in result.conflicts))
    if result.limitations:
        st.warning("Limitations\n\n" + "\n".join(f"- {item}" for item in result.limitations))


def _unique_changes(changes: list[Any]) -> list[Any]:
    seen: set[str] = set()
    unique = []
    for change in changes:
        key = json.dumps(change.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(change)
    return unique


def main() -> None:
    st.set_page_config(page_title="Email Archive", page_icon="📨", layout="wide")
    st.title("Email Archive Review")
    st.caption("Fixture input provider · Gmail MCP 연결 전 개발 및 테스트 전용")

    selection = st.selectbox("이메일 / Thread 선택", list(FIXTURES), key="fixture_selection")
    if st.session_state.get("active_selection") != selection:
        st.session_state.pop("archive_result", None)
        st.session_state.pop("save_result", None)

    if st.button("Analyze Archive", type="primary", key="analyze_archive"):
        try:
            thread, service = fixture_service(selection)
            st.session_state.archive_result = service.process(thread, write=False)
            st.session_state.active_selection = selection
            st.session_state.pop("save_result", None)
        except Exception as error:
            st.error(f"Archive 분석 실패: {error}")

    result: ArchiveResult | None = st.session_state.get("archive_result")
    if result is None:
        st.info("Thread를 선택하고 Analyze Archive를 실행하세요.")
        return

    status_tone = {
        "new_record_ready": st.success,
        "record_update_ready": st.info,
        "additional_confirmation_required": st.warning,
        "saved": st.success,
    }.get(result.result_status, st.info)
    status_tone(f"Result status: {result.result_status}")

    active_repository = repository()
    render_match(result)
    render_record(result, active_repository)

    ambiguous = result.result_status == "additional_confirmation_required"
    if ambiguous:
        st.caption("후보 Record 확인 전에는 저장할 수 없습니다.")

    if st.button(
        "Save Archive",
        disabled=ambiguous,
        type="primary",
        key="save_archive",
        help="클릭은 표시된 Archive Preview의 명시적 Excel write 승인으로 처리됩니다.",
    ):
        try:
            thread, service = fixture_service(selection)
            saved = service.process(thread, write=True)
            st.session_state.archive_result = saved
            st.session_state.save_result = saved
        except Exception as error:
            st.error(f"Archive 저장 실패: {error}")

    saved: ArchiveResult | None = st.session_state.get("save_result")
    if saved and saved.storage.executed:
        st.success(
            f"Archive 저장 완료 · {saved.storage.operation} · "
            f"Record ID {saved.storage.saved_record_id}"
        )
        st.caption(f"Workbook: {saved.storage.destination}")


if __name__ == "__main__":
    main()
