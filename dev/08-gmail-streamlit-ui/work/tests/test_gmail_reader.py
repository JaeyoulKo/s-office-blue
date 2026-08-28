from __future__ import annotations

import unittest
from unittest.mock import patch

from main_service.gmail_mcp import fetch_messages
from main_service.service import fetch_inbox


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, arguments: dict):
        self.calls.append((tool, arguments))
        if tool == "search_threads":
            return {"threads": [{"id": "synthetic-thread"}]}
        return {
            "messages": [{
                "id": "synthetic-message", "threadId": "synthetic-thread",
                "sender": "sender@example.invalid",
                "toRecipients": ["receiver@example.invalid"],
                "subject": "Synthetic subject", "plaintextBody": "Synthetic body",
                "date": "Thu, 13 Aug 2026 09:00:00 +0900",
            }],
        }

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class GmailReaderTests(unittest.TestCase):
    def test_service_delegates_inbox_loading_to_reader(self) -> None:
        with patch("main_service.service.fetch_messages", return_value=([], [])) as mocked:
            self.assertEqual(fetch_inbox("in:inbox", max_results=3), ([], []))
        mocked.assert_called_once_with("in:inbox", max_results=3)

    def test_rejects_empty_query(self) -> None:
        with self.assertRaises(ValueError):
            fetch_messages("  ")

    def test_rejects_result_limit_outside_read_boundary(self) -> None:
        with self.assertRaises(ValueError):
            fetch_messages("in:inbox", max_results=51)

    def test_uses_read_only_mcp_tools_and_returns_messages(self) -> None:
        client = FakeClient()
        with patch("main_service.gmail_mcp.GmailClient", return_value=client):
            result = fetch_messages("in:inbox is:unread", max_results=5)

        self.assertEqual(len(result[0]), 1)
        self.assertEqual(result[1], [])
        self.assertEqual([name for name, _ in client.calls], ["search_threads", "get_thread"])


if __name__ == "__main__":
    unittest.main()
