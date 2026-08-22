"""Office Blue용 읽기 전용 Gmail stdio MCP 서버."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from googleapiclient.discovery import build

from main_service.gmail_api import _body, _credentials, _headers


TOOLS = [
    {
        "name": "search_threads",
        "description": "Search Gmail threads using Gmail query syntax.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "pageSize": {"type": "integer"}},
        },
    },
    {
        "name": "get_thread",
        "description": "Read one Gmail thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string"},
                "messageFormat": {"type": "string"},
            },
            "required": ["threadId"],
        },
    },
    {"name": "list_labels", "description": "List Gmail labels.", "inputSchema": {"type": "object"}},
    {"name": "list_drafts", "description": "List Gmail drafts.", "inputSchema": {"type": "object"}},
]


def _service():
    return build("gmail", "v1", credentials=_credentials(), cache_discovery=False)


def _message(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload") or {}
    headers = _headers(payload)
    return {
        "id": str(raw.get("id") or ""),
        "threadId": str(raw.get("threadId") or ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "body": _body(payload),
        "snippet": str(raw.get("snippet") or ""),
    }


def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    service = _service()
    if name == "search_threads":
        page_size = max(1, min(int(arguments.get("pageSize") or 20), 50))
        result = service.users().threads().list(
            userId="me", q=str(arguments.get("query") or ""), maxResults=page_size
        ).execute()
        return {"threads": [{"id": item.get("id", "")} for item in result.get("threads") or []]}
    if name == "get_thread":
        thread = service.users().threads().get(
            userId="me", id=str(arguments["threadId"]), format="full"
        ).execute()
        return {
            "id": str(thread.get("id") or ""),
            "messages": [_message(message) for message in thread.get("messages") or []],
        }
    if name == "list_labels":
        result = service.users().labels().list(userId="me").execute()
        return {"labels": result.get("labels") or []}
    if name == "list_drafts":
        result = service.users().drafts().list(
            userId="me", maxResults=max(1, min(int(arguments.get("pageSize") or 20), 50))
        ).execute()
        return {"drafts": result.get("drafts") or []}
    raise ValueError(f"지원하지 않는 도구입니다: {name}")


def _response(request_id: Any, *, result: Any = None, error: str | None = None) -> None:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        message["result"] = result
    else:
        message["error"] = {"code": -32000, "message": error}
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method")
            if request_id is None:
                continue
            if method == "initialize":
                _response(
                    request_id,
                    result={
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "office-blue-gmail", "version": "1.0.0"},
                    },
                )
            elif method == "tools/list":
                _response(request_id, result={"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params") or {}
                value = _call(str(params.get("name") or ""), params.get("arguments") or {})
                _response(
                    request_id,
                    result={
                        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                        "structuredContent": value,
                        "isError": False,
                    },
                )
            else:
                _response(request_id, error=f"지원하지 않는 메서드입니다: {method}")
        except Exception as exc:
            _response(locals().get("request_id"), error=str(exc))


if __name__ == "__main__":
    main()
