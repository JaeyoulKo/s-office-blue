"""Google Gmail API를 직접 호출하는 읽기 전용 inbox adapter."""

from __future__ import annotations

import base64
import json
import os
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DEFAULT_QUERY = "is:unread"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CONFIG_DIR = Path.home() / ".config" / "office-blue"
CLIENT_FILE = Path(os.environ.get("GMAIL_OAUTH_CLIENT_FILE", CONFIG_DIR / "google-oauth-client.json"))
TOKEN_FILE = Path(os.environ.get("GMAIL_OAUTH_TOKEN_FILE", CONFIG_DIR / "gmail-readonly-token.json"))


class GmailError(RuntimeError):
    """Gmail API 인증 또는 조회가 실패했다."""


def _credentials() -> Credentials:
    credentials: Credentials | None = None
    should_save = False
    if TOKEN_FILE.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except (ValueError, json.JSONDecodeError) as exc:
            raise GmailError(f"Gmail OAuth 토큰을 읽을 수 없습니다: {TOKEN_FILE}") from exc

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            should_save = True
        except Exception as exc:
            raise GmailError("Gmail OAuth 토큰 갱신에 실패했습니다. 다시 인증하세요.") from exc

    if not credentials or not credentials.valid:
        if not CLIENT_FILE.is_file():
            raise GmailError(f"Google OAuth 클라이언트 파일이 없습니다: {CLIENT_FILE}")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
            credentials = flow.run_local_server(
                host="127.0.0.1",
                port=0,
                open_browser=True,
                authorization_prompt_message="Gmail 읽기 권한 승인을 위해 다음 주소를 여세요: {url}",
                success_message="Gmail 인증이 완료되었습니다. 이 창을 닫아도 됩니다.",
            )
            should_save = True
        except Exception as exc:
            raise GmailError(f"Gmail OAuth 인증에 실패했습니다: {exc}") from exc

    if should_save:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def _decode(data: str | None) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")


def _body(payload: dict[str, Any]) -> str:
    mime_type = str(payload.get("mimeType") or "")
    if mime_type == "text/plain":
        return _decode((payload.get("body") or {}).get("data"))
    plain = ""
    html = ""
    for part in payload.get("parts") or []:
        value = _body(part)
        if not value:
            continue
        if str(part.get("mimeType") or "") == "text/plain":
            plain = value
        elif not html:
            html = value
    return plain or html or _decode((payload.get("body") or {}).get("data"))


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("name") or "").lower(): str(item.get("value") or "")
        for item in payload.get("headers") or []
    }


def _date(raw: str) -> str:
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        return raw


def _snapshot(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload") or {}
    headers = _headers(payload)
    recipients = [value.strip() for value in headers.get("to", "").replace(";", ",").split(",") if value.strip()]
    attachments = [
        {"filename": part.get("filename", ""), "mime_type": part.get("mimeType", "")}
        for part in payload.get("parts") or []
        if part.get("filename")
    ]
    return {
        "message_id": str(message.get("id") or ""),
        "thread_id": str(message.get("threadId") or ""),
        "sender": headers.get("from", ""),
        "recipients": recipients,
        "subject": headers.get("subject", ""),
        "body": _body(payload) or str(message.get("snippet") or ""),
        "received_at": _date(headers.get("date", "")),
        "attachments": attachments,
    }


def fetch_messages(
    query: str = DEFAULT_QUERY, *, max_results: int = 50, timeout_seconds: int = 60
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    del timeout_seconds  # googleapiclient 자체 HTTP timeout 정책을 사용한다.
    query = query.strip()
    if not query:
        raise ValueError("Gmail 검색어가 비어 있습니다.")
    if not 1 <= max_results <= 50:
        raise ValueError("조회 개수는 1개에서 50개 사이여야 합니다.")

    try:
        service = build("gmail", "v1", credentials=_credentials(), cache_discovery=False)
        listed = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    except (HttpError, OSError) as exc:
        raise GmailError(f"Gmail API 조회에 실패했습니다: {exc}") from exc

    messages: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in listed.get("messages") or []:
        message_id = str(item.get("id") or "")
        if not message_id:
            continue
        try:
            raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            messages.append(_snapshot(raw))
        except (HttpError, OSError) as exc:
            errors.append({"where": f"messages.get({message_id})", "reason": str(exc)})

    messages.sort(key=lambda message: message.get("received_at") or "", reverse=True)
    return messages, errors
