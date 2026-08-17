from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from main_service.gmail_mcp import (
    DEFAULT_QUERY,
    READ_ONLY_TOOLS,
    GmailClient,
    GmailError,
    _to_snapshot,
    fetch_messages,
)
from main_service.skill_registry import PROJECT_ROOT

SCHEMA = json.loads(
    (PROJECT_ROOT / "main_service" / "gmail_snapshot.schema.json").read_text(encoding="utf-8")
)


def message(msg_id: str, *, subject: str = "제목", date: str = "Mon, 17 Aug 2026 07:12:00 +0900"):
    return {
        "id": msg_id, "threadId": f"t{msg_id}", "from": "보낸이 <a@example.invalid>",
        "to": "받는이 <b@example.invalid>", "subject": subject, "date": date,
        "body": "본문", "snippet": "요약",
    }


class FakeClient:
    """search_threads / get_thread 응답을 흉내낸다. 서버도 네트워크도 쓰지 않는다."""

    def __init__(self, threads, thread_messages, failing=()):
        self.threads = threads
        self.thread_messages = thread_messages
        self.failing = set(failing)
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        if tool == "search_threads":
            return {"threads": self.threads}
        thread_id = arguments["threadId"]
        if thread_id in self.failing:
            raise GmailError("boom")
        return {"id": thread_id, "messages": self.thread_messages[thread_id]}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def run_with(client):
    return patch("main_service.gmail_mcp.GmailClient", return_value=client)


class FetchMessagesTests(unittest.TestCase):
    def test_returns_newest_first_with_thread_history(self):
        client = FakeClient(
            threads=[{"id": "t1"}],
            thread_messages={
                "t1": [
                    message("m1", date="Mon, 10 Aug 2026 09:00:00 +0900"),
                    message("m2", date="Mon, 17 Aug 2026 09:00:00 +0900"),
                ]
            },
        )
        with run_with(client):
            messages, errors = fetch_messages("is:unread")
        self.assertEqual(errors, [])
        self.assertEqual(len(messages), 1)
        # 스레드의 마지막 메시지가 받은편지함에 보이는 그 메일이고 앞선 것은 대화다
        self.assertEqual(messages[0]["message_id"], "m2")
        self.assertEqual(len(messages[0]["thread"]), 1)
        self.assertEqual(messages[0]["thread"][0]["message_id"], "m1")

    def test_one_broken_thread_does_not_empty_the_inbox(self):
        client = FakeClient(
            threads=[{"id": "t1"}, {"id": "t2"}],
            thread_messages={"t2": [message("m2")]},
            failing={"t1"},
        )
        with run_with(client):
            messages, errors = fetch_messages("is:unread")
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("t1", errors[0]["where"])

    def test_respects_max_results(self):
        threads = [{"id": f"t{i}"} for i in range(10)]
        client = FakeClient(threads, {f"t{i}": [message(f"m{i}")] for i in range(10)})
        with run_with(client):
            messages, _ = fetch_messages("is:unread", max_results=3)
        self.assertEqual(len(messages), 3)
        self.assertEqual(client.calls[0][1]["pageSize"], 3)

    def test_rejects_empty_query_and_out_of_range_limits(self):
        with self.assertRaises(ValueError):
            fetch_messages("   ")
        with self.assertRaises(ValueError):
            fetch_messages("is:unread", max_results=51)

    def test_default_query_is_unread(self):
        self.assertEqual(DEFAULT_QUERY, "is:unread")


class SnapshotTests(unittest.TestCase):
    def test_snapshot_matches_the_declared_schema(self):
        required = set(SCHEMA["properties"]["messages"]["items"]["required"])
        allowed = set(SCHEMA["properties"]["messages"]["items"]["properties"])
        snapshot = _to_snapshot(message("m1"))
        self.assertEqual(set(snapshot), required)
        self.assertEqual(set(snapshot) - allowed, set())

    def test_parses_rfc2822_date_to_iso(self):
        snapshot = _to_snapshot(message("m1", date="Mon, 17 Aug 2026 07:12:00 +0900"))
        self.assertTrue(snapshot["received_at"].startswith("2026-08-17T07:12:00"))

    def test_keeps_unparsable_date_verbatim(self):
        self.assertEqual(_to_snapshot(message("m1", date="어제"))["received_at"], "어제")

    def test_splits_multiple_recipients(self):
        snapshot = _to_snapshot({**message("m1"), "to": "a@x.invalid, b@x.invalid; c@x.invalid"})
        self.assertEqual(len(snapshot["recipients"]), 3)

    def test_falls_back_to_snippet_when_body_is_absent(self):
        payload = {k: v for k, v in message("m1").items() if k != "body"}
        self.assertEqual(_to_snapshot(payload)["body"], "요약")


class ReadOnlyTests(unittest.TestCase):
    """이 모듈에는 발송·삭제 경로가 없어야 한다."""

    def test_write_tools_are_rejected(self):
        client = GmailClient.__new__(GmailClient)  # __init__을 건너뛰고 가드만 확인
        for tool in ("create_draft", "send_message", "trash"):
            with self.assertRaises(GmailError):
                client.call(tool, {})

    def test_read_only_allowlist_excludes_create_draft(self):
        self.assertNotIn("create_draft", READ_ONLY_TOOLS)
        self.assertIn("search_threads", READ_ONLY_TOOLS)
        self.assertIn("get_thread", READ_ONLY_TOOLS)


if __name__ == "__main__":
    unittest.main()
