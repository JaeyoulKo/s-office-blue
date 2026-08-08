"""codex exec 를 띄우고 --json 이벤트를 흘려보낸다.

이 파일이 하는 일은 하나뿐이다: 터미널에서 손으로 치는 것과 **완전히 같은 명령**을 만들어
실행하고, 진행 상황을 콜백으로 넘긴다. 명령 전문을 그대로 돌려주기 때문에 UI가 화면에
띄울 수 있고, 멘티는 "UI가 마법을 부리는 게 아니라 이 한 줄을 실행하는구나"를 볼 수 있다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_EFFORT = "medium"

_FALLBACK_CODEX = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
)

# codex.exe를 절대경로로 직접 띄우면 데스크톱 런처가 넣어주던 PATH 항목이 없어서
# 번들 도구(rg 등)와 샌드박스 설정 실행 파일을 못 찾고 shell 도구가 전부 실패한다.
_CODEX_RUNTIME = Path.home() / ".codex" / "packages" / "standalone" / "current"
_REQUIRED_DIRS = (
    _CODEX_RUNTIME / "codex-resources",
    _CODEX_RUNTIME / "codex-path",
    Path(r"C:\Program Files\nodejs"),
)


def codex_bin() -> str:
    found = shutil.which("codex")
    if found:
        return found
    if _FALLBACK_CODEX.exists():
        return str(_FALLBACK_CODEX)
    raise FileNotFoundError("codex 실행 파일을 찾을 수 없습니다. docs/setup.md 를 보세요.")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    current = env.get("PATH", "")
    known = {p.lower().rstrip("\\") for p in current.split(os.pathsep) if p}
    extra = [str(d) for d in _REQUIRED_DIRS if d.is_dir() and str(d).lower() not in known]
    if extra:
        env["PATH"] = os.pathsep.join(extra) + os.pathsep + current
    return env


def build_command(
    workspace: Path,
    schema_path: Path,
    out_path: Path,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
) -> list[str]:
    """모든 arm이 이 함수로 명령을 만든다. arm 사이에 다른 것은 workspace 내용물뿐이다."""
    return [
        codex_bin(), "exec",
        # --ephemeral        이 실행의 흔적을 세션 기록에 남기지 않는다
        # --ignore-user-config  ~/.codex/config.toml 의 모델·effort·전역 스킬 차단.
        #                       이게 없으면 "스킬 없는 arm"에도 전역 스킬이 새어 든다.
        # --sandbox read-only   분석 단계는 아무것도 쓰지 않는다
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--model", model,
        "--config", f"model_reasoning_effort={json.dumps(effort)}",
        "--output-schema", str(schema_path),
        "--output-last-message", str(out_path),
        "--cd", str(workspace),
        "--json",
        "--color", "never",
        "-",  # 프롬프트는 stdin으로 (내용은 workspace/prompt.md 와 동일)
    ]


def _iter_events(stream: Iterable[str]) -> Iterable[dict[str, Any]]:
    for line in stream:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            yield {"type": "raw", "text": line}


def run(
    command: list[str],
    prompt: str,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    timeout: int = 900,
) -> tuple[int, list[dict[str, Any]]]:
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_env(),
        bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    events: list[dict[str, Any]] = []
    for event in _iter_events(proc.stdout):
        events.append(event)
        if on_event:
            on_event(event)
    return proc.wait(timeout=timeout), events


def event_text(event: dict[str, Any]) -> str:
    """이벤트에서 사람이 읽을 한 줄을 뽑는다. 이벤트 스키마 변동에 관대하게."""
    if event.get("type") == "raw":
        return str(event.get("text", ""))
    for key in ("text", "message", "command", "summary"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    msg = event.get("msg")
    if isinstance(msg, dict):
        for key in ("text", "message", "command"):
            value = msg.get(key)
            if isinstance(value, str) and value.strip():
                return f"{msg.get('type', '')} {value}".strip()
        return str(msg.get("type", ""))
    return str(event.get("type", ""))


def usage_of(events: list[dict[str, Any]]) -> dict[str, int]:
    """이벤트 스트림에서 토큰 사용량을 긁어모은다. 못 찾으면 빈 dict."""
    for event in reversed(events):
        for holder in (event, event.get("msg") if isinstance(event.get("msg"), dict) else {}):
            usage = holder.get("usage") if isinstance(holder, dict) else None
            if isinstance(usage, dict):
                return {k: v for k, v in usage.items() if isinstance(v, int)}
    return {}
