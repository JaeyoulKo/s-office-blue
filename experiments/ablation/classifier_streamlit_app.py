from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = "email-classifier"
EXPERIMENT_DIR = Path(__file__).resolve().parent / EXPERIMENT
RUNNER = Path(__file__).resolve().parent / "run.py"


AMOUNT_PATTERN = re.compile(
    r"(?:"
    r"(?:KRW|USD|EUR|JPY|₩|\$|€|¥)\s*[0-9][0-9,]*(?:\.[0-9]+)?"
    r"|[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:KRW|USD|EUR|JPY|원|만원|억원|달러|엔)"
    r")",
    re.IGNORECASE,
)
KOREAN_COMPOSITE_AMOUNT_PATTERN = re.compile(
    r"[0-9][0-9,]*(?:\.[0-9]+)?\s*억(?:\s*[0-9][0-9,]*(?:\.[0-9]+)?\s*만)?원"
)


def email_text(email: dict[str, object]) -> tuple[str, str]:
    messages = email.get("messages")
    if isinstance(messages, list) and messages:
        valid_messages = [message for message in messages if isinstance(message, dict)]
        if valid_messages:
            latest = valid_messages[-1]
            subject = str(latest.get("subject") or email.get("title") or "")
            body = "\n\n".join(
                "\n".join(
                    (
                        f"보낸 사람: {message.get('from') or ''}",
                        f"날짜: {message.get('date') or ''}",
                        f"제목: {message.get('subject') or ''}",
                        str(message.get("body") or ""),
                    )
                )
                for message in valid_messages
            )
            return subject, body

    subject = str(email.get("subject") or email.get("email_subject") or "")
    if email.get("body") or email.get("email_body"):
        return subject, str(email.get("body") or email.get("email_body"))

    cost = email.get("cost_breakdown") if isinstance(email.get("cost_breakdown"), dict) else {}
    effects = email.get("expected_effects") if isinstance(email.get("expected_effects"), dict) else {}
    body = "\n".join(
        (
            f"요청자: {email.get('requester') or 'unknown'}",
            f"구매 유형: {email.get('type') or 'unknown'}",
            f"품목/서비스 및 목적: {email.get('description') or 'unknown'}",
            f"공급사: {email.get('vendor') or 'unknown'}",
            f"금액: {email.get('total_amount') or 'unknown'}",
            f"비용 산출 근거: {cost.get('details') or 'unknown'}",
            f"예상 정량 효과: {effects.get('details') or 'unknown'}",
            f"최근 의견: {email.get('recent_comments') or 'unknown'}",
        )
    )
    return subject, body


def email_amount(email: dict[str, object], subject: str, body: str) -> str:
    structured = str(email.get("total_amount") or "").strip()
    if structured:
        return structured
    messages = email.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[-1], dict):
        latest_body = str(messages[-1].get("body") or "")
        match = KOREAN_COMPOSITE_AMOUNT_PATTERN.search(latest_body) or AMOUNT_PATTERN.search(latest_body)
        if match:
            return match.group(0).strip()
    for text in (subject, body):
        match = KOREAN_COMPOSITE_AMOUNT_PATTERN.search(text) or AMOUNT_PATTERN.search(text)
        if match:
            return match.group(0).strip()
    return "금액 미상"


def load_result(run_dir: Path, condition: str) -> object:
    folder = run_dir / condition
    for filename in ("result.json", "output.txt", "error.txt"):
        path = folder / filename
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if filename == "error.txt":
                return {"error": text.strip()}
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
    case_path: Path,
    on_event: Callable[[dict[str, object]], None] | None = None,
) -> Path:
    process = subprocess.Popen(
        [sys.executable, "-u", str(RUNNER), EXPERIMENT, "--case", str(case_path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    result_path: Path | None = None
    for raw_line in process.stdout or ():
        line = raw_line.strip()
        if line.startswith("AB_EVENT "):
            if on_event is not None:
                on_event(json.loads(line.removeprefix("AB_EVENT ")))
        elif line:
            result_path = Path(line)
    stderr = process.stderr.read().strip() if process.stderr else ""
    process.wait()
    if result_path is None:
        raise RuntimeError(stderr or "실험 결과를 확인할 수 없습니다.")
    return result_path


def render_result(title: str, result: object, amount: str) -> None:
    st.markdown(f"### {title}")
    with st.container(border=True):
        if not isinstance(result, dict):
            st.code(str(result), language="text")
            return
        st.markdown("#### 분류")
        st.write(result.get("label") or "분류 미지정")
        st.markdown("#### 금액")
        st.write(amount)
        st.markdown("#### 긴급도")
        st.write(result.get("urgency") or "긴급도 미지정")
        st.markdown("#### 요약")
        st.write(result.get("summary") or "요약 없음")
        st.markdown("#### 권장 다음 단계")
        st.write(result.get("recommended_action") or "권장 조치 없음")
        with st.expander("전체 결과"):
            st.json(result)


def main() -> None:
    st.set_page_config(page_title="Email Classifier A/B", page_icon="✉️", layout="wide")
    config = json.loads((EXPERIMENT_DIR / "experiment.json").read_text(encoding="utf-8"))
    cases = [ROOT / relative_path for relative_path in config["cases"]]

    st.title("Email Classifier A/B 테스트")
    st.caption("동일한 이메일을 Skill 미적용 baseline과 적용 treatment로 분류합니다.")

    case_path = st.selectbox("테스트 케이스", cases, format_func=lambda path: path.name)
    email = json.loads(case_path.read_text(encoding="utf-8"))
    subject, body = email_text(email)
    amount = email_amount(email, subject, body)
    st.markdown("### 이메일")
    st.write(f"**제목:** {subject}")
    st.text(body)

    if st.button("Classifier A/B 실행", type="primary", use_container_width=True):
        with st.status("A와 B를 동시에 실행합니다...", expanded=True) as status:
            slots = {"treatment": st.empty(), "baseline": st.empty()}
            labels = {"treatment": "A · Skill 적용", "baseline": "B · Skill 미적용"}
            failed: set[str] = set()

            def show_event(event: dict[str, object]) -> None:
                condition = str(event.get("condition") or "")
                state = str(event.get("state") or "")
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
                    slot.error(f"{label}: 실패 — {event.get('error') or '원인 미상'}")

            try:
                st.session_state.classifier_run_dir = str(run_ab(case_path, show_event))
            except RuntimeError as exc:
                status.update(label="실행 실패", state="error", expanded=True)
                st.error(str(exc))
            else:
                status.update(
                    label="일부 조건 실패" if failed else "A/B 실행 완료",
                    state="error" if failed else "complete",
                    expanded=bool(failed),
                )

    if not st.session_state.get("classifier_run_dir"):
        return

    run_dir = Path(st.session_state.classifier_run_dir)
    st.divider()
    st.header("A/B 비교 결과")
    treatment, baseline = st.columns(2)
    with treatment:
        render_result("A · Email Classifier Skill 적용", load_result(run_dir, "treatment"), amount)
    with baseline:
        render_result("B · Skill 미적용", load_result(run_dir, "baseline"), amount)


if __name__ == "__main__":
    main()
