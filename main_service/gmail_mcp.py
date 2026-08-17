"""로컬 Gmail MCP 서버를 직접 호출한다. LLM을 거치지 않는다.

메일을 가져오는 일에는 판단이 없다. "안 읽은 메일을 주세요"는 검색 한 번과 스레드 조회
몇 번이면 끝나는 결정론적 작업이라, 여기에 모델을 넣으면 얻는 것 없이 세 가지를 잃는다.

- 속도: `codex exec` 한 번이 수십 초에서 몇 분. 직접 호출은 왕복 몇 백 밀리초다.
- 신뢰성: 모델이 도구를 못 찾으면 스키마에 맞는 빈 목록을 조용히 돌려준다. 실제로 그렇게
  0건이 나왔고 원인을 찾는 데 시간이 걸렸다.
- 비용: 메일 목록을 옮겨 적는 데 토큰을 쓴다.

서버는 `~/.codex/config.toml`의 `mcp_servers.gmail`에 등록된 stdio 프로세스이고 줄 단위
JSON-RPC 2.0을 쓴다. 인증은 서버가 자기 토큰 파일로 처리하므로 여기서 비밀값을 다루지 않는다.

읽기 도구만 부른다. 이 모듈에는 발송·라벨 변경·삭제 경로가 없다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".codex" / "config.toml"
SERVER_NAME = "gmail"
DEFAULT_QUERY = "is:unread"
READ_ONLY_TOOLS = frozenset({"search_threads", "get_thread", "list_labels", "list_drafts"})


class GmailError(RuntimeError):
    """Gmail MCP 호출이 실패했다."""


def _server_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise GmailError(f"Codex 설정을 찾을 수 없습니다: {CONFIG_PATH}")
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    server = (config.get("mcp_servers") or {}).get(SERVER_NAME)
    if not server:
        raise GmailError(
            f"`{SERVER_NAME}` MCP 서버가 등록되어 있지 않습니다. `codex mcp list`로 확인하세요."
        )
    return server


class GmailClient:
    """stdio MCP 서버 하나를 붙잡고 읽기 도구를 부른다."""

    def __init__(self, timeout_seconds: int = 60) -> None:
        server = _server_config()
        command = server.get("command")
        if not command:
            raise GmailError("Gmail MCP 서버 설정에 command가 없습니다.")
        resolved = shutil.which(command) or command
        args = [str(a) for a in (server.get("args") or [])]
        env = {**os.environ, **{str(k): str(v) for k, v in (server.get("env") or {}).items()}}
        self.timeout = timeout_seconds
        self._next_id = 0
        try:
            self.process = subprocess.Popen(
                [resolved, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=server.get("cwd") or None,
                env=env,
            )
        except FileNotFoundError as exc:
            raise GmailError(f"MCP 서버를 실행할 수 없습니다: {resolved}") from exc
        try:
            self._request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "office-blue", "version": "0.1.0"},
                },
            )
            self._notify("notifications/initialized")
        except Exception:
            self.close()
            raise

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        while True:
            message = self._read()
            if message.get("id") != request_id:
                continue  # 서버가 보낸 알림은 건너뛴다
            if "error" in message:
                raise GmailError(str(message["error"].get("message") or message["error"]))
            return message.get("result")

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _write(self, message: dict[str, Any]) -> None:
        if self.process.stdin is None or self.process.poll() is not None:
            raise GmailError("Gmail MCP 서버가 종료되었습니다.")
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        if self.process.stdout is None:
            raise GmailError("Gmail MCP 서버 출력을 읽을 수 없습니다.")
        line = self.process.stdout.readline()
        if not line:
            stderr = (self.process.stderr.read() if self.process.stderr else "") or ""
            raise GmailError(f"Gmail MCP 서버가 응답하지 않았습니다. {stderr.strip()[-500:]}")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise GmailError(f"MCP 응답을 읽을 수 없습니다: {line.strip()[:200]}") from exc

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        """읽기 도구만 부른다. 쓰기 도구 이름은 여기서 막는다."""
        if tool not in READ_ONLY_TOOLS:
            raise GmailError(f"읽기 전용 도구가 아닙니다: {tool}")
        result = self._request("tools/call", {"name": tool, "arguments": arguments})
        content = (result or {}).get("content") or []
        text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if (result or {}).get("isError"):
            raise GmailError(text or f"{tool} 호출이 실패했습니다.")
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise GmailError(f"{tool} 응답을 읽을 수 없습니다: {text[:200]}") from exc

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is None:
            return
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            process.kill()

    def __enter__(self) -> GmailClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _iso_date(raw: str) -> str:
    """RFC 2822 헤더를 ISO 8601로. 못 읽으면 원문을 그대로 둔다."""
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        return raw


def _addresses(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;]", raw or "") if part.strip()]


def _to_snapshot(message: dict[str, Any]) -> dict[str, Any]:
    """MCP 메시지를 gmail_snapshot.schema.json 형태로 옮긴다."""
    return {
        "message_id": str(message.get("id") or ""),
        "thread_id": str(message.get("threadId") or ""),
        "sender": str(message.get("from") or ""),
        "recipients": _addresses(str(message.get("to") or "")),
        "subject": str(message.get("subject") or ""),
        "body": str(message.get("body") or message.get("snippet") or ""),
        "received_at": _iso_date(str(message.get("date") or "")),
        "attachments": [],
    }


def fetch_messages(
    query: str = DEFAULT_QUERY, *, max_results: int = 50, timeout_seconds: int = 60
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """검색어에 맞는 메일을 최신순으로 가져온다.

    `(messages, errors)`를 돌려준다. 스레드 하나가 실패해도 나머지는 살린다 — 메일 한 통
    때문에 받은편지함 전체가 비어 보이면 안 된다.
    """
    query = query.strip()
    if not query:
        raise ValueError("Gmail 검색어가 비어 있습니다.")
    if not 1 <= max_results <= 50:
        raise ValueError("조회 개수는 1개에서 50개 사이여야 합니다.")

    messages: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with GmailClient(timeout_seconds=timeout_seconds) as client:
        found = client.call("search_threads", {"query": query, "pageSize": max_results})
        threads = found.get("threads") or []
        for thread in threads:
            thread_id = str(thread.get("id") or "")
            if not thread_id:
                continue
            try:
                detail = client.call("get_thread", {"threadId": thread_id, "view": "full"})
            except GmailError as exc:
                errors.append({"where": f"get_thread({thread_id})", "reason": str(exc)})
                continue
            thread_messages = detail.get("messages") or []
            if not thread_messages:
                continue
            # 스레드의 마지막 메시지가 받은편지함에 보이는 그 메일이고, 앞선 것들이 대화다.
            latest = _to_snapshot(thread_messages[-1])
            latest["thread"] = [_to_snapshot(m) for m in thread_messages[:-1]]
            messages.append(latest)
            if len(messages) >= max_results:
                break

    messages.sort(key=lambda m: m.get("received_at") or "", reverse=True)
    return messages, errors
