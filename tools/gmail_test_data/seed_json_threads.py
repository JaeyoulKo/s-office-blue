#!/usr/bin/env python3
"""Insert Main UI JSON fixtures into the current user's test Gmail mailbox.

Dry-run is the default.  This module deliberately has no dependency on the
application's Gmail adapter and never exposes a send or draft operation.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, parseaddr, parsedate_to_datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Sequence

# Keep the documented direct-script invocation working without installing the project.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from main_service.emails import EMAIL_DIR, load_inbox, load_sources, subject_title

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
INSERT_SCOPE = "https://www.googleapis.com/auth/gmail.insert"
SCOPES = (READONLY_SCOPE, INSERT_SCOPE)
DEFAULT_TOKEN_PATH = Path("~/.codex/mcp/gmail-local/private/seed-token.json").expanduser()
DEFAULT_CREDENTIALS_PATH = Path("~/.codex/mcp/gmail-local/private/credentials.json").expanduser()
MAX_WORKERS = 3
_MESSAGE_ID_SAFE = re.compile(r"[^A-Za-z0-9.!#$%&'*+/=?^_`{|}~@-]+")


class ValidationError(ValueError):
    """A fixture cannot safely be converted into a message."""


@dataclass
class SeedMessage:
    source_id: str
    thread_key: str
    ordinal: int
    sender: str
    recipients: list[str]
    subject: str
    body: str
    date: datetime
    message_id: str
    original_missing: tuple[str, ...] = ()


@dataclass
class SeedThread:
    source_ids: set[str]
    key: str
    messages: list[SeedMessage]


@dataclass
class Inventory:
    discovered_sources: int = 0
    malformed_sources: list[str] = field(default_factory=list)
    source_counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    before_threads: int = 0
    before_messages: int = 0
    after_threads: int = 0
    after_messages: int = 0
    duplicate_threads: int = 0
    duplicate_messages: int = 0
    missing_fields: dict[str, int] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class RunCounts:
    valid: int = 0
    already_exists: int = 0
    inserted: int = 0
    skipped: int = 0
    failed: int = 0

    def add(self, other: "RunCounts") -> None:
        for name in ("valid", "already_exists", "inserted", "skipped", "failed"):
            setattr(self, name, getattr(self, name) + getattr(other, name))


def _stable_hex(*parts: object, length: int = 24) -> str:
    value = "\0".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:length]


def normalize_message_id(value: str, *, source_id: str, thread_key: str, ordinal: int) -> str:
    raw = str(value or "").strip().strip("<>").strip()
    raw = _MESSAGE_ID_SAFE.sub("-", raw).strip(".-@")
    if raw:
        if "@" not in raw:
            raw = f"{raw}@fixture.office-blue.invalid"
        return f"<{raw}>"
    digest = _stable_hex(source_id, thread_key, ordinal)
    return f"<fixture-{digest}@fixture.office-blue.invalid>"


def _parse_date(value: object, *, identity: str, ordinal: int) -> datetime:
    text = str(value or "").strip()
    if text:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValidationError("invalid date field") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    # Fixtures without dates still need a stable RFC 2822 Date header.
    seconds = int(_stable_hex(identity, length=8), 16) % (20 * 365 * 24 * 3600)
    return datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds + ordinal)


def _addresses(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value] if value else []
    return [str(item).strip() for item in values if str(item).strip()]


def _safe_address(value: str, role: str, identity: str) -> str:
    display, address = parseaddr(value)
    if address and "@" in address and " " not in address:
        return value
    local = f"fixture-{role}-{_stable_hex(identity, value, length=12)}"
    return f"{display or role} <{local}@example.invalid>"


def _message_from_record(record: dict[str, Any], source_id: str, thread_key: str, ordinal: int) -> SeedMessage:
    attachments = record.get("attachments") or []
    if attachments:
        raise ValidationError("attachments are declared but attachment seeding is unsupported")
    sender = str(record.get("sender") or record.get("from") or "").strip()
    recipients = _addresses(record.get("recipients") or record.get("to"))
    subject = str(record.get("subject") or record.get("email_subject") or "").strip()
    body = str(record.get("body") or record.get("email_body") or "")
    date_value = record.get("received_at") or record.get("date")
    missing = tuple(
        name for name, present in (
            ("From", bool(sender)), ("To", bool(recipients)), ("Subject", bool(subject)),
            ("Date", bool(date_value)), ("Message-ID", bool(record.get("message_id"))),
        ) if not present
    )
    identity = f"{ordinal}:{subject_title(subject)}:{body}"
    sender = _safe_address(sender, "sender", identity)
    recipients = [_safe_address(value, "recipient", identity) for value in recipients]
    if not recipients:
        recipients = [_safe_address("", "recipient", identity)]
    if not subject:
        subject = "(제목 없음)"
    return SeedMessage(
        source_id=source_id, thread_key=thread_key, ordinal=ordinal,
        sender=sender, recipients=recipients, subject=subject, body=body,
        date=_parse_date(date_value, identity=identity, ordinal=ordinal),
        message_id=normalize_message_id(
            str(record.get("message_id") or ""), source_id=source_id,
            thread_key=thread_key, ordinal=ordinal,
        ),
        original_missing=missing,
    )


def _load_source(path: Path) -> list[SeedThread]:
    source_id = path.relative_to(EMAIL_DIR).as_posix()
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else [raw]
    threads: list[SeedThread] = []
    flat_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    normalized = load_inbox(path)
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValidationError(f"record {index + 1} is not an object")
        nested = record.get("messages")
        if nested is not None:
            if not isinstance(nested, list) or not nested or not all(isinstance(m, dict) for m in nested):
                raise ValidationError(f"thread record {index + 1} has invalid messages")
            key = str(record.get("thread_id") or record.get("case_id") or f"record-{index + 1}")
            messages = [_message_from_record(m, source_id, key, i) for i, m in enumerate(nested)]
            threads.append(SeedThread({source_id}, key, sorted(messages, key=lambda m: (m.date, m.ordinal))))
        else:
            flat_records.append((record, normalized[index]))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, (raw_record, email) in enumerate(flat_records):
        key = str(email.get("thread_id") or email.get("case_id") or f"record-{index + 1}")
        grouped.setdefault(key, []).append(email)
    for key, items in grouped.items():
        messages = [_message_from_record(item, source_id, key, i) for i, item in enumerate(items)]
        threads.append(SeedThread({source_id}, key, sorted(messages, key=lambda m: (m.date, m.ordinal))))
    return threads


def _message_signature(message: SeedMessage) -> str:
    return _stable_hex(message.sender, message.recipients, subject_title(message.subject), message.body,
                       message.date.isoformat(), length=64)


def _thread_signature(thread: SeedThread) -> str:
    return _stable_hex(*(_message_signature(m) for m in thread.messages), length=64)


def inventory(selected_sources: Sequence[str] | None = None) -> tuple[Inventory, list[SeedThread]]:
    report = Inventory()
    selected = set(selected_sources or [])
    valid_sources = {path.relative_to(EMAIL_DIR).as_posix(): path for path, _, _ in load_sources()}
    all_paths = sorted(EMAIL_DIR.rglob("*.json"))
    candidates = [p for p in all_paths if not selected or p.relative_to(EMAIL_DIR).as_posix() in selected]
    unknown = selected - {p.relative_to(EMAIL_DIR).as_posix() for p in all_paths}
    if unknown:
        raise ValidationError("unknown source: " + ", ".join(sorted(unknown)))
    report.discovered_sources = len(candidates)
    all_threads: list[SeedThread] = []
    for path in candidates:
        source_id = path.relative_to(EMAIL_DIR).as_posix()
        if source_id not in valid_sources:
            report.malformed_sources.append(source_id)
            continue
        try:
            threads = _load_source(path)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            report.validation_errors.append(f"{source_id}: {exc}")
            continue
        report.source_counts[source_id] = (len(threads), sum(len(t.messages) for t in threads))
        for thread in threads:
            for message in thread.messages:
                for field_name in message.original_missing:
                    report.missing_fields[field_name] = report.missing_fields.get(field_name, 0) + 1
        all_threads.extend(threads)
    report.before_threads = len(all_threads)
    report.before_messages = sum(len(t.messages) for t in all_threads)
    deduped: dict[str, SeedThread] = {}
    seen_messages: set[str] = set()
    for thread in all_threads:
        signature = _thread_signature(thread)
        if signature in deduped:
            report.duplicate_threads += 1
            report.duplicate_messages += len(thread.messages)
            deduped[signature].source_ids.update(thread.source_ids)
            continue
        unique_messages = []
        for message in thread.messages:
            message_signature = _message_signature(message)
            if message_signature in seen_messages:
                report.duplicate_messages += 1
                continue
            seen_messages.add(message_signature)
            unique_messages.append(message)
        if unique_messages:
            thread.messages = unique_messages
            deduped[signature] = thread
    result = list(deduped.values())
    report.after_threads = len(result)
    report.after_messages = sum(len(t.messages) for t in result)
    return report, result


def build_mime(message: SeedMessage, *, parent_ids: Sequence[str]) -> bytes:
    mail = EmailMessage(policy=SMTP)
    mail["From"] = message.sender
    mail["To"] = ", ".join(message.recipients)
    mail["Subject"] = message.subject
    mail["Date"] = format_datetime(message.date)
    mail["Message-ID"] = message.message_id
    if parent_ids:
        mail["In-Reply-To"] = parent_ids[-1]
        mail["References"] = " ".join(parent_ids)
    mail.set_content(message.body, charset="utf-8")
    return mail.as_bytes()


class GmailGateway:
    def __init__(self, service: Any):
        self.service = service

    def existing_thread_id(self, message_id: str) -> str | None:
        result = self.service.users().messages().list(
            userId="me", q=f"rfc822msgid:{message_id}", maxResults=1,
        ).execute(num_retries=0)
        messages = result.get("messages") or []
        return str(messages[0].get("threadId") or "") if messages else None

    def insert(self, raw: bytes, thread_id: str | None = None) -> str:
        body: dict[str, Any] = {
            "raw": base64.urlsafe_b64encode(raw).decode("ascii"),
            "labelIds": ["INBOX"],
        }
        if thread_id:
            body["threadId"] = thread_id
        result = self.service.users().messages().insert(
            userId="me", body=body, internalDateSource="dateHeader",
        ).execute(num_retries=0)
        return str(result.get("threadId") or "")


def _seed_thread(thread: SeedThread, gateway: GmailGateway | None, execute: bool) -> RunCounts:
    counts = RunCounts()
    parent_ids: list[str] = []
    provider_thread_id: str | None = None
    for message in thread.messages:
        try:
            raw = build_mime(message, parent_ids=parent_ids)
            counts.valid += 1
            if not execute:
                counts.skipped += 1
            else:
                assert gateway is not None
                try:
                    existing_thread_id = gateway.existing_thread_id(message.message_id)
                except Exception:  # duplicate-check failure must never lead to insert
                    counts.failed += 1
                    parent_ids.append(message.message_id)
                    continue
                if existing_thread_id is not None:
                    provider_thread_id = existing_thread_id or provider_thread_id
                    counts.already_exists += 1
                    counts.skipped += 1
                else:
                    provider_thread_id = gateway.insert(raw, provider_thread_id) or provider_thread_id
                    counts.inserted += 1
            parent_ids.append(message.message_id)
        except Exception:
            counts.failed += 1
    return counts


def run_threads(threads: Sequence[SeedThread], gateway: GmailGateway | None, *, execute: bool,
                max_workers: int) -> RunCounts:
    if not 1 <= max_workers <= MAX_WORKERS:
        raise ValidationError("--max-workers must be between 1 and 3")
    total = RunCounts()
    lock = Lock()
    def work(thread: SeedThread) -> None:
        result = _seed_thread(thread, gateway, execute)
        with lock:
            total.add(result)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, thread) for thread in threads]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception:
                with lock:
                    total.failed += 1
    return total


def authorize(token_path: Path, credentials_path: Path = DEFAULT_CREDENTIALS_PATH) -> GmailGateway:
    """Load/refresh the isolated seed credential; starts OAuth only when explicitly called."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), list(SCOPES))
        if set(credentials.scopes or ()) != set(SCOPES):
            raise ValidationError("seed token has scopes other than the two allowed scopes")
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), list(SCOPES))
        credentials = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    os.chmod(token_path, 0o600)
    return GmailGateway(build("gmail", "v1", credentials=credentials, cache_discovery=False))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed Main UI JSON threads with Gmail messages.insert")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate only (default)")
    mode.add_argument("--execute", action="store_true", help="perform read-only checks and inserts")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--source", action="append", help="source path relative to synthetic email dir")
    selection.add_argument("--all", action="store_true", help="process all sources after deduplication")
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--token-path", type=Path, default=DEFAULT_TOKEN_PATH)
    return parser


def main(argv: Sequence[str] | None = None, *, gateway_factory: Callable[[Path], GmailGateway] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report, threads = inventory(args.source)
        if report.malformed_sources or report.validation_errors:
            raise ValidationError("fixture validation failed")
        gateway = None
        if args.execute:
            gateway = (gateway_factory or authorize)(args.token_path.expanduser())
        counts = run_threads(threads, gateway, execute=args.execute, max_workers=args.max_workers)
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # never echo provider responses, credentials, addresses, or bodies
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"sources={report.discovered_sources}")
    print(f"before_threads={report.before_threads} before_messages={report.before_messages}")
    print(f"after_threads={report.after_threads} after_messages={report.after_messages}")
    print(f"valid={counts.valid}")
    print(f"already_exists={counts.already_exists}")
    print(f"inserted={counts.inserted}")
    print(f"skipped={counts.skipped}")
    print(f"failed={counts.failed}")
    return 1 if counts.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
