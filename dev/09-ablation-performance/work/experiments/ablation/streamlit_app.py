from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = "purchase-email-review"
EXPERIMENT_DIR = Path(__file__).resolve().parent / EXPERIMENT
RUNNER = Path(__file__).resolve().parent / "run.py"
UPLOAD_DIR = ROOT / "experiments" / "instances" / ".uploads"


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
            try:
                return json.loads(text)
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
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if line.startswith("AB_EVENT "):
                if on_event is not None:
                    on_event(json.loads(line.removeprefix("AB_EVENT ")))
            elif line:
                result_path = Path(line)
        assert process.stderr is not None
        stderr = process.stderr.read().strip()
        process.wait()
    finally:
        case_path.unlink(missing_ok=True)
    if result_path is None:
        raise RuntimeError(stderr or "실험 결과를 확인할 수 없습니다.")
    return result_path


def render_result(title: str, caption: str, result: object) -> None:
    st.markdown(f"### {title}")
    st.caption(caption)
    with st.container(border=True):
        if not isinstance(result, dict):
            st.code(str(result), language="text")
            return
        st.markdown("#### 검토 상태")
        st.write(result.get("review_status") or result.get("status") or "상태 미지정")
        st.markdown("#### 필수 항목 검토")
        st.write(result.get("checks") or result.get("missing_information") or "별도 구조로 반환됨")
        st.markdown("#### 보완 요청 자동 답장")
        draft = result.get("reply_draft") or result.get("reply_draft_ko")
        st.write(draft or "초안 없음")
        guidance = result.get("approval_guidance")
        if guidance:
            st.markdown("#### 승인 검토 안내")
            st.write(guidance)
        with st.expander("전체 Codex 결과"):
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
                "attachments": st.session_state.get("email_attachments", []),
                "approval_url": approval_url,
            }
            with st.status("A/B 검토를 시작합니다...", expanded=True) as run_status:
                baseline_status = st.empty()
                treatment_status = st.empty()
                failed_conditions: set[str] = set()

                def show_event(event: dict[str, object]) -> None:
                    condition = str(event["condition"])
                    state = str(event["state"])
                    label = "B · Skill 미적용" if condition == "baseline" else "A · Skill 적용"
                    slot = baseline_status if condition == "baseline" else treatment_status
                    if state == "running":
                        slot.info(f"{label}: 실행 중")
                    elif state == "completed":
                        slot.success(f"{label}: 완료")
                    else:
                        failed_conditions.add(condition)
                        slot.error(f"{label}: {event.get('error') or '실행 실패'}")

                try:
                    st.session_state.run_dir = str(run_ab(email, show_event))
                except RuntimeError as exc:
                    run_status.update(label="A/B 검토 실행 실패", state="error")
                    st.error(str(exc))
                else:
                    if failed_conditions:
                        run_status.update(label="일부 조건이 완료되지 않았습니다.", state="error")
                    else:
                        run_status.update(label="A/B 검토가 완료되었습니다.", state="complete")

    if not st.session_state.get("run_dir"):
        return
    run_dir = Path(st.session_state.run_dir)
    st.divider()
    st.header("A/B 비교 결과")
    st.caption(f"{run_dir.name} · {config['model']} · reasoning {config['reasoning_effort']}")
    a_col, b_col = st.columns(2)
    with a_col:
        render_result("A · Skill 적용", "개발 작업본의 4대 필수항목 규칙 적용", load_result(run_dir, "treatment"))
    with b_col:
        render_result("B · Skill 미적용", "동일 모델의 일반 LLM 검토", load_result(run_dir, "baseline"))


if __name__ == "__main__":
    main()
