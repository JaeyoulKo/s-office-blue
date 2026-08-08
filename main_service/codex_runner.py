from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .skill_registry import resolve_skill


class CodexRunError(RuntimeError):
    """Raised when Codex cannot complete a local Skill run."""


@dataclass(frozen=True)
class CodexResult:
    text: str
    parsed: dict[str, Any] | list[Any] | None

    def display_value(self) -> Any:
        return self.parsed if self.parsed is not None else self.text


def codex_version() -> str:
    try:
        completed = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unavailable"
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def run_codex(
    *,
    prompt: str,
    payload: dict[str, Any],
    skill: str | None,
    model: str | None = None,
    timeout_seconds: int = 300,
) -> CodexResult:
    """Run Codex in an isolated workspace containing only the selected Skill."""
    with tempfile.TemporaryDirectory(prefix="office-blue-") as temp_name:
        workspace = Path(temp_name)
        (workspace / "input.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (workspace / "AGENTS.md").write_text(
            "Read local input only. Do not use networks or change external systems.\n",
            encoding="utf-8",
        )

        if skill is not None:
            destination = workspace / ".agents" / "skills" / skill
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(resolve_skill(skill), destination)

        output_path = workspace / "last-message.txt"
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_path),
            "--cd",
            str(workspace),
        ]
        if model:
            command.extend(["--model", model])
        command.append("-")

        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=workspace,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise CodexRunError("Codex CLI를 찾을 수 없습니다.") from exc
        except subprocess.TimeoutExpired as exc:
            raise CodexRunError("Codex 실행 시간이 초과되었습니다.") from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip()[-1000:]
            raise CodexRunError(
                f"Codex 실행 실패(exit {completed.returncode}): {detail or 'no stderr'}"
            )
        if not output_path.is_file():
            raise CodexRunError("Codex 결과 파일이 생성되지 않았습니다.")

        text = output_path.read_text(encoding="utf-8").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        return CodexResult(text=text, parsed=parsed)
