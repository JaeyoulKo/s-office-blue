"""run_arm() — UI와 실험 스크립트가 아는 유일한 함수.

    run_arm(run_dir, arm_id, skills, snapshot) -> dict

이 시그니처가 인터페이스의 전부다. 내부가 codex exec에서 다른 것으로 바뀌어도
`ui/app.py`와 `experiments/ablation.py`는 바뀌지 않는다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from . import contracts, workspace
from .codex import DEFAULT_EFFORT, DEFAULT_MODEL, build_command, event_text, run, usage_of


def run_arm(
    run_dir: Path,
    arm_id: str,
    skills: list[str],
    snapshot: dict,
    rep: int = 1,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    timeout: int = 900,
) -> dict:
    """arm 하나를 1회 실행한다.

    run_dir : experiments/runs/<run-id>
    arm_id  : 'A0' 같은 식별자. 하위 디렉터리 이름이 된다.
    skills  : 이 arm에 주입할 스킬 이름 목록. []이면 baseline.
    snapshot: contracts/snapshot.schema.json 을 만족하는 dict.
    """
    arm_dir = run_dir / arm_id
    ws_dir = arm_dir / "workspace"
    rep_dir = arm_dir / f"rep-{rep}"
    rep_dir.mkdir(parents=True, exist_ok=True)

    # 작업공간은 arm당 한 번만 만든다. 반복 실행은 입력이 같고 출력 경로만 다르다.
    ws_info = (
        workspace.describe(ws_dir, skills) if ws_dir.exists()
        else workspace.build(ws_dir, snapshot, skills)
    )

    result_path = rep_dir / "result.json"
    command = build_command(
        workspace=ws_dir,
        schema_path=contracts.path_of(contracts.TRIAGE),
        out_path=result_path,
        model=model,
        effort=effort,
    )
    (rep_dir / "command.txt").write_text(" ".join(command), encoding="utf-8")

    events: list[dict[str, Any]] = []

    def collect(event: dict[str, Any]) -> None:
        events.append(event)
        if on_event:
            on_event(event)

    started = time.monotonic()
    error: str | None = None
    try:
        code, events = run(command, ws_info["prompt"], collect, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — 실패도 실험 결과다. 기록하고 넘어간다.
        code, error = -1, f"{type(exc).__name__}: {exc}"
    elapsed = round(time.monotonic() - started, 2)

    (rep_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8"
    )
    (rep_dir / "stdout.log").write_text(
        "\n".join(event_text(e) for e in events), encoding="utf-8"
    )

    payload: dict | None = None
    if result_path.exists():
        # utf-8-sig: codex가 BOM을 붙여 쓰더라도 json.loads 가 깨지지 않게.
        raw = result_path.read_text(encoding="utf-8-sig").strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            error = error or f"출력이 JSON이 아닙니다 (계약 위반). 앞부분: {raw[:300]}"
    elif error is None:
        error = f"결과 파일이 생성되지 않았습니다 (exit={code})."

    schema_errors = contracts.validate(contracts.TRIAGE, payload) if payload is not None else []

    outcome = {
        "arm": arm_id,
        "rep": rep,
        "skills": list(skills),
        "ok": payload is not None and not schema_errors,
        "exit_code": code,
        "error": error,
        "schema_errors": schema_errors,
        "elapsed_sec": elapsed,
        "usage": usage_of(events),
        "model": model,
        "effort": effort,
        "command": command,
        "workspace": {k: v for k, v in ws_info.items() if k != "prompt"},
        "result": payload,
    }
    (rep_dir / "outcome.json").write_text(
        json.dumps({k: v for k, v in outcome.items() if k != "result"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return outcome
