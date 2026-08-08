"""Track A — 서비스 화면.

이 파일이 아는 하니스 함수는 `run_arm()` 하나뿐이다. Codex도 MCP도 모른다.
내부 구현이 codex exec에서 SDK나 HTTP로 바뀌어도 이 파일은 바뀌지 않는다.
그것이 contracts/ 를 사이에 둔 이유다.

실행:
    streamlit run ui/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import metrics                                      # noqa: E402
from experiments.ablation import ARMS                                # noqa: E402
from experiments.seed_gmail import CASES_PATH, load_cases            # noqa: E402
from harness import contracts, gmail                                 # noqa: E402
from harness.codex import DEFAULT_EFFORT, DEFAULT_MODEL, event_text  # noqa: E402
from harness.run import run_arm                                      # noqa: E402

st.set_page_config(page_title="Office Blue", page_icon="📮", layout="wide")
st.title("📮 Office Blue — 스킬 하니스 비교")
st.caption(
    "같은 메일을 스킬 있이 / 없이 분석해 차이를 본다. "
    "조작 변수는 작업공간의 `skills/` 하나뿐이다."
)

CATEGORY_KO = {
    "important": "중요",
    "ariba_approval": "구매승인",
    "discussion": "논의",
    "notice": "공지",
    "unknown": "분류불가",
}
EFFORTS = ["low", "medium", "high"]


def mask(text: str, on: bool) -> str:
    return ("*" * min(len(text), 12)) if on and text else text


def run_pane(run_dir: Path, snapshot: dict, arm_id: str, start: bool, model: str, effort: str) -> None:
    """arm 한 칸. 작업공간 내용물 → 명령 → 로그 → 결과 순으로 보여준다."""
    skills = ARMS[arm_id]
    st.markdown(f"### `{arm_id}` — {', '.join(f'`{s}`' for s in skills) if skills else '스킬 없음'}")

    # 이 arm이 실제로 보게 될 파일. 두 칸을 나란히 놓으면 조작 변수가 눈에 보인다.
    st.markdown("**작업공간에 들어가는 것**")
    st.code("\n".join(["snapshot.json", "prompt.md"] + [f"skills/{s}/…" for s in skills]), language="text")

    if start:
        log_box = st.empty()
        lines: list[str] = []

        def sink(event, box=log_box, buf=lines):
            text = event_text(event)
            if text:
                buf.append(text)
                box.code("\n".join(buf[-14:]), language="text")

        with st.spinner(f"{arm_id} 실행 중…"):
            st.session_state[f"outcome_{arm_id}"] = run_arm(
                run_dir, arm_id, skills, snapshot,
                rep=1, model=model, effort=effort, on_event=sink,
            )

    outcome = st.session_state.get(f"outcome_{arm_id}")
    if not outcome:
        return

    with st.expander("실행된 명령 전문"):
        st.code(" ".join(outcome["command"]), language="bash")
    prompt_path = run_dir / arm_id / "workspace" / "prompt.md"
    if prompt_path.exists():
        with st.expander("이 arm이 받은 프롬프트"):
            st.code(prompt_path.read_text(encoding="utf-8"), language="markdown")

    if outcome["ok"]:
        st.success(f"스키마 통과 · {outcome['elapsed_sec']}초")
    else:
        st.error(outcome["error"] or "스키마 위반")
        for err in outcome["schema_errors"][:5]:
            st.caption(f"· {err}")
    if outcome["result"]:
        with st.expander("결과 JSON"):
            st.json(outcome["result"], expanded=False)


collect_tab, run_tab, compare_tab = st.tabs(["① 수집", "② 실행 (A/B)", "③ 비교"])

# ────────────────────────────────────────────────────────────── ① 수집
with collect_tab:
    st.subheader("메일 스냅샷 만들기")
    st.markdown(
        "수집은 **한 번만** 한다. 이후 모든 arm이 이 파일 하나를 본다. 덕분에 분석은 Gmail에 "
        "접속하지 않고, 재현 가능하며, 메일함이 바뀌어도 결과가 오염되지 않는다."
    )

    left, right = st.columns([1, 2])
    with left:
        adapter = st.radio(
            "수집 경로", gmail.ADAPTERS,
            format_func=lambda a: {
                "fixture": "fixture — cases.yaml (Gmail 불필요)",
                "connector": "connector — OpenAI Gmail 커넥터",
                "local-mcp": "local-mcp — 로컬 Gmail MCP 서버",
            }[a],
        )
        query = st.text_input(
            "검색 조건", "in:inbox is:unread newer_than:7d", disabled=adapter == "fixture"
        )
        max_results = st.number_input("최대 건수", 1, 200, 50, help="스토리보드 기본값은 50건")
        go = st.button("스냅샷 만들기", type="primary", use_container_width=True)

    with right:
        st.markdown("**실행될 것**")
        if adapter == "fixture":
            st.code(f"{CASES_PATH.name} → snapshot.json    # Gmail 호출 없음", language="text")
        else:
            st.code(
                "codex exec --ephemeral --sandbox read-only\n"
                "  --output-schema contracts/snapshot.schema.json\n"
                f'  # 프롬프트: "{query}" 를 읽기 전용 도구로만 조회',
                language="bash",
            )
            st.caption("읽기 전용이다. 발송·초안·라벨 변경 도구는 쓰지 않는다.")

    if go:
        with st.status("수집 중…", expanded=True) as status:
            try:
                snapshot = gmail.collect(
                    adapter, cases_path=CASES_PATH, query=query, max_results=int(max_results)
                )
                errors = contracts.validate(contracts.SNAPSHOT, snapshot)
                if errors:
                    status.update(label="계약 위반", state="error")
                    st.error("\n".join(errors[:10]))
                else:
                    st.session_state["run_dir"] = str(gmail.save(snapshot))
                    status.update(label=f"{len(snapshot['messages'])}건 수집 완료", state="complete")
            except Exception as exc:  # noqa: BLE001
                status.update(label="수집 실패", state="error")
                st.exception(exc)

    runs = gmail.list_runs()
    if runs:
        st.divider()
        names = [p.name for p in runs]
        current = Path(st.session_state.get("run_dir", "")).name
        chosen = st.selectbox(
            "작업할 스냅샷", runs, format_func=lambda p: p.name,
            index=names.index(current) if current in names else 0,
        )
        st.session_state["run_dir"] = str(chosen)

        snapshot = gmail.load(chosen)
        masked = st.toggle("본문·제목 가리기", value=False, help="화면 공유 중이면 켠다")
        st.dataframe(
            [
                {
                    "message_id": m["message_id"],
                    "from": mask(m["from"], masked),
                    "subject": mask(m["subject"], masked),
                    "date": m["date"][:16],
                    "첨부": len(m["attachments"]),
                }
                for m in snapshot["messages"]
            ],
            use_container_width=True, hide_index=True,
        )

ready = bool(st.session_state.get("run_dir"))

# ────────────────────────────────────────────────────────── ② 실행 (A/B)
with run_tab:
    st.subheader("두 조건을 나란히 실행")
    if not ready:
        st.info("먼저 ① 수집 탭에서 스냅샷을 만드세요.")
    else:
        run_dir = Path(st.session_state["run_dir"])
        snapshot = gmail.load(run_dir)

        cfg = st.columns(4)
        arm_left = cfg[0].selectbox("왼쪽 arm", list(ARMS), index=0, key="arm_left")
        arm_right = cfg[1].selectbox("오른쪽 arm", list(ARMS), index=len(ARMS) - 1, key="arm_right")
        model = cfg[2].text_input("모델", DEFAULT_MODEL)
        effort = cfg[3].selectbox("reasoning effort", EFFORTS, index=EFFORTS.index(DEFAULT_EFFORT))
        st.caption(
            "모델·effort·출력 스키마·스냅샷은 두 arm에 동일하게 고정된다. "
            "다른 것은 `skills/` 하나뿐이다."
        )

        start = st.button("두 arm 실행", type="primary")
        panes = st.columns(2)
        for pane, arm_id in zip(panes, (arm_left, arm_right)):
            with pane:
                run_pane(run_dir, snapshot, arm_id, start, model, effort)

# ───────────────────────────────────────────────────────────── ③ 비교
with compare_tab:
    st.subheader("무엇이 달라졌나")
    if not ready:
        st.info("먼저 ① 수집 탭에서 스냅샷을 만드세요.")
    else:
        run_dir = Path(st.session_state["run_dir"])
        report_path = run_dir / "report.md"
        if report_path.exists():
            with st.expander("전체 리포트 (experiments/ablation.py 결과)", expanded=True):
                st.markdown(report_path.read_text(encoding="utf-8"))
        else:
            st.info(
                "반복 실행까지 포함한 전체 리포트는 터미널에서 만듭니다.\n\n"
                "`python -m experiments.ablation --arms A0,A1,A2,A3 --reps 3`"
            )

        left = st.session_state.get(f"outcome_{st.session_state.get('arm_left')}")
        right = st.session_state.get(f"outcome_{st.session_state.get('arm_right')}")
        if not (left and right and left["result"] and right["result"]):
            st.caption("② 탭에서 두 arm을 실행하면 여기에 대조표가 나옵니다.")
        else:
            st.divider()
            blind = st.toggle(
                "arm 이름 가리기 (블라인드)", value=False,
                help="어느 쪽이 스킬 쪽인지 모르게 한다. 사람이 평가할 때 확증편향을 막는다.",
            )
            name_l, name_r = ("좌", "우") if blind else (left["arm"], right["arm"])

            snapshot = gmail.load(run_dir)
            truth = metrics.ground_truth(snapshot, load_cases())
            score_l = metrics.score(left["result"], snapshot, truth)
            score_r = metrics.score(right["result"], snapshot, truth)

            cols = st.columns(4)
            for col, title, key in zip(
                cols,
                ("정확도", "근거 인용률", "우선순위 재현율", "환각 id"),
                ("accuracy", "evidence_rate", "priority_recall", "hallucinated_ids"),
            ):
                a, b = score_l[key], score_r[key]
                if key == "hallucinated_ids":
                    a, b = len(a), len(b)
                col.metric(
                    f"{title} · {name_r}",
                    b if b is not None else "—",
                    delta=None if a is None or b is None else round(b - a, 3),
                    delta_color="inverse" if key == "hallucinated_ids" else "normal",
                )
                col.caption(f"{name_l}: {a if a is not None else '—'}")

            rows = []
            for message in snapshot["messages"]:
                mid = message["message_id"]
                got_l, got_r = score_l["labels"].get(mid), score_r["labels"].get(mid)
                answer = (truth.get(mid) or {}).get("category")
                rows.append({
                    "제목": message["subject"][:44],
                    name_l: CATEGORY_KO.get(got_l, got_l or "—"),
                    name_r: CATEGORY_KO.get(got_r, got_r or "—"),
                    "정답": CATEGORY_KO.get(answer, answer or "—"),
                    "불일치": "⚠" if got_l != got_r else "",
                    f"{name_l} 오답": "✗" if answer and got_l != answer else "",
                    f"{name_r} 오답": "✗" if answer and got_r != answer else "",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

            brief_l, brief_r = st.columns(2)
            for col, name, outcome in ((brief_l, name_l, left), (brief_r, name_r, right)):
                with col:
                    st.markdown(f"**{name} 브리핑**")
                    st.text((outcome["result"].get("briefing") or {}).get("summary", ""))
                    notes = outcome["result"].get("notes") or []
                    if notes:
                        st.caption("notes: " + " / ".join(notes[:4]))
