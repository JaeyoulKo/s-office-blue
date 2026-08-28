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
    DEFAULT_MAX_WORKERS,
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
    parse_date_override,
    run_threads,
    safe_failure_diagnostic,
    _message_from_record,
    _parser,
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

    def authenticated_email(self):
        self.calls.append(("profile",))
        return "profile-user@example.invalid"

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

    def insert(self, raw, thread_id=None, *, unread=False):
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        message_id = parsed["Message-ID"]
        self.calls.append(("insert", message_id, thread_id, unread))
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
        self.assertEqual(report.source_counts[
            "discussion-email-ar-rules/discussion-email-ar-rules.json"
        ], (10, 50))
        self.assertEqual(report.duplicate_threads, 0)
        self.assertEqual(report.duplicate_messages, 0)
        self.assertEqual((report.before_threads, report.before_messages), (33, 87))
        self.assertEqual((report.after_threads, report.after_messages), (33, 87))
        self.assertEqual(report.after_messages, sum(len(t.messages) for t in threads))
        overlapping_sources = {
            source_id
            for thread in threads if thread.key == "ariba-PR30922"
            for source_id in thread.source_ids
        }
        self.assertEqual(overlapping_sources, {
            "purchase-email-review.json",
            "purchase-email-review/purchase-review-email-sample.json",
        })

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

    def test_date_override_absent_keeps_original_date(self):
        from datetime import datetime, timezone
        original = datetime(2025, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
        item = message("t", 0, date=original)
        parsed = BytesParser(policy=policy.default).parsebytes(build_mime(item, parent_ids=[]))
        self.assertEqual(parsed["Date"].datetime, original)
        self.assertEqual(item.date, original)

    def test_date_override_changes_only_day_and_timezone(self):
        from datetime import datetime, timedelta, timezone
        original = datetime(2025, 3, 4, 5, 6, 7, tzinfo=timezone(timedelta(hours=-4)))
        item = message("t", 0, date=original)
        before = BytesParser(policy=policy.default).parsebytes(build_mime(item, parent_ids=[]))
        after = BytesParser(policy=policy.default).parsebytes(
            build_mime(item, parent_ids=[], date_override=parse_date_override("2026-08-27"))
        )
        changed = after["Date"].datetime
        self.assertEqual((changed.year, changed.month, changed.day), (2026, 8, 27))
        self.assertEqual((changed.hour, changed.minute, changed.second), (5, 6, 7))
        self.assertEqual(changed.utcoffset(), timedelta(hours=9))
        self.assertEqual(after["Message-ID"], before["Message-ID"])
        self.assertEqual(after["Subject"], before["Subject"])
        self.assertEqual(after.get_content(), before.get_content())
        self.assertEqual(after["From"], before["From"])
        self.assertEqual(after["To"], before["To"])
        self.assertEqual(item.date, original)

    def test_explicit_date_header_precedes_native_and_legacy_dates(self):
        item = _message_from_record(
            {
                "Date": "Wed, 05 Aug 2026 12:34:56 +0900",
                "date": "2026-08-06T01:02:03+09:00",
                "received_at": "2026-08-07T01:02:03+09:00",
            },
            "source.json", "thread", 0,
        )
        self.assertEqual(item.date.isoformat(), "2026-08-05T12:34:56+09:00")

    def test_native_naive_date_uses_seoul_timezone(self):
        item = _message_from_record(
            {"date": "2026-08-05T12:34:56"}, "source.json", "thread", 0,
        )
        self.assertEqual(item.date.isoformat(), "2026-08-05T12:34:56+09:00")

    def test_invalid_native_date_is_rejected_without_fallback(self):
        with self.assertRaisesRegex(ValidationError, "invalid date"):
            _message_from_record({"date": "2026-02-30"}, "source.json", "thread", 0)

    def test_ar_fixture_json_dates_round_trip_through_every_mime(self):
        import json
        from datetime import datetime, timedelta
        from main_service.emails import EMAIL_DIR

        source = "discussion-email-ar-rules/discussion-email-ar-rules.json"
        raw = json.loads((EMAIL_DIR / source).read_text())
        expected = {
            normalize_message_id(
                record["message_id"], source_id=source,
                thread_key=record["thread_id"], ordinal=index % 5,
            ): datetime.fromisoformat(record["date"])
            for index, record in enumerate(raw)
        }
        _, threads = inventory([source])
        seen = 0
        last_august_27 = 0
        for thread in threads:
            dates = []
            for item in thread.messages:
                parsed = BytesParser(policy=policy.default).parsebytes(
                    build_mime(
                        item, parent_ids=[], self_recipient="profile-user@example.invalid",
                    )
                )
                mime_date = parsed["Date"].datetime
                self.assertEqual(mime_date, expected[item.message_id])
                self.assertEqual(mime_date.utcoffset(), timedelta(hours=9))
                self.assertIn("profile-user@example.invalid", str(parsed["To"]))
                dates.append(mime_date)
                seen += 1
            self.assertEqual(dates, sorted(dates))
            if dates[-1].date().isoformat() == "2026-08-27":
                last_august_27 += 1
        self.assertEqual(seen, 50)
        self.assertEqual(last_august_27, 10)


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

    def test_cli_defaults_to_one_worker(self):
        self.assertEqual(DEFAULT_MAX_WORKERS, 1)
        self.assertEqual(_parser().parse_args([]).max_workers, 1)

    def test_invalid_date_override_stops_before_gateway_creation(self):
        factory_calls = []
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = main(
                ["--execute", "--source", "discussion-email.json", "--date-override", "2026-02-30"],
                gateway_factory=lambda path: factory_calls.append(path),
            )
        self.assertEqual(result, 2)
        self.assertEqual(factory_calls, [])

    def test_date_override_applies_to_every_generated_mime(self):
        class DateGateway(FakeGateway):
            def __init__(self):
                super().__init__()
                self.dates = []
            def insert(self, raw, thread_id=None, *, unread=False):
                parsed = BytesParser(policy=policy.default).parsebytes(raw)
                self.dates.append(parsed["Date"].datetime)
                return super().insert(raw, thread_id, unread=unread)
        gateway = DateGateway()
        counts = run_threads(
            self.threads, gateway, execute=True, max_workers=1, unread=True,
            date_override=parse_date_override("2026-08-27"),
        )
        self.assertEqual(counts.inserted, 12)
        self.assertEqual(len(gateway.dates), 12)
        self.assertTrue(all(value.date().isoformat() == "2026-08-27" for value in gateway.dates))
        self.assertTrue(all(value.utcoffset().total_seconds() == 9 * 3600 for value in gateway.dates))

    def test_recipient_self_replaces_only_placeholder_and_deduplicates(self):
        from datetime import datetime, timezone
        item = message("t", 0, date=datetime(2026, 8, 1, tzinfo=timezone.utc))
        item.recipients = [
            "김재무 <jaemu.kim@example.invalid>",
            "기존 수신자 <other@example.invalid>",
            "중복 수신자 <profile-user@example.invalid>",
        ]
        parsed = BytesParser(policy=policy.default).parsebytes(
            build_mime(item, parent_ids=[], self_recipient="profile-user@example.invalid")
        )
        to_header = str(parsed["To"])
        self.assertNotIn("jaemu.kim@example.invalid", to_header)
        self.assertEqual(to_header.count("profile-user@example.invalid"), 1)
        self.assertIn("other@example.invalid", to_header)

    def test_recipient_self_absent_keeps_fixture_recipient(self):
        from datetime import datetime, timezone
        item = message("t", 0, date=datetime(2026, 8, 1, tzinfo=timezone.utc))
        item.recipients = ["김재무 <jaemu.kim@example.invalid>"]
        parsed = BytesParser(policy=policy.default).parsebytes(build_mime(item, parent_ids=[]))
        self.assertIn("jaemu.kim@example.invalid", str(parsed["To"]))

    def test_cli_recipient_self_uses_profile_before_insert(self):
        gateway = FakeGateway()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = main(
                ["--execute", "--recipient-self", "--source", "discussion-email.json"],
                gateway_factory=lambda path: gateway,
            )
        self.assertEqual(result, 0)
        self.assertEqual(gateway.calls[0], ("profile",))

    def test_dry_run_recipient_self_does_not_create_gateway(self):
        factory_calls = []
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = main(
                ["--dry-run", "--recipient-self", "--source", "discussion-email.json"],
                gateway_factory=lambda path: factory_calls.append(path),
            )
        self.assertEqual(result, 0)
        self.assertEqual(factory_calls, [])

    def test_unread_is_forwarded_to_gateway(self):
        gateway = FakeGateway()
        counts = run_threads(
            self.threads[:1], gateway, execute=True, max_workers=1, unread=True,
        )
        self.assertEqual(counts.inserted, 3)
        self.assertTrue(all(call[3] for call in gateway.calls if call[0] == "insert"))

    def test_type_error_keeps_safe_traceback_location(self):
        class TypeErrorGateway(FakeGateway):
            def insert(self, raw, thread_id=None, *, unread=False):
                raise TypeError("bad sender@example.invalid token=private-token-value")
        counts = run_threads(
            self.threads[:1], TypeErrorGateway(), execute=True, max_workers=1, unread=True,
        )
        self.assertEqual(counts.failed, 3)
        diagnostic = counts.diagnostics[0]
        self.assertEqual(diagnostic.exception_class, "TypeError")
        self.assertTrue(diagnostic.stack)
        self.assertEqual(diagnostic.stack[-1][0], "test_gmail_seed_json_threads.py")
        self.assertNotIn("sender@example.invalid", diagnostic.message)
        self.assertNotIn("private-token-value", diagnostic.message)

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
    def _insert_labels(self, unread=False):
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
        self.assertEqual(gateway.insert(b"mime", unread=unread), "secret-provider-id")
        self.assertEqual(messages.kwargs["internalDateSource"], "dateHeader")
        self.assertNotIn("labelIds", {k: v for k, v in messages.kwargs.items() if k != "body"})
        self.assertEqual(messages.request.kwargs, {"num_retries": 0})
        return messages.kwargs["body"]["labelIds"]

    def test_insert_uses_insert_date_header_and_inbox(self):
        self.assertEqual(self._insert_labels(), ["INBOX"])

    def test_insert_unread_uses_inbox_and_unread(self):
        self.assertEqual(self._insert_labels(unread=True), ["INBOX", "UNREAD"])

    def test_authenticated_email_uses_profile_without_exposing_provider_data(self):
        class Request:
            def execute(self, **kwargs):
                self.kwargs = kwargs
                return {"emailAddress": "profile-user@example.invalid"}
        class Users:
            def __init__(self): self.request = Request(); self.kwargs = None
            def getProfile(self, **kwargs): self.kwargs = kwargs; return self.request
        class Service:
            def __init__(self): self.resource = Users()
            def users(self): return self.resource
        service = Service()
        gateway = GmailGateway(service)
        self.assertEqual(gateway.authenticated_email(), "profile-user@example.invalid")
        self.assertEqual(service.resource.kwargs, {"userId": "me"})
        self.assertEqual(service.resource.request.kwargs, {"num_retries": 0})

    def test_missing_authenticated_email_is_validation_error(self):
        class Request:
            def execute(self, **kwargs): return {}
        class Users:
            def getProfile(self, **kwargs): return Request()
        class Service:
            def users(self): return Users()
        with self.assertRaises(ValidationError):
            GmailGateway(Service()).authenticated_email()


if __name__ == "__main__":
    unittest.main()
