"""Ablation 실행기 — arm을 순서대로 돌리고 지표를 계산해 report.md를 쓴다.

    python -m experiments.ablation                          # 최신 run, A0 vs A3, 3회
    python -m experiments.ablation --arms A0,A1,A2,A3       # 사다리 전체
    python -m experiments.ablation --collect fixture        # 수집부터 새로
    python -m experiments.ablation --collect connector --query "label:OFFICEBLUE-TEST"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import gmail  # noqa: E402
from harness.codex import DEFAULT_EFFORT, DEFAULT_MODEL, event_text  # noqa: E402
from harness.run import run_arm  # noqa: E402

from . import metrics  # noqa: E402
from .seed_gmail import CASES_PATH, load_cases  # noqa: E402

# arm 정의 — 쪼갠 스킬을 하나씩 얹어가며 각자의 기여분을 분리해 본다.
ARMS: dict[str, list[str]] = {
    "A0": [],
    "A1": ["mail-classify"],
    "A2": ["mail-classify", "mail-prioritize"],
    "A3": ["mail-classify", "mail-prioritize", "mail-brief"],
}


def resolve_run(collect: str | None, query: str, max_results: int, run_id: str | None) -> Path:
    if collect:
        snapshot = gmail.collect(
            collect, cases_path=CASES_PATH, query=query, max_results=max_results
        )
        return gmail.save(snapshot)
    if run_id:
        run_dir = gmail.RUNS_DIR / run_id
        if not (run_dir / "snapshot.json").exists():
            raise SystemExit(f"스냅샷이 없습니다: {run_dir}")
        return run_dir
    runs = gmail.list_runs()
    if not runs:
        raise SystemExit(
            "스냅샷이 없습니다. 먼저 실행하세요:\n"
            "  python -m experiments.seed_gmail --mode fixture"
        )
    return runs[0]


def execute(run_dir: Path, arm_ids: list[str], reps: int, model: str, effort: str) -> dict:
    snapshot = gmail.load(run_dir)
    truth = metrics.ground_truth(snapshot, load_cases())
    print(f"스냅샷 {len(snapshot['messages'])}건 · 정답 있는 메일 {len(truth)}건 · {run_dir.name}\n")

    summary: dict[str, dict] = {}
    details: dict[str, list] = {}

    for arm_id in arm_ids:
        skills = ARMS[arm_id]
        label = ", ".join(skills) if skills else "스킬 없음"
        print(f"[{arm_id}] {label}")
        outcomes, scores = [], []
        for rep in range(1, reps + 1):
            outcome = run_arm(
                run_dir, arm_id, skills, snapshot, rep=rep,
                model=model, effort=effort,
                on_event=lambda e: _tick(event_text(e)),
            )
            scored = metrics.score(outcome["result"], snapshot, truth)
            outcomes.append(outcome)
            scores.append(scored)
            flag = "OK " if outcome["ok"] else "실패"
            print(
                f"\r  rep{rep} {flag} 정확도={scored['accuracy']} "
                f"근거={scored['evidence_rate']} 환각={len(scored['hallucinated_ids'])} "
                f"{outcome['elapsed_sec']}s" + " " * 20
            )
            if outcome["error"]:
                print(f"       {outcome['error'][:160]}")
        summary[arm_id] = metrics.aggregate(outcomes, scores)
        summary[arm_id]["skills"] = skills
        details[arm_id] = scores
        print()

    payload = {
        "run_id": run_dir.name,
        "snapshot": {"messages": len(snapshot["messages"]), "adapter": snapshot["adapter"]},
        "model": model,
        "effort": effort,
        "reps": reps,
        "summary": summary,
        "details": details,
    }
    (run_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def _tick(text: str) -> None:
    if text:
        print(f"\r    · {text[:70]}" + " " * 10, end="", flush=True)


# ------------------------------------------------------------------ 리포트

_ROWS = [
    ("정확도 (정답 라벨 대비)", "accuracy"),
    ("근거 인용률 (원문 부분문자열)", "evidence_rate"),
    ("환각 id 총계", "hallucinated_total"),
    ("커버리지", "coverage"),
    ("우선순위 재현율", "priority_recall"),
    ("스키마 통과", "schema_pass"),
    ("counts 합계 일치", "counts_consistent"),
    ("자기일관성", "self_consistency"),
    ("소요(중앙값, 초)", "elapsed_median"),
    ("출력 토큰 합", "output_tokens"),
]


def write_report(run_dir: Path, payload: dict) -> Path:
    arms = list(payload["summary"])
    lines = [
        f"# Ablation 결과 — {payload['run_id']}",
        "",
        f"- 스냅샷: {payload['snapshot']['messages']}건 (`{payload['snapshot']['adapter']}` 어댑터)",
        f"- 모델 `{payload['model']}` · effort `{payload['effort']}` · arm당 {payload['reps']}회",
        "",
        "## arm",
        "",
        "| arm | 주입 스킬 |",
        "| --- | --- |",
    ]
    for arm in arms:
        skills = payload["summary"][arm]["skills"]
        lines.append(f"| `{arm}` | {', '.join(f'`{s}`' for s in skills) if skills else '— (baseline)'} |")

    lines += ["", "## 지표", "", "| 지표 | " + " | ".join(f"`{a}`" for a in arms) + " |",
              "| --- | " + " | ".join("---" for _ in arms) + " |"]
    for title, key in _ROWS:
        cells = [_fmt(payload["summary"][a].get(key)) for a in arms]
        lines.append(f"| {title} | " + " | ".join(cells) + " |")

    lines += ["", "## 틀린 분류", ""]
    for arm in arms:
        wrong = [w for s in payload["details"][arm] for w in s["wrong"]]
        if not wrong:
            lines.append(f"- `{arm}`: 없음")
            continue
        lines.append(f"- `{arm}`:")
        for item in wrong[:10]:
            lines.append(
                f"  - `{item['message_id']}` — 정답 `{item['expected']}` / 답변 `{item['got']}`"
            )

    halluc = {
        arm: sorted({h for s in payload["details"][arm] for h in s["hallucinated_ids"]})
        for arm in arms
    }
    if any(halluc.values()):
        lines += ["", "## 환각 — 스냅샷에 없는 message_id", ""]
        for arm, ids in halluc.items():
            lines.append(f"- `{arm}`: {', '.join(f'`{i}`' for i in ids) if ids else '없음'}")

    lines += [
        "",
        "## 읽는 법",
        "",
        "정확도·근거 인용률·환각 셋만 봐도 결론이 난다. 셋 다 객관적으로 계산되고 반박할 수 없다.",
        "",
        "**결과가 예상과 다르면 그것이 결과다.** 스킬이 baseline을 이기지 못했다면 그대로 적고,",
        "어느 케이스에서 밀렸는지 위의 '틀린 분류'에서 확인해 스킬 문서를 고칠 단서로 쓴다.",
        "",
        "표본이 작다 (메일 수 × 반복 수). 소수점 둘째 자리 차이는 노이즈로 본다.",
    ]
    path = run_dir / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="스킬 유무에 따른 차이를 측정한다")
    parser.add_argument("--arms", default="A0,A3", help=f"쉼표 구분. 가능: {','.join(ARMS)}")
    parser.add_argument("--reps", type=int, default=3, help="arm당 반복 횟수")
    parser.add_argument("--collect", choices=gmail.ADAPTERS, help="지정하면 수집부터 새로 한다")
    parser.add_argument("--query", default="in:inbox is:unread newer_than:7d")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--run-id", help="기존 스냅샷 재사용")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    args = parser.parse_args()

    arm_ids = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_ids if a not in ARMS]
    if unknown:
        raise SystemExit(f"모르는 arm: {', '.join(unknown)} (가능: {', '.join(ARMS)})")

    run_dir = resolve_run(args.collect, args.query, args.max_results, args.run_id)
    payload = execute(run_dir, arm_ids, args.reps, args.model, args.effort)
    report = write_report(run_dir, payload)
    print(f"리포트 → {report}")


if __name__ == "__main__":
    main()
