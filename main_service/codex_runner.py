from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .skill_registry import resolve_skill


class CodexRunError(RuntimeError):
    """Raised when Codex cannot complete a local Skill run.

    `kind` lets a caller decide whether retrying is worth anything without matching on
    the Korean message text. A batch retries `timeout` and `exit`, but retrying
    `missing_cli` just fails N more times at the same speed.
    """

    def __init__(self, message: str, *, kind: str = "unknown") -> None:
        super().__init__(message)
        self.kind = kind


# Codex reads workspace files by shelling out to Windows PowerShell 5.1
# (`Get-Content -Raw -LiteralPath ...`). Without a BOM that cmdlet decodes the file
# with the system ANSI codepage (CP949 on Korean Windows), which mangles Hangul into
# mojibake before the model ever sees it. Every file Codex may read is therefore
# written with a UTF-8 BOM.
CODEX_TEXT_SUFFIXES = frozenset({".md", ".json", ".txt", ".yaml", ".yml", ".toml", ".csv"})


# Codex only enforces "you must use this skill" for skills registered under
# `$CODEX_HOME/skills/`. A Skill copied into the workspace is just a file the model may
# read and then ignore: measured 3/3 reads but only 1/3 adherence. Restating the mandate
# in AGENTS.md — which is always part of the model-visible prompt — raised adherence to
# 3/3 without changing the request text, so both conditions keep the same prompt.
SKILL_MANDATE = (
    "\n"
    "이 작업공간에는 `.agents/skills/{name}/SKILL.md` 에 적용해야 할 Skill 이 있습니다.\n"
    "작업을 시작하기 전에 그 SKILL.md 를 끝까지 읽고, 그 안에서 참조하는 파일도 모두 읽은 뒤\n"
    "거기 정의된 절차와 출력 형식을 그대로 따르세요.\n"
)

BASE_AGENTS_MD = "Read local input only. Do not use networks or change external systems.\n"


def parse_codex_json(text: str) -> dict[str, Any] | list[Any] | None:
    """Parse Codex output, tolerating a ```json fence.

    The Skill contract forbids fences, but a run without that Skill has no such rule and
    routinely wraps its JSON. Dropping the fence keeps the baseline result structured
    instead of degrading it to raw text.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[A-Za-z0-9_-]*[ \t]*\r?\n?", "", candidate)
        candidate = re.sub(r"\r?\n?```$", "", candidate).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def write_for_codex(path: Path, text: str) -> None:
    """Write a file that Codex will read, in an encoding PowerShell decodes correctly."""
    path.write_text(text, encoding="utf-8-sig")


def copy_tree_for_codex(source: Path, destination: Path) -> None:
    """Copy a Skill folder, re-encoding its text files so Codex reads them intact."""
    shutil.copytree(source, destination)
    for path in destination.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in CODEX_TEXT_SUFFIXES:
            continue
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        write_for_codex(path, text)


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
    skill_path: Path | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: int = 300,
) -> CodexResult:
    """Run Codex in an isolated workspace containing only the selected Skill.

    `skill` names an approved Skill under `skills/`. `skill_path` points at an
    in-progress working copy under `dev/` and wins when both are given.
    `service_tier="priority"` buys latency with quota: same model and output, but
    the request is processed ahead of the default queue.
    """
    with tempfile.TemporaryDirectory(prefix="office-blue-") as temp_name:
        workspace = Path(temp_name)
        write_for_codex(
            workspace / "input.json",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        source: Path | None = None
        if skill_path is not None:
            source = Path(skill_path)
            if not (source / "SKILL.md").is_file():
                raise CodexRunError(f"Skill 파일이 없습니다: {source}", kind="missing_skill")
        elif skill is not None:
            source = resolve_skill(skill)

        agents_md = BASE_AGENTS_MD
        if source is not None:
            name = skill or source.name
            destination = workspace / ".agents" / "skills" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_tree_for_codex(source, destination)
            agents_md += SKILL_MANDATE.format(name=name)
        write_for_codex(workspace / "AGENTS.md", agents_md)

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
        if reasoning_effort:
            command.extend(
                ["--config", f'model_reasoning_effort="{reasoning_effort}"']
            )
        if service_tier:
            command.extend(["--config", f'service_tier="{service_tier}"'])
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
            raise CodexRunError("Codex CLI를 찾을 수 없습니다.", kind="missing_cli") from exc
        except subprocess.TimeoutExpired as exc:
            raise CodexRunError("Codex 실행 시간이 초과되었습니다.", kind="timeout") from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip()[-1000:]
            raise CodexRunError(
                f"Codex 실행 실패(exit {completed.returncode}): {detail or 'no stderr'}",
                kind="exit",
            )
        if not output_path.is_file():
            raise CodexRunError("Codex 결과 파일이 생성되지 않았습니다.", kind="no_output")

        text = output_path.read_text(encoding="utf-8").strip()
        return CodexResult(text=text, parsed=parse_codex_json(text))
