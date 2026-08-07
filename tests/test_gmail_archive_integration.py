from __future__ import annotations

from pathlib import Path

import pytest

from archive.analyzer import FixtureArchiveAnalyzer
from archive.gmail_adapter import CodexGmailGateway, GmailAdapter
from archive.models import ThreadAnalysis
from archive.service import ArchiveService
from archive.storage import ExcelRecordRepository
from office_blue import codex_gmail_bridge


FIXTURES = Path(__file__).parent / "fixtures"


def raw_message(message_id: str, received_at: str, *, attachment: bool = False) -> dict:
    return {
        "message_id": message_id,
        "thread_id": "gmail-thread-1",
        "sender": "requester@example.com",
        "recipients": ["owner@example.com"],
        "subject": "Project Gmail",
        "body": f"Body for {message_id}",
        "received_at": received_at,
        "attachments": ["quote.pdf"] if attachment else [],
    }


def test_codex_gmail_gateway_maps_and_sorts_complete_thread() -> None:
    gateway = CodexGmailGateway(
        lambda thread_id: [
            raw_message("msg-2", "2026-08-08T10:00:00+09:00"),
            raw_message("msg-1", "2026-08-07T09:00:00+09:00", attachment=True),
        ]
    )
    thread = GmailAdapter(gateway).fetch_normalized_thread("gmail-thread-1")

    assert thread.source_type == "gmail_mcp"
    assert [message.message_id for message in thread.messages] == ["msg-1", "msg-2"]
    assert thread.messages[0].cc == []
    assert thread.messages[0].reference_ids == []
    attachment = thread.messages[0].attachments[0]
    assert attachment.file_name == "quote.pdf"
    assert attachment.file_type == "pdf"
    assert attachment.access_status == "unverified"
    assert attachment.extracted_text == "unknown"


def test_codex_gmail_gateway_rejects_missing_timestamp() -> None:
    raw = raw_message("msg-1", "")
    with pytest.raises(ValueError, match="timestamp"):
        GmailAdapter(CodexGmailGateway(lambda thread_id: [raw])).fetch_normalized_thread(
            "gmail-thread-1"
        )


def test_codex_gmail_gateway_rejects_mixed_threads() -> None:
    raw = raw_message("msg-1", "2026-08-07T09:00:00+09:00")
    raw["thread_id"] = "different-thread"
    with pytest.raises(ValueError, match="different thread ID"):
        GmailAdapter(CodexGmailGateway(lambda thread_id: [raw])).fetch_normalized_thread(
            "gmail-thread-1"
        )


def test_fetch_gmail_thread_uses_existing_read_only_runner(monkeypatch) -> None:
    captured = {}

    def fake_runner(prompt: str, timeout: int):
        captured["prompt"] = prompt
        captured["timeout"] = timeout
        return [raw_message("msg-1", "2026-08-07T09:00:00+09:00")]

    monkeypatch.setattr(codex_gmail_bridge, "_run_read_only_snapshot", fake_runner)
    result = codex_gmail_bridge.fetch_gmail_thread("gmail-thread-1", timeout=12)

    assert result[0]["message_id"] == "msg-1"
    assert "read tools" in captured["prompt"]
    assert "Do not send" in captured["prompt"]
    assert captured["timeout"] == 12


def test_live_gmail_thread_runs_through_archive_service(tmp_path: Path) -> None:
    gateway = CodexGmailGateway(
        lambda thread_id: [raw_message("msg-1", "2026-08-07T09:00:00+09:00")]
    )
    thread = GmailAdapter(gateway).fetch_normalized_thread("gmail-thread-1")
    analysis = ThreadAnalysis.model_validate_json(
        (FIXTURES / "analysis_initial.json").read_text(encoding="utf-8")
    )
    workbook = tmp_path / "archive.xlsx"
    result = ArchiveService(
        FixtureArchiveAnalyzer(analysis),
        ExcelRecordRepository(workbook, tmp_path),
    ).process(thread, write=False)

    assert result.result_status == "new_record_ready"
    assert result.input_inventory["source_type"] == "gmail_mcp"
    assert result.archive_record.source_emails[0].source_type == "mcp_tool_result"
    assert not workbook.exists()


def test_live_gmail_thread_update_appends_change_history(tmp_path: Path) -> None:
    workbook = tmp_path / "archive.xlsx"
    repository = ExcelRecordRepository(workbook, tmp_path)
    initial_analysis = ThreadAnalysis.model_validate_json(
        (FIXTURES / "analysis_initial.json").read_text(encoding="utf-8")
    )
    update_analysis = ThreadAnalysis.model_validate_json(
        (FIXTURES / "analysis_update.json").read_text(encoding="utf-8")
    )
    initial_thread = GmailAdapter(
        CodexGmailGateway(
            lambda thread_id: [raw_message("msg-1", "2026-08-07T09:00:00+09:00")]
        )
    ).fetch_normalized_thread("gmail-thread-1")
    update_thread = GmailAdapter(
        CodexGmailGateway(
            lambda thread_id: [
                raw_message("msg-1", "2026-08-07T09:00:00+09:00"),
                raw_message("msg-2", "2026-08-08T10:00:00+09:00"),
            ]
        )
    ).fetch_normalized_thread("gmail-thread-1")

    created = ArchiveService(FixtureArchiveAnalyzer(initial_analysis), repository).process(
        initial_thread, write=True
    )
    updated = ArchiveService(FixtureArchiveAnalyzer(update_analysis), repository).process(
        update_thread, write=True
    )

    assert updated.storage.operation == "update"
    assert updated.storage.saved_record_id == created.storage.saved_record_id
    history = repository.list_change_history(created.storage.saved_record_id)
    due_change = next(item for item in history if item.field_path.endswith(".due_date"))
    assert due_change.previous_value == "2026-08-10"
    assert due_change.new_value == "2026-08-15"
