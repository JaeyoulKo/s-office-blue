from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from main_service.gmail_reader import fetch_messages


class GmailReaderTests(unittest.TestCase):
    def test_rejects_empty_query(self) -> None:
        with self.assertRaises(ValueError):
            fetch_messages("  ")

    def test_rejects_result_limit_outside_read_boundary(self) -> None:
        with self.assertRaises(ValueError):
            fetch_messages("in:inbox", max_results=51)

    def test_uses_read_only_codex_exec_and_returns_messages(self) -> None:
        message = {
            "message_id": "synthetic-message",
            "thread_id": "synthetic-thread",
            "sender": "sender@example.invalid",
            "recipients": ["receiver@example.invalid"],
            "subject": "Synthetic subject",
            "body": "Synthetic body",
            "received_at": "2026-08-13T00:00:00Z",
            "attachments": [],
        }

        def complete(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch("main_service.gmail_reader.tempfile.TemporaryDirectory") as temporary,
            patch("main_service.gmail_reader.subprocess.run", side_effect=complete) as mocked,
            patch(
                "main_service.gmail_reader.Path.read_text",
                return_value=json.dumps({"messages": [message]}),
            ),
        ):
            temporary.return_value.__enter__.return_value = "."
            result = fetch_messages("in:inbox is:unread", max_results=5)

        command = mocked.call_args.args[0]
        self.assertEqual(result, [message])
        self.assertIn("exec", command)
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.4")
        self.assertIn('model_reasoning_effort="low"', command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--ephemeral", command)
        self.assertIn("--output-schema", command)
        self.assertIn("mcp__codex_apps__gmail_*", command[-1])
        self.assertIn("Do not draft, send", command[-1])


if __name__ == "__main__":
    unittest.main()
