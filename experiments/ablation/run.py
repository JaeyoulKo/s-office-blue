from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Skill ablation experiment.")
    parser.add_argument("experiment", help="Directory name under experiments/ablation")
    parser.add_argument("--case", type=Path)
    parser.add_argument("--run-id")
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

    manifest = {
        "run_id": run_id,
        "experiment": config["name"],
        "created_at": utc_now(),
        "finished_at": None,
        "codex_version": codex_version(),
        "model": config["model"],
        "reasoning_effort": config["reasoning_effort"],
        "input_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "conditions": {},
    }

    for condition, skill in (("baseline", None), ("treatment", config["treatment_skill"])):
        started_at = utc_now()
        try:
            result = run_codex(
                prompt=prompt,
                payload=payload,
                skill=skill,
                model=config["model"],
                reasoning_effort=config["reasoning_effort"],
            )
            save_result(run_dir / condition, result)
            error = None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            error_dir = run_dir / condition
            error_dir.mkdir()
            (error_dir / "error.txt").write_text(error + "\n", encoding="utf-8")
        manifest["conditions"][condition] = {
            "skill": skill,
            "started_at": started_at,
            "finished_at": utc_now(),
            "error": error,
        }

    manifest["finished_at"] = utc_now()
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(run_dir)
    if any(item["error"] for item in manifest["conditions"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
