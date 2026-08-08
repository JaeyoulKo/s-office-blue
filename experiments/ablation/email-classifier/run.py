from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main_service.codex_runner import CodexResult, codex_version, run_codex


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("email-classifier-%Y%m%d-%H%M%S")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_result(folder: Path, result: CodexResult) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "output.txt").write_text(result.text + "\n", encoding="utf-8")
    if result.parsed is not None:
        (folder / "result.json").write_text(
            json.dumps(result.parsed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    config = json.loads((EXPERIMENT_DIR / "experiment.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description="Run one exploratory Skill ablation instance.")
    parser.add_argument("--case", type=Path, default=ROOT / config["cases"][0])
    parser.add_argument("--model", default=None)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    case_path = args.case if args.case.is_absolute() else ROOT / args.case
    case_bytes = case_path.read_bytes()
    email = json.loads(case_bytes.decode("utf-8"))
    taxonomy = (ROOT / "shared" / "taxonomy.md").read_text(encoding="utf-8")
    prompt = (EXPERIMENT_DIR / "prompt.md").read_text(encoding="utf-8")
    payload = {"email": email, "taxonomy": taxonomy}

    run_id = args.run_id or new_run_id()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise SystemExit("run-id may contain only letters, digits, dot, underscore, and hyphen")
    run_dir = ROOT / "experiments" / "instances" / run_id
    if run_dir.exists():
        raise SystemExit(f"Run already exists: {run_dir}")

    (run_dir / "input").mkdir(parents=True)
    shutil.copy2(case_path, run_dir / "input" / "email.json")
    shutil.copy2(EXPERIMENT_DIR / "observation.md", run_dir / "observation.md")

    manifest = {
        "run_id": run_id,
        "experiment": config["name"],
        "exploratory": True,
        "created_at": now(),
        "finished_at": None,
        "codex_version": codex_version(),
        "model": args.model or "local-default",
        "input_sha256": sha256(case_bytes),
        "prompt_sha256": sha256(prompt.encode("utf-8")),
        "conditions": {},
        "errors": [],
    }

    for condition, skill in (
        ("baseline", None),
        ("treatment", config["treatment_skill"]),
    ):
        entry = {"skill": skill, "started_at": now(), "finished_at": None, "error": None}
        try:
            result = run_codex(
                prompt=prompt,
                payload=payload,
                skill=skill,
                model=args.model,
            )
            save_result(run_dir / condition, result)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            manifest["errors"].append(f"{condition}: {entry['error']}")
            error_dir = run_dir / condition
            error_dir.mkdir(parents=True, exist_ok=True)
            (error_dir / "error.txt").write_text(entry["error"] + "\n", encoding="utf-8")
        entry["finished_at"] = now()
        manifest["conditions"][condition] = entry

    manifest["finished_at"] = now()
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(run_dir)
    if manifest["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
