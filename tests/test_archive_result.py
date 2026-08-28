from __future__ import annotations

import unittest

from main_service.archive_result import (
    ARCHIVE_FORMAT_ERROR_MESSAGE,
    CANONICAL_ARCHIVE_FIELDS,
    ArchiveResultFormatError,
    archive_output_contract,
    normalize_archive_result,
    validate_archive_result,
)


def canonical(**changes):
    result = {
        "발신자": "담당자",
        "날짜": "2026-08-22",
        "Topic": "AGV 도입 검토",
        "금액": 318_000_000,
        "통화": "KRW",
        "Business Impact": {
            "confirmed": ["처리량 개선이 필요합니다."],
            "estimated": ["운영비 절감이 예상됩니다."],
        },
        "Thread 진행 중 변경된 내용": [
            {"field": "금액", "from": 300_000_000, "to": 318_000_000}
        ],
        "결정된 내용": ["수정 견적을 검토하기로 했습니다."],
        "Open Item": ["최종 승인을 확인해야 합니다."],
    }
    result.update(changes)
    return result


class ArchiveResultNormalizationTests(unittest.TestCase):
    def test_ab_canonical_flat_result_passes_without_value_changes(self):
        expected = canonical()
        source = {
            "thread_id": "internal-thread",
            **expected,
            "승인 상태": "REAPPROVAL_REQUIRED",
            "적용 규칙": ["AR-01"],
        }
        self.assertEqual(normalize_archive_result(source, {}), expected)
        self.assertEqual(tuple(expected), CANONICAL_ARCHIVE_FIELDS)

    def test_supported_single_wrappers(self):
        for wrapper in (
            "archive_result",
            "archive_record",
            "excel_output",
            "thread_analysis",
        ):
            with self.subTest(wrapper=wrapper):
                self.assertEqual(
                    normalize_archive_result({wrapper: canonical()}, {}), canonical()
                )

    def test_two_level_nested_wrapper(self):
        raw = {"archive_result": {"archive_record": canonical()}}
        self.assertEqual(normalize_archive_result(raw, {}), canonical())

    def test_english_aliases_are_mapped(self):
        raw = {
            "sender": "담당자",
            "latest_date": "2026-08-22T18:30:00+09:00",
            "title": "AGV 도입 검토",
            "final_amount": "318,000,000",
            "currency": "krw",
            "business_impact": ["공급 안정성이 개선됩니다."],
            "change_history": ["견적이 변경되었습니다."],
            "confirmed_decisions": ["수정안을 검토합니다."],
            "unresolved_items": ["승인이 필요합니다."],
        }
        result = normalize_archive_result(raw, {})
        self.assertEqual(result["날짜"], "2026-08-22")
        self.assertEqual(result["금액"], 318_000_000)
        self.assertEqual(result["통화"], "KRW")
        self.assertEqual(
            result["Business Impact"],
            {"confirmed": ["공급 안정성이 개선됩니다."], "estimated": []},
        )

    def test_snapshot_safely_fills_only_sender_date_and_topic(self):
        raw = {
            "금액": None,
            "통화": None,
            "Business Impact": {},
            "Thread 진행 중 변경된 내용": [],
            "결정된 내용": [],
            "Open Item": [],
        }
        snapshot = {
            "sender": "최신 발신자",
            "received_at": "2026-08-22T09:00:00+09:00",
            "subject": "화성 사업장 AGV 도입",
            "body": "금액처럼 보이는 본문은 보완에 사용하지 않습니다.",
        }
        result = normalize_archive_result(raw, snapshot)
        self.assertEqual(result["발신자"], "최신 발신자")
        self.assertEqual(result["날짜"], "2026-08-22")
        self.assertEqual(result["Topic"], "화성 사업장 AGV 도입")
        self.assertIsNone(result["금액"])

    def test_partial_metadata_stays_empty_when_snapshot_has_no_value(self):
        result = normalize_archive_result({"archive_result": {}}, {})
        self.assertEqual(result["발신자"], "")
        self.assertEqual(result["날짜"], "")
        self.assertEqual(result["Topic"], "")

    def test_ambiguous_multiple_amounts_are_not_selected(self):
        result = normalize_archive_result(
            {"amount": [300_000_000, 318_000_000], "Topic": "견적 변경"}, {}
        )
        self.assertIsNone(result["금액"])

    def test_unrecognized_object_raises_format_error(self):
        with self.assertRaisesRegex(
            ArchiveResultFormatError, ARCHIVE_FORMAT_ERROR_MESSAGE
        ):
            normalize_archive_result({"unrelated": {"value": "내용"}}, {})

    def test_normal_empty_canonical_result_is_valid(self):
        empty = {
            "발신자": "",
            "날짜": "",
            "Topic": "",
            "금액": None,
            "통화": None,
            "Business Impact": {"confirmed": [], "estimated": []},
            "Thread 진행 중 변경된 내용": [],
            "결정된 내용": [],
            "Open Item": [],
        }
        self.assertEqual(normalize_archive_result(empty, {}), empty)
        self.assertIs(validate_archive_result(empty), empty)

    def test_hwaseong_style_nested_result_becomes_canonical(self):
        raw = {
            "archive_result": {
                "result_status": "new_record_ready",
                "archive_record": {
                    "latest_sender": "담당자",
                    "latest_message_date": "2026-08-22",
                    "title": "AGV 도입 견적 및 ROI 분석",
                    "final_amount": 318_000_000,
                    "currency": "KRW",
                    "business_impact": {
                        "confirmed": ["현재 운영 영향이 확인되었습니다."],
                        "estimated": ["ROI 개선이 예상됩니다."],
                    },
                    "changes_in_thread": ["최종 견적이 변경되었습니다."],
                    "decisions": ["수정 견적을 검토합니다."],
                    "open_items": ["투자 승인을 확인해야 합니다."],
                },
            }
        }
        result = normalize_archive_result(raw, {})
        self.assertEqual(tuple(result), CANONICAL_ARCHIVE_FIELDS)
        self.assertEqual(result["금액"], 318_000_000)
        self.assertEqual(result["Open Item"], ["투자 승인을 확인해야 합니다."])

    def test_duplicate_business_impact_sentence_is_removed(self):
        result = normalize_archive_result(
            {
                "Business Impact": {
                    "confirmed": ["같은 문장"],
                    "estimated": ["같은 문장"],
                }
            },
            {},
        )
        self.assertEqual(
            result["Business Impact"], {"confirmed": ["같은 문장"], "estimated": []}
        )

    def test_prompt_contract_forbids_wrappers_and_markdown(self):
        prompt = archive_output_contract()
        self.assertIn("정확히 하나의 JSON 객체", prompt)
        self.assertIn("Markdown code fence", prompt)
        self.assertIn("wrapper를 만들지 마세요", prompt)
        for field in CANONICAL_ARCHIVE_FIELDS:
            self.assertIn(field, prompt)


if __name__ == "__main__":
    unittest.main()
