from __future__ import annotations

import base64
import io
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

from tools.gmail_test_data.seed_json_threads import (
    DEFAULT_TOKEN_PATH,
    INSERT_SCOPE,
    MAX_WORKERS,
    READONLY_SCOPE,
    SCOPES,
    GmailGateway,
    SeedMessage,
    SeedThread,
    ValidationError,
    build_mime,
    inventory,
    main,
    normalize_message_id,
    run_threads,
    _message_from_record,
)


class FakeGateway:
    def __init__(self, existing=(), fail_search=(), fail_insert=()):
        self.existing = set(existing)
        self.fail_search = set(fail_search)
        self.fail_insert = set(fail_insert)
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def existing_thread_id(self, message_id):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(("search", message_id))
        time.sleep(0.005)
        with self.lock:
            self.active -= 1
        if message_id in self.fail_search:
            raise RuntimeError("private-token-value")
        return "provider-thread" if message_id in self.existing else None

    def insert(self, raw, thread_id=None):
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        message_id = parsed["Message-ID"]
        self.calls.append(("insert", message_id, thread_id))
        if message_id in self.fail_insert:
            raise RuntimeError("private-address@example.com")
        return thread_id or "provider-thread"


def message(thread, ordinal, *, date, message_id=None, body="한글 본문"):
    return SeedMessage(
        source_id="source.json", thread_key=thread, ordinal=ordinal,
        sender="보낸이 <sender@example.invalid>", recipients=["recipient@example.invalid"],
        subject="Re: 한글 제목" if ordinal else "한글 제목", body=body, date=date,
        message_id=message_id or f"<m-{thread}-{ordinal}@fixture.invalid>",
    )


class InventoryTests(unittest.TestCase):
    def test_inventory_covers_ui_sources_and_is_deduplicated(self):
        report, threads = inventory()
        self.assertEqual(report.discovered_sources, len(report.source_counts))
        self.assertFalse(report.malformed_sources)
        self.assertFalse(report.validation_errors)
        self.assertGreater(report.before_threads, 0)
        self.assertGreater(report.before_messages, report.before_threads)
        self.assertEqual(report.duplicate_threads, 1)
        self.assertEqual(report.duplicate_messages, 1)
        self.assertEqual((report.before_threads, report.before_messages), (43, 57))
        self.assertEqual((report.after_threads, report.after_messages), (42, 56))
        self.assertEqual(report.after_messages, sum(len(t.messages) for t in threads))

    def test_source_filter(self):
        report, _ = inventory(["discussion-email.json"])
        self.assertEqual(report.discovered_sources, 1)
        self.assertEqual(report.source_counts["discussion-email.json"], (1, 8))

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValidationError):
            inventory(["not-a-source.json"])

    def test_declared_attachment_is_a_validation_error(self):
        with self.assertRaisesRegex(ValidationError, "attachment"):
            _message_from_record(
                {"attachments": [{"name": "redacted"}]}, "source.json", "thread", 0
            )


class MimeTests(unittest.TestCase):
    def test_message_id_is_deterministic_and_normalized(self):
        first = normalize_message_id("unsafe id", source_id="s", thread_key="t", ordinal=2)
        second = normalize_message_id("unsafe id", source_id="s", thread_key="t", ordinal=2)
        generated = normalize_message_id("", source_id="s", thread_key="t", ordinal=2)
        self.assertEqual(first, second)
        self.assertEqual(generated, normalize_message_id("", source_id="s", thread_key="t", ordinal=2))
        self.assertRegex(first, r"^<[^ <>]+@[^ <>]+>$")

    def test_utf8_mime_and_reply_headers(self):
        from datetime import datetime, timezone
        item = message("t", 1, date=datetime(2025, 1, 2, tzinfo=timezone.utc))
        raw = build_mime(item, parent_ids=["<root@fixture.invalid>"])
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(parsed["Subject"], "Re: 한글 제목")
        self.assertIn("한글 본문", parsed.get_content())
        self.assertEqual(parsed["In-Reply-To"], "<root@fixture.invalid>")
        self.assertEqual(parsed["References"], "<root@fixture.invalid>")

    def test_inventory_sorts_dates_and_chains_all_references(self):
        _, threads = inventory(["discussion-email.json"])
        dates = [item.date for item in threads[0].messages]
        self.assertEqual(dates, sorted(dates))
        parent_ids = []
        for item in threads[0].messages:
            parsed = BytesParser(policy=policy.default).parsebytes(build_mime(item, parent_ids=parent_ids))
            if parent_ids:
                self.assertEqual(str(parsed["In-Reply-To"]), parent_ids[-1])
                self.assertEqual(str(parsed["References"]), " ".join(parent_ids))
            parent_ids.append(item.message_id)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        from datetime import datetime, timedelta, timezone
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.threads = [
            SeedThread({"source.json"}, f"t{i}", [
                message(f"t{i}", n, date=start + timedelta(minutes=n)) for n in range(3)
            ]) for i in range(4)
        ]

    def test_dry_run_never_touches_gateway(self):
        gateway = FakeGateway()
        counts = run_threads(self.threads, gateway, execute=False, max_workers=3)
        self.assertEqual(gateway.calls, [])
        self.assertEqual(counts.skipped, 12)

    def test_execute_skips_existing_and_only_execute_inserts(self):
        existing = self.threads[0].messages[0].message_id
        gateway = FakeGateway(existing={existing})
        counts = run_threads(self.threads[:1], gateway, execute=True, max_workers=1)
        self.assertEqual(counts.already_exists, 1)
        self.assertEqual(counts.inserted, 2)
        self.assertNotIn(("insert", existing, None), gateway.calls)

    def test_same_thread_is_sequential_and_uses_provider_thread(self):
        gateway = FakeGateway()
        run_threads(self.threads[:1], gateway, execute=True, max_workers=3)
        message_ids = [m.message_id for m in self.threads[0].messages]
        searches = [call[1] for call in gateway.calls if call[0] == "search"]
        self.assertEqual(searches, message_ids)
        inserts = [call for call in gateway.calls if call[0] == "insert"]
        self.assertIsNone(inserts[0][2])
        self.assertTrue(all(call[2] == "provider-thread" for call in inserts[1:]))

    def test_different_threads_use_at_most_three_workers(self):
        gateway = FakeGateway()
        run_threads(self.threads, gateway, execute=True, max_workers=3)
        self.assertGreaterEqual(gateway.max_active, 2)
        self.assertLessEqual(gateway.max_active, MAX_WORKERS)
        with self.assertRaises(ValidationError):
            run_threads(self.threads, gateway, execute=True, max_workers=4)

    def test_failure_does_not_stop_other_threads_and_search_failure_never_inserts(self):
        failed = self.threads[0].messages[0].message_id
        gateway = FakeGateway(fail_search={failed})
        counts = run_threads(self.threads, gateway, execute=True, max_workers=3)
        self.assertEqual(counts.failed, 1)
        self.assertEqual(counts.inserted, 11)
        self.assertFalse(any(call[0] == "insert" and call[1] == failed for call in gateway.calls))

    def test_cli_defaults_to_dry_run_and_execute_is_explicit(self):
        factory_calls = []
        def factory(path):
            factory_calls.append(path)
            return FakeGateway()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--source", "discussion-email.json"], gateway_factory=factory), 0)
        self.assertEqual(factory_calls, [])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--execute", "--source", "discussion-email.json"], gateway_factory=factory), 0)
        self.assertEqual(len(factory_calls), 1)

    def test_logs_do_not_contain_fixture_content_token_or_addresses(self):
        failed = self.threads[0].messages[0].message_id
        gateway = FakeGateway(fail_search={failed})
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            run_threads(self.threads[:1], gateway, execute=True, max_workers=1)
        text = output.getvalue()
        self.assertNotIn("한글 본문", text)
        self.assertNotIn("private-token-value", text)
        self.assertNotIn("sender@example.invalid", text)

    def test_oauth_scopes_and_token_are_isolated(self):
        self.assertEqual(SCOPES, (READONLY_SCOPE, INSERT_SCOPE))
        self.assertEqual(DEFAULT_TOKEN_PATH.name, "seed-token.json")
        self.assertNotEqual(DEFAULT_TOKEN_PATH.name, "token.json")


class GatewayShapeTests(unittest.TestCase):
    def test_insert_uses_insert_date_header_and_inbox(self):
        class Request:
            def execute(self, **kwargs):
                self.kwargs = kwargs
                return {"threadId": "secret-provider-id"}
        class Messages:
            def __init__(self): self.request = Request(); self.kwargs = None
            def insert(self, **kwargs): self.kwargs = kwargs; return self.request
        class Users:
            def __init__(self, messages): self._messages = messages
            def messages(self): return self._messages
        class Service:
            def __init__(self, messages): self._users = Users(messages)
            def users(self): return self._users
        messages = Messages()
        gateway = GmailGateway(Service(messages))
        self.assertEqual(gateway.insert(b"mime"), "secret-provider-id")
        self.assertEqual(messages.kwargs["internalDateSource"], "dateHeader")
        self.assertEqual(messages.kwargs["body"]["labelIds"], ["INBOX"])
        self.assertNotIn("labelIds", {k: v for k, v in messages.kwargs.items() if k != "body"})


if __name__ == "__main__":
    unittest.main()
