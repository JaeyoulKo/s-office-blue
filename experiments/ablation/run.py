from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main_service.codex_runner import CodexResult, codex_version, run_codex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_result(folder: Path, result: CodexResult) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "output.txt").write_text(result.text + "\n", encoding="utf-8")
    if result.parsed is not None:
        (folder / "result.json").write_text(
            json.dumps(result.parsed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def emit_event(condition: str, state: str, **details: object) -> None:
    """Stream one condition's progress to the caller as a single stdout line."""
    event = {"condition": condition, "state": state, **details}
    print(f"AB_EVENT {json.dumps(event, ensure_ascii=False)}", flush=True)


def result_contract_error(result: CodexResult, config: dict[str, object]) -> str | None:
    allowed_labels = config.get("allowed_labels")
    if not isinstance(allowed_labels, list) or not allowed_labels:
        return None
    if result.parsed is None or not isinstance(result.parsed, dict):
        return "JSON 객체로 파싱되지 않았습니다."
    label = result.parsed.get("label")
    if label not in allowed_labels:
        allowed = ", ".join(f"`{item}`" for item in allowed_labels)
        return f"label `{label or '없음'}`은 허용되지 않습니다. 허용값: {allowed}"
    return None


def contract_retry_prompt(prompt: str, contract_error: str) -> str:
    return (
        f"{prompt}\n\n"
        "직전 출력이 아래 계약을 위반했습니다. input.json을 다시 읽고 사실과 부정 표현을 "
        "재확인한 뒤, 계약을 만족하는 JSON 전체를 다시 반환하세요. 직전 출력의 라벨이나 "
        "근거를 그대로 답습하지 마세요.\n"
        f"계약 오류: {contract_error}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Skill ablation experiment.")
    parser.add_argument("experiment", help="Directory name under experiments/ablation")
    parser.add_argument("--case", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--service-tier",
        help="Override experiment.json service_tier for this run (e.g. priority).",
    )
    args = parser.parse_args()

    experiment_dir = Path(__file__).resolve().parent / args.experiment
    config = json.loads((experiment_dir / "experiment.json").read_text(encoding="utf-8"))
    prompt_path = experiment_dir / config.get("prompt", "prompt.md")
    case_path = args.case or Path(config["cases"][0])
    if not case_path.is_absolute():
        case_path = ROOT / case_path

    run_id = args.run_id or f'{args.experiment}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}'
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise SystemExit("run-id may contain only letters, digits, dot, underscore, and hyphen")
    run_dir = ROOT / "experiments" / "instances" / run_id
    if run_dir.exists():
        raise SystemExit(f"Run already exists: {run_dir}")

    case_bytes = case_path.read_bytes()
    prompt = prompt_path.read_text(encoding="utf-8")
    payload = {config.get("input_key", "input"): json.loads(case_bytes.decode("utf-8"))}
    for key, relative_path in config.get("context", {}).items():
        payload[key] = (ROOT / relative_path).read_text(encoding="utf-8")
    run_dir.mkdir(parents=True)
    shutil.copy2(case_path, run_dir / "input.json")
    observation_path = experiment_dir / "observation.md"
    if observation_path.is_file():
        shutil.copy2(observation_path, run_dir / "observation.md")

    treatment_path = config.get("treatment_skill_path")
    timeout_seconds = int(config.get("condition_timeout_seconds", 150))
    max_contract_retries = int(config.get("max_contract_retries", 0))
    service_tier = args.service_tier or config.get("service_tier")

    manifest = {
        "run_id": run_id,
        "experiment": config["name"],
        "created_at": utc_now(),
        "finished_at": None,
        "codex_version": codex_version(),
        "model": config["model"],
        "reasoning_effort": config["reasoning_effort"],
        "service_tier": service_tier,
        "input_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "conditions": {},
    }

    conditions = (("baseline", None), ("treatment", config["treatment_skill"]))

    def execute_condition(condition: str, skill: str | None) -> dict[str, object]:
        started_at = utc_now()
        emit_event(condition, "running", timeout_seconds=timeout_seconds)
        use_path = treatment_path and condition == "treatment"
        attempts = 0
        try:
            current_prompt = prompt
            while True:
                attempts += 1
                result = run_codex(
                    prompt=current_prompt,
                    payload=payload,
                    skill=None if use_path else skill,
                    skill_path=(ROOT / treatment_path) if use_path else None,
                    model=config["model"],
                    reasoning_effort=config["reasoning_effort"],
                    service_tier=service_tier,
                    timeout_seconds=timeout_seconds,
                )
                contract_error = result_contract_error(result, config)
                if contract_error is None:
                    break
                invalid_dir = run_dir / condition
                invalid_dir.mkdir(parents=True, exist_ok=True)
                (invalid_dir / f"invalid-output-attempt-{attempts}.txt").write_text(
                    result.text + "\n", encoding="utf-8"
                )
                if attempts > max_contract_retries:
                    raise ValueError(f"분류 출력 계약 위반: {contract_error}")
                emit_event(
                    condition,
                    "retrying",
                    attempt=attempts + 1,
                    error=contract_error,
                )
                current_prompt = contract_retry_prompt(prompt, contract_error)
            save_result(run_dir / condition, result)
            error = None
            emit(condition, "completed")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            error_dir = run_dir / condition
            error_dir.mkdir(parents=True, exist_ok=True)
            (error_dir / "error.txt").write_text(error + "\n", encoding="utf-8")
        emit_event(condition, "failed" if error else "completed", error=error)
        return {
            "skill": skill,
            "skill_path": treatment_path if use_path else None,
            "attempts": attempts,
            "started_at": started_at,
            "finished_at": utc_now(),
            "error": error,
        }

    # baseline and treatment are independent, so wall clock is the slower of the two
    # rather than their sum.
    with ThreadPoolExecutor(max_workers=len(conditions), thread_name_prefix="ablation") as executor:
        futures = {
            condition: executor.submit(execute_condition, condition, skill)
            for condition, skill in conditions
        }
        for condition, future in futures.items():
            manifest["conditions"][condition] = future.result()

    manifest["finished_at"] = utc_now()
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(run_dir)
    if any(item["error"] for item in manifest["conditions"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
