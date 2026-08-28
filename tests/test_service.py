from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from main_service.archive_result import (
    ARCHIVE_FORMAT_ERROR_MESSAGE,
    ArchiveResultFormatError,
)
from main_service.codex_runner import CodexResult, CodexRunError
from main_service.service import (
    RECIPIENT_ERROR,
    archive_discussion_email,
    archive_discussion_emails,
    classify_emails,
    purchase_draft_fingerprint,
    save_purchase_review_draft,
)
from main_service.skill_registry import resolve_skill


def emails(count: int) -> list[dict[str, object]]:
    return [{"case_id": f"c{i}", "subject": f"s{i}", "body": ""} for i in range(count)]


def case_of(kwargs) -> str:
    """run_codex는 키워드 전용이라 대역도 payload에서 이메일을 꺼내야 한다."""
    return str(kwargs["payload"]["email"]["case_id"])


def ok(**kwargs) -> CodexResult:
    return CodexResult(text="{}", parsed={"label": "일반 이메일", "case_id": case_of(kwargs)})


class PurchaseDraftTests(unittest.TestCase):
    def test_saves_current_edited_fields_once_through_gmail_boundary(self):
        with patch("main_service.service.create_draft", return_value={"draftId": "internal"}) as create:
            result = save_purchase_review_draft(
                to="담당자 <edited@example.com>",
                cc="copy@example.com",
                bcc="hidden@example.com",
                subject="수정한 제목",
                body="사용자가 수정한 최신 본문",
            )
        create.assert_called_once_with(
            to=["edited@example.com"],
            cc=["copy@example.com"],
            bcc=["hidden@example.com"],
            subject="수정한 제목",
            body="사용자가 수정한 최신 본문",
        )
        self.assertEqual(result, {"draftId": "internal"})

    def test_blocks_recipient_name_without_address(self):
        with patch("main_service.service.create_draft") as create:
            with self.assertRaisesRegex(ValueError, RECIPIENT_ERROR):
                save_purchase_review_draft(to="구매 담당자", subject="제목", body="본문")
        create.assert_not_called()

    def test_fingerprint_changes_only_when_current_edit_changes(self):
        first = purchase_draft_fingerprint(to="a@example.com", subject="제목", body="본문")
        same = purchase_draft_fingerprint(to="a@example.com", subject="제목", body="본문")
        edited = purchase_draft_fingerprint(to="a@example.com", subject="제목", body="수정 본문")
        self.assertEqual(first, same)
        self.assertNotEqual(first, edited)


class ClassifyEmailsTests(unittest.TestCase):
    def test_preserves_input_order(self):
        """완료 순서가 역순이어도 반환은 입력 순서여야 한다.

        `index`가 정렬의 마지막 tiebreak이라, 여기가 흔들리면 화면 순서가 재현되지 않는다.
        """

        def slow(**kwargs):
            time.sleep(0.30 - 0.05 * int(case_of(kwargs)[1:]))
            return ok(**kwargs)

        with patch("main_service.service.run_codex", side_effect=slow):
            records = classify_emails(emails(5), max_workers=5, on_event=None)
        self.assertEqual([r["case_id"] for r in records], [f"c{i}" for i in range(5)])
        self.assertEqual([r["index"] for r in records], list(range(5)))

    def test_runs_concurrently(self):
        lock = threading.Lock()
        live = peak = 0

        def tracked(**kwargs):
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.15)
            with lock:
                live -= 1
            return ok(**kwargs)

        with patch("main_service.service.run_codex", side_effect=tracked):
            classify_emails(emails(6), max_workers=3)
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 3)

    def test_records_failure_without_aborting_the_batch(self):
        def flaky(**kwargs):
            if case_of(kwargs) == "c1":
                raise CodexRunError("boom", kind="missing_cli")  # 재시도 대상 아님
            return ok(**kwargs)

        with patch("main_service.service.run_codex", side_effect=flaky):
            records = classify_emails(emails(3), max_workers=3)
        self.assertEqual([r["status"] for r in records], ["ok", "error", "ok"])
        self.assertIn("boom", records[1]["error"])

    def test_retries_a_retryable_failure_once(self):
        calls: list[str] = []

        def once(**kwargs):
            case_id = case_of(kwargs)
            calls.append(case_id)
            if calls.count(case_id) == 1:
                raise CodexRunError("timed out", kind="timeout")
            return ok(**kwargs)

        with patch("main_service.service.run_codex", side_effect=once):
            records = classify_emails(emails(1), max_workers=1)
        self.assertEqual(records[0]["status"], "ok")
        self.assertEqual(records[0]["attempts"], 2)

    def test_does_not_retry_a_non_retryable_failure(self):
        calls: list[str] = []

        def always(**kwargs):
            calls.append(case_of(kwargs))
            raise CodexRunError("no cli", kind="missing_cli")

        with patch("main_service.service.run_codex", side_effect=always):
            records = classify_emails(emails(1), max_workers=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(records[0]["attempts"], 1)

    def test_emits_events_on_the_calling_thread(self):
        """Streamlit 워커 스레드에는 ScriptRunContext가 없어 st.* 호출이 깨진다.

        진행 표시를 그리는 콜백은 반드시 호출자 스레드에서 실행되어야 한다.
        """
        threads: set[int] = set()
        states: list[str] = []

        def record(event):
            threads.add(threading.get_ident())
            states.append(event["state"])

        with patch("main_service.service.run_codex", side_effect=ok):
            classify_emails(emails(4), max_workers=4, on_event=record)

        self.assertEqual(threads, {threading.get_ident()})
        self.assertEqual(states[0], "submitted")
        self.assertEqual(len(states), 5)  # submitted + 4건

    def test_unparsable_output_is_an_error_not_a_crash(self):
        with patch(
            "main_service.service.run_codex",
            side_effect=lambda *a, **k: CodexResult(text="not json", parsed=None),
        ):
            records = classify_emails(emails(1))
        self.assertEqual(records[0]["status"], "error")
        self.assertEqual(records[0]["text"], "not json")

    def test_empty_input_returns_empty(self):
        self.assertEqual(classify_emails([]), [])

    def test_workers_are_capped(self):
        with patch("main_service.service.run_codex", side_effect=ok):
            seen: list[int] = []
            classify_emails(
                emails(3), max_workers=99, on_event=lambda e: seen.append(e["workers"])
            )
        self.assertEqual(set(seen), {3})  # 메일 수와 MAX_PARALLEL 중 작은 쪽


class ClassifyArgvTests(unittest.TestCase):
    """tests/test_gmail_reader.py와 같은 방식으로 실제 argv를 확인한다."""

    def test_sends_low_effort_and_priority_tier(self):
        captured: dict[str, object] = {}

        def fake(*args, **kwargs):
            captured.update(kwargs)
            return CodexResult(text="{}", parsed={"label": "일반 이메일"})

        with patch("main_service.service.run_codex", side_effect=fake):
            classify_emails(emails(1))
        self.assertEqual(captured["reasoning_effort"], "low")
        self.assertEqual(captured["service_tier"], "priority")
        self.assertEqual(captured["skill"], "email-classifier")
        self.assertEqual(captured["timeout_seconds"], 120)

    def test_taxonomy_is_injected(self):
        captured: dict[str, object] = {}

        def fake(*args, **kwargs):
            captured.update(kwargs)
            return CodexResult(text="{}", parsed={"label": "일반 이메일"})

        with patch("main_service.service.run_codex", side_effect=fake):
            classify_emails(emails(1))
        self.assertIn("구매 승인 검토 필요 이메일", captured["payload"]["taxonomy"])
        self.assertIn("urgency", captured["prompt"])


class EmailAgentIntegrationTests(unittest.TestCase):
    def test_archive_review_uses_promoted_approved_skill(self):
        captured: dict[str, object] = {}

        def fake(**kwargs):
            captured.update(kwargs)
            return CodexResult(
                text="{}",
                parsed={
                    "발신자": "담당자",
                    "날짜": "2026-08-22",
                    "Topic": "논의 Thread",
                    "금액": None,
                    "통화": None,
                    "Business Impact": {"confirmed": [], "estimated": []},
                    "Thread 진행 중 변경된 내용": [],
                    "결정된 내용": [],
                    "Open Item": [],
                },
            )

        selected_thread = {
            "case_id": "selected",
            "subject": "논의 Thread",
            "body": "최신 본문",
            "thread": [{"message_id": "m1", "body": "이전 본문"}],
        }
        with patch("main_service.service.run_codex", side_effect=fake):
            archive_discussion_email(selected_thread, {}, None)
        self.assertEqual(captured["skill"], "email-archive-agent")
        self.assertEqual(captured["payload"]["email"], selected_thread)
        self.assertIn("정확히 하나의 JSON 객체만 반환", captured["prompt"])
        self.assertIn("wrapper를 만들지 마세요", captured["prompt"])
        self.assertIn("references/output-schema.md", captured["prompt"])
        skill_path = resolve_skill("email-archive-agent")
        self.assertEqual(skill_path.name, "email-archive-agent")
        discussion_path = resolve_skill("discussion-email-review")
        self.assertEqual(discussion_path.name, "discussion-email-review")
        self.assertNotEqual(skill_path, discussion_path)
        discussion_text = (discussion_path / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: discussion-email-review", discussion_text)
        skill_text = (skill_path / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: email-archive-agent", skill_text)
        for relative in (
            "references/workflow.md",
            "references/company-archive-policy.md",
            "references/output-schema.md",
            "templates/archive-summary.md",
            "templates/change-history.md",
        ):
            self.assertTrue((skill_path / relative).is_file(), relative)
            self.assertIn(relative, skill_text)

    def test_archive_review_normalizes_nested_result_at_service_boundary(self):
        nested = {
            "archive_result": {
                "archive_record": {
                    "sender": "담당자",
                    "date": "2026-08-22",
                    "title": "논의 Thread",
                    "final_amount": None,
                    "currency": None,
                    "business_impact": [],
                    "changes": [],
                    "decisions": [],
                    "open_items": [],
                }
            }
        }
        email = {"subject": "논의 Thread", "received_at": "2026-08-22"}
        with patch(
            "main_service.service.run_codex",
            return_value=CodexResult(text="raw result", parsed=nested),
        ):
            result = archive_discussion_email(email, {}, None)
        self.assertEqual(result.parsed["Topic"], "논의 Thread")
        self.assertNotIn("archive_result", result.parsed)


class ArchiveBatchTests(unittest.TestCase):
    def test_runs_in_parallel_with_three_worker_cap_and_preserves_order(self):
        lock = threading.Lock()
        live = peak = 0

        def analyze(email, classification, model):
            del classification, model
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.04 * (6 - int(email["case_id"][1:])))
            with lock:
                live -= 1
            return CodexResult(text="{}", parsed={"Topic": email["case_id"]})

        targets = [(email, {}) for email in emails(5)]
        with patch("main_service.service.archive_discussion_email", side_effect=analyze):
            records = archive_discussion_emails(targets, max_workers=99)
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 3)
        self.assertEqual([record["case_id"] for record in records], [f"c{i}" for i in range(5)])
        self.assertEqual(len({record["run_id"] for record in records}), 5)

    def test_one_failure_does_not_stop_other_results_or_retry(self):
        calls: list[str] = []

        def analyze(email, classification, model):
            del classification, model
            calls.append(email["case_id"])
            if email["case_id"] == "c1":
                raise RuntimeError("private raw details")
            return CodexResult(text="{}", parsed={})

        targets = [(email, {}) for email in emails(3)]
        with patch("main_service.service.archive_discussion_email", side_effect=analyze):
            records = archive_discussion_emails(targets)
        self.assertEqual([record["status"] for record in records], ["ok", "error", "ok"])
        self.assertEqual(calls.count("c1"), 1)
        self.assertNotIn("private raw details", records[1]["error"])

    def test_format_error_has_safe_user_message_and_is_not_retried(self):
        calls = 0

        def analyze(*_args):
            nonlocal calls
            calls += 1
            raise ArchiveResultFormatError(ARCHIVE_FORMAT_ERROR_MESSAGE)

        with patch(
            "main_service.service.archive_discussion_email", side_effect=analyze
        ):
            records = archive_discussion_emails([(emails(1)[0], {})])
        self.assertEqual(calls, 1)
        self.assertEqual(records[0]["status"], "error")
        self.assertEqual(records[0]["error"], ARCHIVE_FORMAT_ERROR_MESSAGE)


if __name__ == "__main__":
    unittest.main()
