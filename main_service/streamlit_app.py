from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from main_service.codex_runner import CodexResult, codex_version
from main_service.archive_result import is_canonical_archive_result
from main_service.email_archive_excel import (
    EmailArchiveExcelStore,
    EMPTY_VALUE as ARCHIVE_EMPTY_VALUE,
    archive_save_candidates,
    formatted_amount,
    natural_language_items,
)
from main_service.emails import (
    LABELS,
    amount_ranks,
    build_briefing,
    load_inbox,
    load_sources,
    rank_briefings,
    summarize,
)
from main_service.render import (
    REPLY_WAIT_MESSAGES,
    ROW_STYLE,
    STAGE_ORDER,
    WAIT_MESSAGES,
    classified_line,
    item_header,
    progress_text,
    render_counts,
    render_headline,
    render_failures,
    render_item_body,
    render_draft,
    render_original_email,
    reply_line,
    stage_caption,
    render_top_amounts,
    wait_message,
)
from main_service.replies import mail_stage
from main_service.service import (
    DEFAULT_MAX_WORKERS,
    GMAIL_DEFAULT_QUERY,
    MAX_PARALLEL,
    archive_discussion_emails,
    can_reply,
    classify_email,
    classify_emails,
    draft_replies,
    fetch_inbox,
    purchase_draft_fingerprint,
    review_discussion_email,
    review_purchase_email,
    save_purchase_review_draft,
    supported_labels,
)
from main_service.skill_registry import PROJECT_ROOT

DATA_DIR = PROJECT_ROOT / "data" / "synthetic" / "emails"
ARCHIVE_LABEL = "논의 내용 요약 필요 이메일"


# ------------------------------------------------------------------ 목록 · 분류 · 정렬


class BatchJob:
    """오래 걸리는 배치를 백그라운드 스레드에서 돌린다.

    메인 스크립트 스레드에서 `as_completed`를 기다리면 그 동안 Streamlit이 아무것도
    다시 그릴 수 없어서, 경과 시간이 완료 시점에만 껑충 뛴다. 배치를 스레드로 빼고
    이벤트를 큐로 넘기면 `st.fragment(run_every=1)`이 1초마다 화면을 갱신할 수 있다.

    워커 스레드는 `st.*`도 `session_state`도 건드리지 않는다. 평범한 Queue와 이 객체의
    필드만 쓰고, 화면 갱신은 전부 fragment(메인 스레드)에서 한다.

    분류와 회신 생성이 같은 구조라 `runner`만 갈아끼운다.
    """

    def __init__(
        self,
        *,
        kind: str,
        total: int,
        senders: dict[str, str],
        runner: Callable[[Callable[[dict[str, Any]], None]], Any],
    ) -> None:
        self.kind = kind
        self.total = total
        # 로그에 case_id(해시처럼 보이는 값)를 찍어봐야 사람이 못 알아본다. 보낸 사람을 쓴다.
        self.senders = senders
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.records: dict[str, dict[str, Any]] = {}
        self.log: list[str] = []
        self.done = 0
        self.failed = 0
        self.error: str | None = None
        self.finished = False
        self.started = time.perf_counter()
        self.thread = threading.Thread(
            target=self._run, args=(runner,), name=f"batch-{kind}", daemon=True
        )
        self.thread.start()

    def _run(self, runner: Callable[[Callable[[dict[str, Any]], None]], Any]) -> None:
        try:
            runner(self.queue.put)
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self.queue.put({"state": "finished"})

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.started

    def _line(self, record: dict[str, Any]) -> str:
        sender = self.senders.get(record["case_id"], "")
        ok = record["status"] == "ok"
        if self.kind == "archive":
            return "아카이빙 분석을 완료했습니다." if ok else "아카이빙 분석에 실패했습니다."
        if self.kind == "reply":
            return reply_line(sender, ok=ok)
        classification = record.get("classification") or {}
        label = str(classification.get("label") or "") if isinstance(classification, dict) else ""
        return classified_line(sender, label, ok=ok)

    def drain(self) -> None:
        """큐에 쌓인 이벤트를 메인 스레드에서 반영한다."""
        while True:
            try:
                event = self.queue.get_nowait()
            except queue.Empty:
                return
            if event.get("state") == "finished":
                self.finished = True
                continue
            record = event.get("record")
            if record is None:
                continue
            self.records[record["case_id"]] = record
            self.done = event.get("done", self.done)
            self.failed = event.get("failed", self.failed)
            if record.get("status") != "running":
                self.log.append(self._line(record))


JOB_VIEW = {
    "classify": ("메일 {total}건을 함께 분류하고 있어요…", "classified", WAIT_MESSAGES),
    "reply": ("회신 메일 {total}건을 쓰고 있어요…", "drafts", REPLY_WAIT_MESSAGES),
    "archive": (
        "선택한 {total}건의 논의 이메일을 정리하고 있습니다",
        "archive_results",
        WAIT_MESSAGES,
    ),
}


@st.fragment(run_every=1.0)
def render_running_batch() -> None:
    """1초마다 다시 그린다. 경과 시간이 실제로 흐르고 문구는 3초마다 바뀐다."""
    job: BatchJob | None = st.session_state.get("job")
    if job is None:
        return
    job.drain()
    title, store_key, messages = JOB_VIEW[job.kind]

    if job.finished:
        st.session_state.setdefault(store_key, {}).update(job.records)
        st.session_state.job = None
        st.session_state.last_error = job.error
        st.rerun(scope="app")
        return

    elapsed = job.elapsed
    with st.status(title.format(total=job.total), expanded=True):
        st.markdown(f"### {wait_message(elapsed, messages)}")
        st.progress(
            job.done / job.total if job.total else 0.0,
            text=progress_text(
                done=job.done, total=job.total, failed=job.failed, elapsed=elapsed
            ),
        )
        # 코드블록으로 찍으면 문장이 로그처럼 보인다. 사람이 읽는 문장이라 그냥 글로 둔다.
        for line in job.log[-6:]:
            st.markdown(line)
        if job.kind == "archive":
            status_names = {
                "running": "분석 중",
                "ok": "완료",
                "error": "실패",
            }
            for case_id, title in job.senders.items():
                status = (job.records.get(case_id) or {}).get("status")
                st.write(f"{title} · {status_names.get(status, '대기 중')}")


def build_items(inbox: list[dict[str, Any]]) -> list[dict[str, Any]]:
    store: dict[str, dict[str, Any]] = st.session_state.get("classified", {})
    drafts: dict[str, dict[str, Any]] = st.session_state.get("drafts", {})
    ranks = amount_ranks(inbox)
    items = []
    for email in inbox:
        item = build_briefing(
            email,
            store.get(email["case_id"]),
            amount_rank=ranks.get(email["case_id"]),
            amount_pool=len(ranks),
        )
        item["draft_record"] = drafts.get(item["case_id"])
        item["stage"] = mail_stage(
            classified=item["classified"],
            label=item["label"],
            follow_up=item["needs_reply"],
            draft_record=item["draft_record"],
        )
        items.append(item)
    return items


def apply_filters(items: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    selected: set[str] = st.session_state.get("selected_cases", set())
    filtered = items
    if settings["labels"]:
        filtered = [item for item in filtered if item["label"] in settings["labels"]]
    if settings["unclassified_only"]:
        filtered = [item for item in filtered if item["status"] == "pending"]
    if settings["selected_only"]:
        filtered = [item for item in filtered if item["case_id"] in selected]
    return filtered


def render_list_tab(inbox: list[dict[str, Any]], settings: dict[str, Any], ready: bool) -> None:
    current_job: BatchJob | None = st.session_state.get("job")
    if current_job is not None and current_job.kind != "archive":
        render_running_batch()
        return

    left, right = st.columns([3, 1])
    left.subheader(f"메일 {len(inbox)}건")
    disabled = not ready or not inbox
    if right.button("📥 전체 분류 실행", type="primary", disabled=disabled, width="stretch"):
        st.session_state.job = BatchJob(
            kind="classify",
            total=len(inbox),
            senders={email["case_id"]: email["sender"] for email in inbox},
            runner=lambda on_event: classify_emails(
                inbox,
                model=settings["model"],
                max_workers=settings["workers"],
                timeout_seconds=settings["timeout"],
                service_tier="priority" if settings["priority"] else None,
                on_event=on_event,
            ),
        )
        st.rerun()
    if not ready:
        st.warning("Codex CLI를 찾을 수 없어 분류를 실행할 수 없습니다. `codex --version`을 확인하세요.")
    if st.session_state.pop("last_error", None):
        st.error(st.session_state.get("last_error") or "분류 실행 중 오류가 발생했습니다.")

    items = build_items(inbox)
    ranked = rank_briefings(items, mode=settings["sort"])
    summary = summarize(inbox, items)

    # 요약이 먼저 나오고 목록이 그 아래다.
    render_headline(summary)
    render_counts(summary)
    failures = [item for item in items if item["status"] == "error"]
    visible = apply_filters(ranked, settings)

    st.divider()
    if not visible:
        st.info("조건에 맞는 메일이 없습니다.")
    else:
        render_stage_sections(visible, settings, ready)

    render_failures(failures)


def render_stage_sections(
    items: list[dict[str, Any]], settings: dict[str, Any], ready: bool
) -> None:
    """처리 단계별로 묶어서 보여준다.

    "무엇을 더 해야 하는가"가 화면의 첫 질문이라 `처리 필요`가 맨 위에 오고, 회신 생성
    버튼도 탭을 넘기지 않고 그 자리에 둔다.
    """
    selected: set[str] = st.session_state.setdefault("selected_cases", set())
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item["stage"], []).append(item)

    # 스타일과 스코프 컨테이너는 페이지에 한 번만 만든다. 구역마다 만들면 같은 key가
    # 여러 번 생겨 StreamlitDuplicateElementKey가 난다.
    st.markdown(ROW_STYLE, unsafe_allow_html=True)
    with st.container(key="mail-rows"):
        for stage in STAGE_ORDER:
            bucket = grouped.get(stage)
            if not bucket:
                continue
            title, hint = stage_caption(stage)
            if stage == "unsupported":
                render_archive_stage_header(bucket, settings, title, ready)
            else:
                st.subheader(f"{title} {len(bucket)}건")

            if stage == "todo":
                picked = [item for item in bucket if item["case_id"] in selected]
                left, right = st.columns([2, 1], vertical_alignment="center")
                left.caption(hint)
                if right.button(
                    f"✍️ 선택 {len(picked)}건 회신 메일 생성",
                    type="primary",
                    disabled=not picked,
                    width="stretch",
                ):
                    start_reply_batch(picked, settings)
                    st.rerun()
                if not picked:
                    st.caption("아래에서 회신할 건을 눌러 선택하세요.")
            else:
                st.caption(hint)

            render_fold_list(bucket, settings)
            if stage == "unsupported":
                if st.session_state.get("job") is not None:
                    render_running_batch()
                else:
                    render_archive_batch_results()
            st.write("")


def render_fold_list(items: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    """메일 한 줄 = 왼쪽 펼침 버튼 + 클릭하면 선택되는 본문 바.

    체크박스를 누르는 것보다 줄 전체를 누르는 편이 목표가 훨씬 크다. 그래서 펼치기를
    왼쪽 작은 버튼으로 옮기고, 넓은 바는 선택 토글로 쓴다. 선택된 줄은 primary 버튼이라
    색이 채워져서 한눈에 구분된다.
    """
    selected: set[str] = st.session_state.setdefault("selected_cases", set())
    opened: set[str] = st.session_state.setdefault("expanded_cases", set())
    inbox_key = settings["inbox_key"]

    for item in items:
        case_id = item["case_id"]
        is_open = case_id in opened
        is_picked = case_id in selected
        archive_selected: set[str] = st.session_state.setdefault(
            "archive_selected_cases", set()
        )
        archive_selectable = (
            item.get("stage") == "unsupported" and item.get("label") == ARCHIVE_LABEL
        )
        archive_id = _archive_selection_id(item)
        is_archive_picked = archive_id in archive_selected
        # 아직 회신을 만들지 않은, 만들 수 있는 건만 고를 수 있다. 이미 처리했거나
        # 처리할 내용이 없는 건을 선택해봐야 할 일이 없다.
        selectable = item["stage"] == "todo"

        # 메일 한 건 = 박스 하나. 펼친 내용도 같은 박스 안에 들어간다.
        with st.container(border=True):
            toggle, bar = st.columns([1, 30], vertical_alignment="center")
            if toggle.button(
                "",
                icon=(
                    ":material/keyboard_arrow_down:" if is_open
                    else ":material/chevron_right:"
                ),
                key=f"open::{inbox_key}::{case_id}",
                type="tertiary",
                help="접기" if is_open else "펼치기",
            ):
                opened.symmetric_difference_update({case_id})
                st.rerun()

            if selectable:
                clicked = bar.button(
                    item_header(item),
                    key=f"pick::{inbox_key}::{case_id}",
                    type="primary" if is_picked else "secondary",
                    icon=":material/check_circle:" if is_picked else ":material/circle:",
                    width="stretch",
                    help="클릭하면 회신 초안 대상으로 선택/해제됩니다",
                )
                if clicked:
                    selected.symmetric_difference_update({case_id})
                    st.rerun()
            elif archive_selectable:
                if bar.button(
                    item_header(item),
                    key=f"archive-pick::{inbox_key}::{case_id}",
                    type="primary" if is_archive_picked else "secondary",
                    icon=(
                        ":material/check_circle:"
                        if is_archive_picked
                        else ":material/circle:"
                    ),
                    width="stretch",
                    help="클릭하면 논의 아카이빙 대상으로 선택/해제됩니다",
                ):
                    archive_selected.symmetric_difference_update({archive_id})
                    st.rerun()
            else:
                # 선택할 수 없는 줄도 눌리긴 해야 한다. 여기서는 펼치기로 동작한다.
                if bar.button(
                    item_header(item),
                    key=f"open-bar::{inbox_key}::{case_id}",
                    type="tertiary",
                    width="stretch",
                    help="회신 초안을 지원하지 않는 분류입니다. 클릭하면 펼쳐집니다.",
                ):
                    opened.symmetric_difference_update({case_id})
                    st.rerun()

            if is_open:
                st.divider()
                render_item_body(item)
                record = item.get("draft_record")
                if record is not None:
                    # 어떻게 처리했는지가 이 메일에서 가장 궁금한 부분이라 위에 둔다.
                    st.markdown(f"**처리 결과** · {record.get('skill', '')}")
                    render_draft(
                        record,
                        save_draft=save_purchase_review_draft,
                        draft_fingerprint=purchase_draft_fingerprint,
                    )
                # 원본 메일은 그 안에서 한 번 더 접어 둔다. 기본은 접힌 상태다.
                with st.expander("📧 원본 메일 보기", expanded=False):
                    render_original_email(item)


# ------------------------------------------------------------------------ 나머지 탭


def render_pick_tab(inbox: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    """현재 화면에서 빠져 있다. 선택·회신은 목록 페이지의 `처리 필요` 구역이 담당한다."""
    if st.session_state.get("job") is not None:
        render_running_batch()
        return

    selected: set[str] = st.session_state.get("selected_cases", set())
    items = {item["case_id"]: item for item in build_items(inbox)}
    picked = [items[case_id] for case_id in selected if case_id in items]

    st.subheader(f"선택된 메일 {len(picked)}건")
    st.caption(
        "회신 초안을 지원하는 분류: " + ", ".join(f"`{label}`" for label in supported_labels())
    )
    if not picked:
        st.info("메일 목록 탭에서 분류를 먼저 실행하고, 회신할 건을 선택하세요.")
        return

    ranked = rank_briefings(picked)
    for item in ranked:
        st.markdown(f"- {item_header(item)}")

    if st.button("✍️ 선택 건 회신 메일 생성", type="primary"):
        start_reply_batch(ranked, settings)
        st.rerun()

    drafts: dict[str, dict[str, Any]] = st.session_state.get("drafts", {})
    if not drafts:
        return
    st.divider()
    st.subheader("회신 메일")
    for item in ranked:
        record = drafts.get(item["case_id"])
        if record is None:
            continue
        with st.expander(f"{item_header(item)}", expanded=False):
            st.caption(f"{record.get('skill', '')} · {record.get('action', '')}")
            render_draft(
                record,
                save_draft=save_purchase_review_draft,
                draft_fingerprint=purchase_draft_fingerprint,
            )


def start_reply_batch(items: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    """선택한 건들의 회신 메일을 만든다.

    분류와 똑같이 백그라운드 스레드로 돌린다. 메인 스레드에서 기다리면 경과 시간이
    0초에 멈춰 있다가 끝날 때 한 번에 튄다.
    """
    targets = [(item["email"], item["classification"]) for item in items]
    st.session_state.job = BatchJob(
        kind="reply",
        total=len(targets),
        senders={item["case_id"]: item["sender"] for item in items},
        runner=lambda on_event: draft_replies(
            targets,
            model=settings["model"],
            max_workers=settings["workers"],
            service_tier="priority" if settings["priority"] else None,
            on_event=on_event,
        ),
    )


def render_summary_tab(inbox: list[dict[str, Any]]) -> None:
    """현재 탭에서 빠져 있다. 필요해지면 main()의 st.tabs 목록에 다시 넣는다."""
    items = build_items(inbox)
    summary = summarize(inbox, items)
    render_headline(summary)
    st.subheader("유형별 건수")
    render_counts(summary)

    st.subheader("금액순 상위 구매 건")
    st.caption(
        f"제목과 본문에서 금액을 읽어낸 {summary['amount_known']}건이 대상입니다. "
        "구성항목·기대효과 충족 여부는 구매 검토 Skill의 판단이라 여기서 세지 않습니다."
    )
    render_top_amounts(summary)


def show_result(result: CodexResult | None) -> None:
    if result is None:
        st.caption("아직 실행하지 않았습니다.")
    elif result.parsed is not None:
        st.json(result.parsed)
    else:
        st.code(result.text, language="text")


def archive_button_label(selected_count: int) -> str:
    if selected_count <= 0:
        return "🗂️ 아카이빙할 메일 선택"
    return f"🗂️ 선택 {selected_count}건 아카이빙"


def _archive_selection_id(item: dict[str, Any]) -> str:
    email = item.get("email") or {}
    return str(email.get("thread_id") or item.get("case_id") or "")


def render_archive_stage_header(
    items: list[dict[str, Any]],
    settings: dict[str, Any],
    title: str,
    ready: bool,
) -> None:
    selected: set[str] = st.session_state.setdefault("archive_selected_cases", set())
    archive_items = [item for item in items if item.get("label") == ARCHIVE_LABEL]
    valid_ids = {_archive_selection_id(item) for item in archive_items}
    selected.intersection_update(valid_ids)
    count = len(selected)
    title_column, run_column = st.columns([2, 1], vertical_alignment="center")
    title_column.subheader(f"{title} {len(items)}건")
    running = st.session_state.get("job") is not None
    selected_items = [
        item for item in archive_items if _archive_selection_id(item) in selected
    ]
    if run_column.button(
        archive_button_label(count),
        key="archive-selected-run",
        type="primary",
        disabled=not ready or not selected_items or running,
        width="stretch",
    ):
        st.session_state.archive_run_order = [item["case_id"] for item in selected_items]
        st.session_state.archive_results = {}
        st.session_state.job = BatchJob(
            kind="archive",
            total=len(selected_items),
            senders={
                item["case_id"]: str(item["email"].get("subject") or "제목 없음")
                for item in selected_items
            },
            runner=lambda on_event: archive_discussion_emails(
                [
                    (item["email"], item.get("classification") or {})
                    for item in selected_items
                ],
                model=settings["model"],
                max_workers=3,
                on_event=on_event,
            ),
        )
        st.rerun()



def render_archive_batch_results() -> None:
    records: dict[str, dict[str, Any]] = st.session_state.get("archive_results", {})
    order: list[str] = st.session_state.get("archive_run_order", [])
    if not order:
        return
    st.subheader("논의 이메일 아카이빙 결과")
    successful, failed = archive_save_candidates(records, order)
    for case_id in order:
        record = records.get(case_id)
        if record is None:
            continue
        if record.get("status") != "ok":
            email = record.get("email") or {}
            title = str(email.get("subject") or "제목 없음")
            latest_date = str(email.get("received_at") or "")[:10]
            with st.expander(
                f"{title} · {latest_date or ARCHIVE_EMPTY_VALUE}", expanded=False
            ):
                st.error(record.get("error") or "분석에 실패했습니다.")
            continue
        email = record["email"]
        codex_result = record["result"]
        parsed = codex_result.parsed if isinstance(codex_result.parsed, dict) else {}
        if not is_canonical_archive_result(parsed):
            title = str(email.get("subject") or "제목 없음")
            latest_date = str(email.get("received_at") or "")[:10]
            with st.expander(
                f"{title} · {latest_date or ARCHIVE_EMPTY_VALUE}", expanded=False
            ):
                st.error("아카이빙 결과 형식을 해석하지 못했습니다. 다시 분석해 주세요.")
            continue
        title = str(email.get("subject") or "제목 없음")
        latest_date = str(email.get("received_at") or parsed.get("날짜") or "")[:10]
        with st.expander(f"{title} · {latest_date or ARCHIVE_EMPTY_VALUE}", expanded=True):
            _render_archive_result(parsed)
    _render_archive_excel_controls(successful, failed)


def _render_archive_value(label: str, value: Any) -> None:
    st.write(f"**{label}**")
    items = natural_language_items(value)
    if not items:
        st.write(ARCHIVE_EMPTY_VALUE)
        return
    for item in items:
        # st.write는 이메일/LLM의 HTML을 실행하지 않고 일반 텍스트로 표시한다.
        st.write(f"• {item}")


def _render_archive_result(result: dict[str, Any]) -> None:
    fields = [
        ("발신자", result.get("발신자")),
        ("최신 날짜", result.get("날짜") or result.get("최신 날짜")),
        ("Topic", result.get("Topic")),
        ("최종 금액", formatted_amount(result.get("금액"), result.get("통화"))),
        ("Business Impact", result.get("Business Impact")),
        ("Thread 진행 중 변경된 내용", result.get("Thread 진행 중 변경된 내용")),
        ("결정된 내용", result.get("결정된 내용")),
        ("Open Item", result.get("Open Item")),
    ]
    for label, value in fields:
        _render_archive_value(label, value)


def _render_archive_excel_controls(
    successful: list[tuple[dict[str, Any], dict[str, Any]]], failed_count: int
) -> None:
    store = EmailArchiveExcelStore()
    try:
        workbook_bytes = store.read_bytes()
    except Exception as exc:  # noqa: BLE001
        workbook_bytes = None
        st.error(f"Master Excel을 읽을 수 없습니다: {exc}")

    save_column, download_column = st.columns(2)
    if save_column.button(
        "💾 Save", key="archive-batch-save", disabled=not successful, width="stretch"
    ):
        try:
            saved = store.append_many(successful)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Master Excel 저장에 실패했습니다: {exc}")
        else:
            if saved.added_count == 0:
                st.info("새로 저장할 아카이빙 결과가 없습니다.")
            else:
                st.success("Master Excel 저장을 완료했습니다.")
            st.write(f"새로 저장된 결과: {saved.added_count}건")
            st.write(f"이미 저장되어 제외된 결과: {saved.duplicate_count}건")
            st.write(f"분석 실패로 제외된 결과: {failed_count}건")
            st.write(f"Master Excel 전체 누적 결과: {saved.row_count}건")
            workbook_bytes = store.read_bytes()

    download_column.download_button(
        "📥 Download",
        data=workbook_bytes or b"",
        file_name="email_archive_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=workbook_bytes is None,
        key="archive-batch-download",
        width="stretch",
    )
    if workbook_bytes is None:
        st.info("먼저 아카이빙 결과를 저장해 주세요")
    st.caption(
        "Save: 분석이 완료된 미저장 아카이빙 결과를 Master Excel에 추가 · "
        "Download: 지금까지 누적된 Master Excel 전체를 다운로드"
    )


def render_single_tab(source: Path, model: str | None) -> None:
    """현재 탭에서 빠져 있다. 필요해지면 main()의 st.tabs 목록에 다시 넣는다.

    기존 단건 흐름. `review_purchase_email`·`review_discussion_email`로 가는 유일한 경로라
    세션 키까지 그대로 둔다."""
    raw = json.loads(source.read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else [raw]
    if len(records) > 1:
        index = st.selectbox(
            "이메일",
            range(len(records)),
            format_func=lambda i: str(
                records[i].get("pr_number") or records[i].get("case_id") or i + 1
            ),
        )
        email = records[index]
        sample_key = f"{source}#{index}"
    else:
        email = records[0]
        sample_key = str(source)

    if st.session_state.get("sample_key") != sample_key:
        st.session_state.sample_key = sample_key
        st.session_state.classification = None
        st.session_state.purchase_review = None
        st.session_state.discussion_review = None

    st.subheader("입력")
    st.json(email, expanded=False)
    actions = st.columns(3)

    if actions[0].button("1. 메일 분류", width="stretch"):
        with st.spinner("메일 분류 Skill 실행 중"):
            try:
                st.session_state.classification = classify_email(email, model)
            except Exception as exc:  # noqa: BLE001
                st.error(f"{type(exc).__name__}: {exc}")

    classification = st.session_state.get("classification")
    if actions[1].button("2. 구매·계약 검토", width="stretch"):
        if classification is None:
            st.warning("먼저 메일을 분류하세요.")
        else:
            with st.spinner("구매 이메일 검토 Skill 실행 중"):
                try:
                    st.session_state.purchase_review = review_purchase_email(
                        email, classification.display_value(), model
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"{type(exc).__name__}: {exc}")

    if actions[2].button("3. 논의·질의 검토", width="stretch"):
        if classification is None:
            st.warning("먼저 메일을 분류하세요.")
        else:
            with st.spinner("논의 이메일 검토 Skill 실행 중"):
                try:
                    st.session_state.discussion_review = review_discussion_email(
                        email, classification.display_value(), model
                    )
                except Exception as exc:  # noqa: BLE001
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


# ----------------------------------------------------------------------------- main


@st.cache_data(show_spinner=False)
def _codex_version() -> str:
    return codex_version()


def main() -> None:
    st.set_page_config(page_title="Office Blue", page_icon="📬", layout="wide")
    st.title("📬 Office Blue")
    st.caption("메일을 한 번에 분류하고, 긴급하고 비용 큰 건부터 봅니다. 발송은 하지 않습니다.")

    sources = load_sources()
    if not sources:
        st.error("data/synthetic/emails에 JSON 샘플이 없습니다.")
        return

    with st.sidebar:
        st.header("설정")
        kind = st.radio(
            "메일 출처", ["Gmail", "합성 데이터"], index=1, horizontal=True,
            help="Gmail은 연결된 Codex Gmail 커넥터로 읽기 전용 조회만 합니다.",
        )
        # 옵션은 Path 하나로 둔다. 튜플을 옵션으로 주면 라벨 조회가 인덱스에 묶여
        # 다루기 번거롭다.
        labels = {path: label for path, label, _ in sources}
        counts = {path: count for path, _, count in sources}
        source: Path | None = None
        if kind == "합성 데이터":
            source = st.selectbox("데이터 소스", list(labels), format_func=labels.__getitem__)
            count = counts[source]
            limit = st.number_input("최대 메일 수", 1, max(1, count), min(count, 30))
        else:
            gmail_query = st.text_input(
                "Gmail 검색어", value=GMAIL_DEFAULT_QUERY,
                help="Gmail 검색 문법을 그대로 씁니다. 기본은 안 읽은 메일 전체입니다.",
            )
            limit = st.number_input("최대 메일 수", 1, 50, 50)
            if st.button("📨 메일 가져오기", width="stretch"):
                with st.spinner("Gmail에서 읽는 중 (최대 4분)"):
                    try:
                        fetched, errors = fetch_inbox(gmail_query, max_results=int(limit))
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"{type(exc).__name__}: {exc}")
                    else:
                        st.session_state.gmail_inbox = fetched
                        st.session_state.gmail_errors = errors
                        st.session_state.gmail_key = f"gmail:{gmail_query}"
                        st.session_state.classified = {}
                        st.session_state.selected_cases = set()
                        st.session_state.archive_selected_cases = set()
                        st.session_state.archive_results = {}
                        st.session_state.archive_run_order = []
                        st.session_state.expanded_cases = set()
                        st.rerun()
        sort_mode = st.segmented_control(
            "정렬", ["균형", "긴급도", "금액순"], default="균형"
        ) or "균형"
        labels = st.multiselect("유형 필터", LABELS)
        unclassified_only = st.checkbox("미분류만 보기", value=False)
        selected_only = st.checkbox("선택한 건만 보기", value=False)

        with st.expander("고급"):
            model_text = st.text_input("Codex 모델", value="", help="비워 두면 로컬 기본 모델")
            workers = st.slider("동시 실행", 1, MAX_PARALLEL, DEFAULT_MAX_WORKERS)
            timeout = st.slider("건당 제한시간(초)", 60, 300, 120, step=10)
            priority = st.checkbox(
                "우선 처리(priority) 사용", value=True, help="대기 시간이 줄지만 사용량을 더 씁니다."
            )

        st.divider()
        version = _codex_version()
        st.caption(f"Codex: `{version}`")
        st.caption(f"모델: `{model_text.strip() or '로컬 기본'}`")

    model = model_text.strip() or None
    if source is not None:
        inbox = load_inbox(source, limit=int(limit))
        # 소스 경로만 키로 쓴다. 여기에 건수를 넣으면 "최대 메일 수"를 조금 바꾸는 것만으로
        # 이미 끝난 분류 결과가 통째로 날아간다. 결과는 case_id로 저장되므로 건수가 줄면
        # 그냥 덜 보일 뿐이다.
        inbox_key = str(source)
    else:
        inbox = st.session_state.get("gmail_inbox") or []
        inbox_key = st.session_state.get("gmail_key", "gmail:")
        # 도구를 못 써도 스키마에 맞는 빈 목록이 나온다. 0건인지 조회가 깨진 건지 구분해 말한다.
        for issue in st.session_state.get("gmail_errors") or []:
            st.error(f"Gmail 조회 오류 — {issue.get('where', '?')}: {issue.get('reason', '')}")
        if not inbox:
            if st.session_state.get("gmail_key"):
                st.warning(
                    "조회 결과가 0건입니다. 위에 오류가 없다면 검색어에 맞는 메일이 실제로 "
                    "없는 것이고, 오류가 있다면 Gmail MCP 연결 문제입니다."
                )
            else:
                st.info("사이드바에서 **메일 가져오기**를 누르세요. 조회는 읽기 전용입니다.")

    if st.session_state.get("inbox_key") != inbox_key:
        # 소스가 바뀌면 이전 소스의 분류 결과와 선택은 의미가 없다.
        st.session_state.inbox_key = inbox_key
        st.session_state.classified = {}
        st.session_state.selected_cases = set()
        st.session_state.archive_selected_cases = set()
        st.session_state.archive_results = {}
        st.session_state.archive_run_order = []
        st.session_state.expanded_cases = set()

    settings = {
        "model": model, "workers": workers, "timeout": timeout, "priority": priority,
        "sort": sort_mode, "labels": labels, "unclassified_only": unclassified_only,
        "selected_only": selected_only, "inbox_key": inbox_key,
    }

    # 탭을 없앴다. 선택하고 회신을 만드는 흐름이 한 화면 안에서 끝나야 한다.
    # `render_summary_tab` / `render_single_tab` / `render_pick_tab`은 코드에 그대로
    # 남아 있으니, 필요해지면 여기서 `st.tabs`로 다시 묶으면 된다.
    render_list_tab(inbox, settings, ready=version != "unavailable")


if __name__ == "__main__":
    main()
