from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from approval_excel import PurchaseApprovalExcelStore, READY_STATUS

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = "purchase-email-review"
EXPERIMENT_DIR = Path(__file__).resolve().parent
RUNNER = Path(__file__).resolve().parent.parent / "run.py"
UPLOAD_DIR = ROOT / "experiments" / "instances" / ".uploads"
EXCEL_EXPORT_ROOT = ROOT / "experiments" / "instances"
EXCEL_EXPORT_PATH = (
    EXCEL_EXPORT_ROOT
    / "purchase_approval_exports"
    / "approved_purchase_emails.xlsx"
)


def normalize_email(data: dict[str, object]) -> dict[str, object]:
    cost = data.get("cost_breakdown") if isinstance(data.get("cost_breakdown"), dict) else {}
    effects = data.get("expected_effects") if isinstance(data.get("expected_effects"), dict) else {}
    generated_body = "\n".join(
        (
            f"요청자: {data.get('requester') or 'unknown'}",
            f"구매 유형: {data.get('type') or 'unknown'}",
            f"품목/서비스 및 목적: {data.get('description') or 'unknown'}",
            f"공급사: {data.get('vendor') or 'unknown'}",
            f"금액: {data.get('total_amount') or 'unknown'}",
            f"비용 산출 근거: {cost.get('details') or 'unknown'}",
            f"예상 정량 효과: {effects.get('details') or 'unknown'}",
            f"최근 의견: {data.get('recent_comments') or 'unknown'}",
        )
    )
    return {
        "case_id": data.get("case_id") or data.get("message_id") or data.get("id") or data.get("pr_number") or "uploaded-email",
        "message_id": data.get("message_id") or (f"ariba-{data.get('id')}" if data.get("id") else ""),
        "thread_id": data.get("thread_id") or (f"ariba-{data.get('pr_number')}" if data.get("pr_number") else ""),
        "sender": data.get("sender") or data.get("from") or data.get("requester") or "",
        "recipients": data.get("recipients") or data.get("to") or [],
        "subject": data.get("subject") or data.get("email_subject") or "",
        "body": data.get("body") or data.get("email_body") or generated_body,
        "received_at": data.get("received_at") or "",
        "attachments": data.get("attachments") or [],
        "approval_url": data.get("approval_url") or "",
    }


def sync_email(data: dict[str, object], token: str) -> None:
    if st.session_state.get("upload_token") == token:
        return
    st.session_state.upload_token = token
    for key, value in normalize_email(data).items():
        st.session_state[f"email_{key}"] = value
    st.session_state.pop("run_dir", None)


def load_result(run_dir: Path, condition: str) -> object:
    folder = run_dir / condition
    for filename in ("result.json", "output.txt", "error.txt"):
        path = folder / filename
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if filename == "error.txt":
                return {"error": text.strip()}
            # Older runs stored output.txt only, sometimes inside a ```json fence.
            candidate = text.strip()
            if candidate.startswith("```"):
                candidate = re.sub(r"^```[A-Za-z0-9_-]*[ \t]*\r?\n?", "", candidate)
                candidate = re.sub(r"\r?\n?```$", "", candidate).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return text
    return {"error": "결과 파일이 없습니다."}


def run_ab(
    email: dict[str, object],
    on_event: Callable[[dict[str, object]], None] | None = None,
) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    case_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.json"
    case_path.write_text(json.dumps(email, ensure_ascii=False), encoding="utf-8")
    result_path: Path | None = None
    stderr = ""
    try:
        process = subprocess.Popen(
            [sys.executable, "-u", str(RUNNER), EXPERIMENT, "--case", str(case_path)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for raw_line in process.stdout or ():
            line = raw_line.strip()
            if line.startswith("AB_EVENT "):
                if on_event is not None:
                    on_event(json.loads(line.removeprefix("AB_EVENT ")))
            elif line:
                result_path = Path(line)
        stderr = (process.stderr.read().strip() if process.stderr else "")
        process.wait()
    finally:
        case_path.unlink(missing_ok=True)
    if result_path is None:
        raise RuntimeError(stderr or "실험 결과를 확인할 수 없습니다.")
    return result_path


ITEM_LABELS = {
    "cost": "비용",
    "quantitative_benefit": "예상 정량 효과",
    "previous_contract_difference": "이전 계약과의 차이",
    "basic_contract_information": "기본 계약 정보",
}
STATUS_LABELS = {
    "SATISFIED": "✅ 충족",
    "MISSING": "❌ 누락",
    "UNCLEAR": "⚠️ 불명확",
    "NOT_APPLICABLE": "➖ 해당 없음",
}
CONTRACT_KEYS = {"document_type", "review_status", "status_reason", "checks",
                 "previous_contract_lookup", "untrusted_instructions", "reply_draft",
                 "approval_guidance", "user_confirmation", "prohibited_actions"}
# Rendered on their own, so the generic pass must not repeat them.
HANDLED_KEYS = {"review_status", "status_reason", "checks", "reply_draft",
                "reply_draft_ko", "approval_guidance", "document_type"}
# baseline invents its own status key each run; check these in order.
STATUS_ALIASES = ("review_status", "status", "decision", "recommended_handling",
                  "recommended_action", "review_summary", "summary")


def render_badge(column, label: str, value: str, tone: str = "normal", tooltip: str = "") -> None:
    """Compact label/value pair. st.metric renders the value at ~2rem, which clips these."""
    colors = {"ok": "#1a7f37", "warn": "#9a6700", "normal": "inherit"}
    title = f' title="{html.escape(tooltip)}"' if tooltip else ""
    column.markdown(
        f'<div{title} style="line-height:1.35;margin-bottom:.25rem">'
        f'<div style="font-size:.72rem;opacity:.65;letter-spacing:.02em">{html.escape(label)}</div>'
        f'<div style="font-size:.95rem;font-weight:600;color:{colors.get(tone, "inherit")};'
        f'word-break:break-word">{html.escape(value)}</div></div>',
        unsafe_allow_html=True,
    )


def as_text(value: object) -> str:
    """Flatten any Codex value into readable text. Evidence is sometimes a list of dicts."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "value" in value:  # e.g. {"type": "fact", "value": "..."}
            prefix = str(value.get("type") or "").strip()
            body = as_text(value["value"])
            return f"[{prefix}] {body}" if prefix else body
        return " · ".join(f"{k}: {as_text(v)}" for k, v in value.items() if v not in (None, "", [], {}))
    if isinstance(value, (list, tuple)):
        return "\n".join(f"• {as_text(v)}" for v in value if v not in (None, "", [], {}))
    return str(value)


def render_checks(checks: object) -> None:
    """Always show the four mandatory items, so A and B stay row-comparable.

    baseline has no `checks`, and that absence is the finding — render it as
    `판정 없음` rather than hiding the table.
    """
    by_item: dict[str, dict] = {}
    if isinstance(checks, list):
        for entry in checks:
            if isinstance(entry, dict) and entry.get("item"):
                by_item[str(entry["item"])] = entry

    rows = []
    for key, label in ITEM_LABELS.items():
        entry = by_item.pop(key, None)
        if entry is None:
            rows.append({"항목": label, "판정": "— 판정 없음", "근거": "", "보완 방향": ""})
            continue
        rows.append({
            "항목": label,
            "판정": STATUS_LABELS.get(str(entry.get("status") or ""), entry.get("status") or "-"),
            "근거": as_text(entry.get("evidence")),
            "보완 방향": as_text(entry.get("correction")),
        })
    for key, entry in by_item.items():  # items the model invented beyond the four
        rows.append({
            "항목": f"{key} (계약 외)",
            "판정": STATUS_LABELS.get(str(entry.get("status") or ""), entry.get("status") or "-"),
            "근거": as_text(entry.get("evidence")),
            "보완 방향": as_text(entry.get("correction")),
        })

    judged = sum(1 for r in rows if r["판정"] != "— 판정 없음")
    st.caption(f"필수 4개 항목 중 **{judged}개** 판정" if judged else "필수 4개 항목이 하나도 판정되지 않았습니다.")
    st.dataframe(
        pd.DataFrame(rows)[["항목", "판정"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "항목": st.column_config.TextColumn(width="medium"),
            "판정": st.column_config.TextColumn(width="small"),
        },
    )
    for row in rows:
        if not row["근거"] and not row["보완 방향"]:
            continue
        with st.expander(f"{row['판정']}  {row['항목']} — 근거 보기"):
            if row["근거"]:
                st.markdown("**근거**")
                st.markdown(row["근거"])
            if row["보완 방향"]:
                st.markdown("**보완 방향**")
                st.markdown(row["보완 방향"])


def render_generic(data: dict) -> None:
    """Baseline returns a different shape every run, so render whatever keys it used."""
    for key, value in data.items():
        if key in HANDLED_KEYS or value in (None, "", [], {}):
            continue
        label = key.replace("_", " ")
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            st.markdown(f"**{label}**")
            flat = [{k: as_text(v) for k, v in row.items()} for row in value]
            st.dataframe(pd.DataFrame(flat), hide_index=True, use_container_width=True)
        elif isinstance(value, dict):
            st.markdown(f"**{label}**")
            st.dataframe(
                pd.DataFrame([{"항목": k, "값": as_text(v)} for k, v in value.items()]),
                hide_index=True, use_container_width=True,
            )
        elif isinstance(value, list):
            st.markdown(f"**{label}**")
            st.markdown("\n".join(f"- {as_text(v)}" for v in value))
        else:
            st.markdown(f"**{label}**  \n{as_text(value)}")


def render_draft(draft: object) -> None:
    if isinstance(draft, dict):
        head = [f"**받는 사람** {draft.get('to') or '-'}", f"**제목** {draft.get('subject') or '-'}"]
        st.markdown("  \n".join(head))
        body = as_text(draft.get("body"))
        if body:
            st.text_area("본문", body, height=200, disabled=True,
                         key=f"draft_{abs(hash(body)) % 10**8}")
    else:
        st.markdown(as_text(draft))


def render_approval_excel_controls(email: dict[str, object], treatment_result: object) -> None:
    """승인 가능한 A 결과를 누적 Excel에 자동 저장하고 다운로드를 제공한다."""
    store = PurchaseApprovalExcelStore(EXCEL_EXPORT_PATH, EXCEL_EXPORT_ROOT)
    eligible = (
        isinstance(treatment_result, dict)
        and treatment_result.get("review_status") == READY_STATUS
    )
    if eligible:
        try:
            row_number, created = store.append_approved_email(email, treatment_result)
        except Exception as exc:
            st.error(f"승인 가능 이메일을 Excel에 저장하지 못했습니다: {exc}")
        else:
            if created:
                st.success(f"승인 가능 이메일을 Excel {row_number}번째 행에 자동 저장했습니다.")
            else:
                st.info(f"이 승인 가능 이메일은 Excel {row_number}번째 행에 이미 저장되어 있습니다.")
    else:
        st.info("A 결과가 승인 가능일 때만 별도 Excel에 자동 저장됩니다.")

    try:
        workbook_bytes = store.read_bytes()
    except Exception as exc:
        st.error(f"누적 Excel 파일을 다운로드할 수 없습니다: {exc}")
        return
    if workbook_bytes is not None:
        st.download_button(
            "승인 가능 이메일 Excel 다운로드",
            data=workbook_bytes,
            file_name=EXCEL_EXPORT_PATH.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def render_result(title: str, caption: str, result: object) -> None:
    st.markdown(f"### {title}")
    st.caption(caption)
    with st.container(border=True):
        if isinstance(result, dict) and "error" in result and len(result) == 1:
            st.error(as_text(result["error"]))
            return
        if not isinstance(result, dict):
            # Unparseable output still gets the three indicators, so A and B stay comparable.
            left, right = st.columns([3, 2])
            render_badge(left, "검토 상태", "확인 불가")
            render_badge(right, "Skill 출력 계약", "미준수", tone="warn",
                         tooltip="JSON 으로 파싱되지 않아 계약을 판정할 수 없습니다.")
            st.markdown("#### 필수 항목 검토")
            render_checks(None)
            with st.expander("원본 출력", expanded=True):
                st.code(str(result), language="text")
            return

        follows_contract = not (CONTRACT_KEYS - set(result))
        # baseline names its status differently every run, so accept the usual aliases.
        status_full = next(
            (as_text(result[k]) for k in STATUS_ALIASES if result.get(k)),
            "",
        ) or "상태 미지정"
        # baseline sometimes yields a whole sentence; metric needs a short label.
        status = status_full.splitlines()[0].strip()
        if len(status) > 44:
            status = status[:43] + "…"
        left, right = st.columns([3, 2])
        render_badge(left, "검토 상태", status,
                     tooltip=status_full if status_full != status else "")
        render_badge(right, "Skill 출력 계약", "준수" if follows_contract else "미준수",
                     tone="ok" if follows_contract else "warn",
                     tooltip="treatment 는 Skill 이 정한 형식을 따라야 하고, baseline 은 따르지 않는 것이 정상입니다.")
        reason = as_text(result.get("status_reason"))
        if reason:
            st.caption(reason)

        st.markdown("#### 필수 항목 검토")
        render_checks(result.get("checks"))

        draft = result.get("reply_draft") or result.get("reply_draft_ko")
        if draft:
            st.markdown("#### 보완 요청 회신 초안")
            render_draft(draft)

        guidance = result.get("approval_guidance")
        if guidance:
            st.markdown("#### 승인 검토 안내")
            st.markdown(as_text(guidance))

        remaining = {k: v for k, v in result.items() if k not in HANDLED_KEYS}
        if remaining:
            with st.expander("그 밖의 반환 항목", expanded=not follows_contract):
                render_generic(remaining)

        with st.expander("원본 JSON"):
            st.json(result)


def main() -> None:
    st.set_page_config(page_title="Ariba 지출결의서 A/B", page_icon="✉️", layout="wide")
    config = json.loads((EXPERIMENT_DIR / "experiment.json").read_text(encoding="utf-8"))
    st.title("Ariba 지출결의서 검토 A/B 테스트")
    st.caption("JSON 업로드 → 이메일 내용 확인·수정 → A/B 동시 검토")
    st.info("A는 개발 중인 Skill을 적용하고 B는 Skill 없이 실행합니다. 두 경로 모두 Codex exec를 사용합니다.")

    uploaded = st.file_uploader("Ariba 이메일 JSON 업로드", type="json")
    try:
        if uploaded is not None:
            raw = uploaded.getvalue()
            uploaded_data = json.loads(raw.decode("utf-8"))
            if isinstance(uploaded_data, list):
                if not uploaded_data or not all(isinstance(item, dict) for item in uploaded_data):
                    raise ValueError("JSON 배열에는 이메일 객체가 한 개 이상 있어야 합니다.")
                selected_index = st.selectbox(
                    "검토할 Ariba 요청",
                    range(len(uploaded_data)),
                    format_func=lambda index: (
                        f"{uploaded_data[index].get('pr_number') or uploaded_data[index].get('case_id') or index + 1} · "
                        f"{uploaded_data[index].get('email_subject') or uploaded_data[index].get('subject') or '(제목 없음)'}"
                    ),
                )
                selected_data = uploaded_data[selected_index]
                token = f"{hashlib.sha256(raw).hexdigest()}:{selected_index}"
                sync_email(selected_data, token)
                st.success(f"Ariba 요청 {len(uploaded_data)}건을 불러왔습니다.")
            elif isinstance(uploaded_data, dict):
                sync_email(uploaded_data, hashlib.sha256(raw).hexdigest())
            else:
                raise ValueError("JSON은 이메일 객체 또는 이메일 객체 배열이어야 합니다.")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        st.error(f"JSON을 불러올 수 없습니다: {exc}")

    with st.form("email_form"):
        left, right = st.columns(2)
        with left:
            sender = st.text_input("발신자", key="email_sender")
            subject = st.text_input("제목", key="email_subject")
        with right:
            message_id = st.text_input("메시지 ID", key="email_message_id")
            thread_id = st.text_input("스레드 ID", key="email_thread_id")
        body = st.text_area("이메일 본문", height=260, key="email_body")
        approval_url = st.text_input("승인 페이지 URL (제공된 경우)", key="email_approval_url")
        submitted = st.form_submit_button("A/B 동시 검토", type="primary", use_container_width=True)

    if submitted:
        if not sender.strip() or not subject.strip() or not body.strip():
            st.error("발신자, 제목, 본문을 입력하세요.")
        else:
            email = {
                "case_id": st.session_state.get("email_case_id") or "ui-email",
                "message_id": message_id,
                "thread_id": thread_id,
                "sender": sender,
                "recipients": st.session_state.get("email_recipients", []),
                "subject": subject,
                "body": body,
                "received_at": st.session_state.get("email_received_at") or "",
                "attachments": st.session_state.get("email_attachments", []),
                "approval_url": approval_url,
            }
            st.session_state.purchase_review_email = email
            with st.status("A와 B를 동시에 실행합니다...", expanded=True) as run_status:
                slots = {"treatment": st.empty(), "baseline": st.empty()}
                labels = {"treatment": "A · Skill 적용", "baseline": "B · Skill 미적용"}
                failed: set[str] = set()

                def show_event(event: dict[str, object]) -> None:
                    condition = str(event["condition"])
                    state = str(event["state"])
                    slot = slots.get(condition)
                    if slot is None:
                        return
                    label = labels.get(condition, condition)
                    if state == "running":
                        slot.info(f"{label}: 실행 중 (최대 {event.get('timeout_seconds')}초)")
                    elif state == "completed":
                        slot.success(f"{label}: 완료")
                    else:
                        failed.add(condition)
                        slot.error(f"{label}: {event.get('error') or '실행 실패'}")

                try:
                    st.session_state.run_dir = str(run_ab(email, show_event))
                except RuntimeError as exc:
                    run_status.update(label="A/B 검토 실행 실패", state="error")
                    st.error(str(exc))
                else:
                    run_status.update(
                        label="일부 조건이 완료되지 않았습니다." if failed else "A/B 검토가 완료되었습니다.",
                        state="error" if failed else "complete",
                    )

    if not st.session_state.get("run_dir"):
        return
    run_dir = Path(st.session_state.run_dir)
    st.divider()
    st.header("A/B 비교 결과")
    st.caption(f"{run_dir.name} · {config['model']} · reasoning {config['reasoning_effort']}")
    treatment_result = load_result(run_dir, "treatment")
    baseline_result = load_result(run_dir, "baseline")
    a_col, b_col = st.columns(2)
    with a_col:
        render_result("A · Skill 적용", "개발 작업본의 4대 필수항목 규칙 적용", treatment_result)
    with b_col:
        render_result("B · Skill 미적용", "동일 모델의 일반 LLM 검토", baseline_result)

    st.divider()
    st.subheader("승인 가능 이메일 Excel")
    current_email = st.session_state.get("purchase_review_email")
    if isinstance(current_email, dict):
        render_approval_excel_controls(current_email, treatment_result)
    else:
        st.info("현재 실행에 사용된 이메일을 확인할 수 없습니다.")


if __name__ == "__main__":
    main()
