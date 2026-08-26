from __future__ import annotations

import random
import re
import unittest
from email.utils import parseaddr
from pathlib import Path

from main_service.emails import (
    LABELS,
    PURCHASE_LABELS,
    REPLY_LABELS,
    Amount,
    amount_ranks,
    build_briefing,
    load_inbox,
    merge_urgency,
    normalize_email,
    parse_amount,
    rank_briefings,
    rule_urgency,
    summarize,
)
from main_service.skill_registry import PROJECT_ROOT

SAMPLE = (
    PROJECT_ROOT
    / "data/synthetic/emails/purchase-email-review/purchase-review-email-sample.json"
)


def briefing(case_id, *, label="구매 승인 검토 필요 이메일", urgency="low", amount=None, index=0):
    email = normalize_email({"case_id": case_id, "subject": case_id, "body": ""})
    email["index"] = index
    email["amount"] = Amount(value=amount, currency="KRW" if amount else "", raw="")
    record = {"status": "ok", "classification": {"label": label, "urgency": urgency}}
    item = build_briefing(email, record, amount_rank=None)
    item["urgency"] = urgency  # 규칙 신호가 없는 합성 데이터라 모델값을 그대로 쓴다
    return item


class ParseAmountTests(unittest.TestCase):
    def test_reads_ariba_string(self):
        amount = parse_amount("60,000,000 KRW")
        self.assertEqual(amount.value, 60_000_000)
        self.assertEqual(amount.currency, "KRW")

    def test_reads_korean_units(self):
        self.assertEqual(parse_amount("1억 2천만원").value, 120_000_000)
        self.assertEqual(parse_amount("3억원").value, 300_000_000)
        self.assertEqual(parse_amount("5,000만원").value, 50_000_000)

    def test_ignores_numbers_without_a_currency_token(self):
        """통화 없는 숫자를 금액으로 읽으면 정렬이 조용히 틀린다."""
        self.assertIsNone(parse_amount("PR10293 센서 500개 12개월 8/01").value)
        self.assertIsNone(parse_amount("회의는 3층 250호에서 14시에").value)

    def test_keeps_foreign_currency_unconverted(self):
        amount = parse_amount("$40,000")
        self.assertIsNone(amount.value)          # 환율 근거가 없으므로 환산하지 않는다
        self.assertEqual(amount.currency, "USD")

    def test_uses_candidates_in_priority_order(self):
        amount = parse_amount(None, "", "제목 없음", "총액 84,200,000 KRW 입니다")
        self.assertEqual(amount.value, 84_200_000)


class RankTests(unittest.TestCase):
    def test_urgent_purchase_with_highest_amount_comes_first(self):
        items = [
            briefing("low-big", urgency="low", amount=900, index=0),
            briefing("high-small", urgency="high", amount=10, index=1),
            briefing("high-big", urgency="high", amount=500, index=2),
        ]
        order = [item["case_id"] for item in rank_briefings(items)]
        self.assertEqual(order, ["high-big", "high-small", "low-big"])

    def test_notice_outranks_purchase_when_more_urgent(self):
        items = [
            briefing("purchase", label="구매 승인 검토 필요 이메일", urgency="medium", amount=999, index=0),
            briefing("notice", label="일반 이메일", urgency="high", index=1),
        ]
        self.assertEqual(rank_briefings(items)[0]["case_id"], "notice")

    def test_purchase_sorts_before_non_purchase_at_equal_urgency(self):
        items = [
            briefing("notice", label="일반 이메일", urgency="high", index=0),
            briefing("purchase", label="구매 승인 검토 필요 이메일", urgency="high", amount=1, index=1),
        ]
        self.assertEqual(rank_briefings(items)[0]["case_id"], "purchase")

    def test_unknown_amount_sorts_after_zero_amount(self):
        items = [
            briefing("unknown", urgency="high", amount=None, index=0),
            briefing("zero", urgency="high", amount=0, index=1),
        ]
        self.assertEqual([i["case_id"] for i in rank_briefings(items)], ["zero", "unknown"])

    def test_is_deterministic_for_fully_tied_items(self):
        """1~5번 항목이 전부 동점이어도 입력 순서가 재현되어야 한다."""
        items = [briefing(f"c{i}", urgency="low", amount=None, index=i) for i in range(30)]
        expected = [item["case_id"] for item in rank_briefings(list(items))]
        for seed in range(5):
            shuffled = list(items)
            random.Random(seed).shuffle(shuffled)
            self.assertEqual([i["case_id"] for i in rank_briefings(shuffled)], expected)

    def test_errors_are_excluded_from_the_ranking(self):
        items = [briefing("ok", index=0)]
        broken = briefing("broken", index=1)
        broken["status"] = "error"
        self.assertEqual([i["case_id"] for i in rank_briefings(items + [broken])], ["ok"])

    def test_amount_ranks_break_ties_by_index(self):
        inbox = load_inbox(SAMPLE)
        ranks = amount_ranks(inbox)
        by_rank = sorted(ranks, key=lambda case_id: ranks[case_id])
        values = [
            next(e for e in inbox if e["case_id"] == case_id)["amount"].value
            for case_id in by_rank[:6]
        ]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(len(set(ranks.values())), len(ranks))  # 동점이어도 순위는 유일


class RuleUrgencyTests(unittest.TestCase):
    def test_flags_top_amount_purchases(self):
        email = normalize_email({"case_id": "a", "subject": "", "body": ""})
        urgency, reasons = rule_urgency(email, amount_rank=0, is_purchase=True, amount_pool=30)
        self.assertEqual(urgency, "high")
        self.assertTrue(any("금액순" in reason for reason in reasons))

    def test_does_not_flag_amount_rank_for_non_purchase(self):
        email = normalize_email({"case_id": "a", "subject": "", "body": ""})
        self.assertEqual(rule_urgency(email, amount_rank=0, is_purchase=False, amount_pool=30)[0], "low")

    def test_flags_overdue_and_tax_keywords(self):
        overdue = normalize_email({"case_id": "a", "subject": "지급기일 초과 안내", "body": ""})
        self.assertEqual(rule_urgency(overdue, amount_rank=None, is_purchase=True)[0], "high")
        tax = normalize_email({"case_id": "b", "subject": "세금계산서 발행 요청", "body": ""})
        self.assertEqual(rule_urgency(tax, amount_rank=None, is_purchase=True)[0], "medium")

    def test_low_when_no_signal(self):
        email = normalize_email({"case_id": "a", "subject": "정기 점검 안내", "body": "안내드립니다."})
        self.assertEqual(rule_urgency(email, amount_rank=None, is_purchase=False)[0], "low")

    def test_amount_rank_does_not_fire_when_the_pool_is_too_small(self):
        """후보가 5건 이하면 '상위 5건'이 곧 전체라 목록만 전부 빨개진다."""
        email = normalize_email({"case_id": "a", "subject": "", "body": ""})
        self.assertEqual(
            rule_urgency(email, amount_rank=0, is_purchase=True, amount_pool=5)[0], "low"
        )
        self.assertEqual(
            rule_urgency(email, amount_rank=0, is_purchase=True, amount_pool=6)[0], "high"
        )

    def test_ai_attribution_omits_rule_note_when_no_rule_fired(self):
        rule = ("low", [])
        _, reasons = merge_urgency(rule, "low")
        self.assertEqual(reasons, ["[AI] low로 판단"])
        _, raised = merge_urgency(rule, "high")
        self.assertEqual(raised, ["[AI] high로 판단"])
        _, kept = merge_urgency(("high", ["[규칙] 지급기일 초과 표현"]), "low")
        self.assertIn("(규칙이 우선)", kept[-1])


class InboxTests(unittest.TestCase):
    def test_accepts_object_and_array(self):
        single = load_inbox(PROJECT_ROOT / "data/synthetic/emails/purchase-request.json")
        self.assertEqual(len(single), 1)
        inbox = load_inbox(SAMPLE)
        self.assertEqual(len(inbox), 10)
        self.assertEqual(
            [email["case_id"] for email in inbox],
            ["PR30922", "PR60274", "PR90612", "PR31829", "PR61720",
             "PR91582", "PR33011", "PR63340", "PR94122", "PR35455"],
        )

    def test_limit_applies(self):
        self.assertEqual(len(load_inbox(SAMPLE, limit=7)), 7)

    def test_case_ids_are_unique(self):
        inbox = load_inbox(SAMPLE)
        self.assertEqual(len({email["case_id"] for email in inbox}), len(inbox))

    def test_title_is_short_enough_for_a_header(self):
        for email in load_inbox(SAMPLE):
            self.assertLessEqual(len(email["title"]), 60, email["title"])

    def test_normalized_record_exposes_only_real_email_fields(self):
        """테스트 JSON의 미리 파싱된 필드가 파이프라인으로 새면 Gmail에서 무너진다."""
        allowed = {
            "case_id", "message_id", "thread_id", "sender", "recipients", "subject",
            "title", "body", "received_at", "attachments", "thread", "amount", "index",
        }
        leaked = {"total_amount", "cost_breakdown", "expected_effects", "pr_number",
                  "vendor", "description", "recent_comments", "type", "raw"}
        for email in load_inbox(SAMPLE):
            self.assertEqual(set(email) - allowed, set(), email["case_id"])
            self.assertEqual(set(email) & leaked, set(), email["case_id"])

    def test_amount_is_read_from_the_body_not_a_field(self):
        inbox = load_inbox(SAMPLE)
        amounts = [e["amount"].value for e in inbox if e["amount"].known]
        self.assertEqual(len(amounts), 10)
        self.assertIn(100_000_000, amounts)

    def test_missing_sections_appear_as_text_for_the_model_to_judge(self):
        """`has_data: false`를 플래그로 넘기지 않고 본문에 적어 모델이 읽게 한다."""
        bodies = [e["body"] for e in load_inbox(SAMPLE)]
        self.assertTrue(any("기재되지 않음" in body for body in bodies))

    def test_first_four_purchase_reviews_are_complete(self):
        """앞의 네 건은 구매 검토 Skill의 네 필수 항목을 모두 본문에 제공한다."""
        for email in load_inbox(SAMPLE)[:4]:
            self.assertNotIn("기재되지 않음", email["body"], email["case_id"])
            self.assertIn("비용 산출 근거:", email["body"])
            self.assertIn("예상 정량 효과:", email["body"])
            self.assertIn("이전 유사 계약과의 차이:", email["body"])
            self.assertIn("계약/적용 기간:", email["body"])
            self.assertIn("요청 부서:", email["body"])
            self.assertIn("승인 검토 URL: https://", email["body"])

    def test_purchase_review_fixtures_have_replyable_requesters(self):
        """구매 검토 fixture는 Gmail 초안 수신인으로 쓸 요청자 주소를 보존한다."""
        for email in load_inbox(SAMPLE):
            address = parseaddr(email["sender"])[1]
            self.assertTrue(address.endswith("@example.com"), email["case_id"])
            self.assertEqual(email["recipients"], ["buyer@example.invalid"])
            self.assertIn(f"요청자 이메일: {address}", email["body"])

    def test_codex_payload_carries_only_email_fields(self):
        from main_service.emails import for_codex

        payload = for_codex(load_inbox(SAMPLE)[0])
        self.assertEqual(
            set(payload) - {"case_id", "message_id", "thread_id", "sender", "recipients",
                            "subject", "body", "received_at", "attachments", "thread"},
            set(),
        )
        self.assertNotIn("amount", payload)
        self.assertNotIn("title", payload)

    def test_subject_title_strips_reply_prefixes(self):
        from main_service.emails import subject_title

        self.assertEqual(subject_title("Re: Fwd: 견적 회신"), "견적 회신")
        self.assertTrue(subject_title("Action required: Approve the Requisition").startswith("Approve"))
        self.assertEqual(subject_title(""), "(제목 없음)")

    def test_nothing_derived_from_the_body_leaks_before_classification(self):
        """분류 전 목록은 받은편지함 한 줄이 아는 것만 안다 — 제목·발신·날짜·첨부.

        금액은 본문을 읽어야 나오는 값이라, 분류를 돌리기 전에 보여주면 아직 하지 않은
        판단을 한 척하게 된다.
        """
        inbox = load_inbox(SAMPLE)
        ranks = amount_ranks(inbox)
        pending = [
            build_briefing(e, None, amount_rank=ranks.get(e["case_id"]), amount_pool=len(ranks))
            for e in inbox
        ]
        self.assertTrue(all(not item["classified"] for item in pending))
        self.assertTrue(all(item["label"] == "" for item in pending))

        summary = summarize(inbox, pending)
        self.assertEqual(summary["classified"], 0)
        self.assertEqual(summary["amount_total"], 0)
        self.assertEqual(summary["amount_known"], 0)
        self.assertEqual(summary["urgent"], 0)
        self.assertEqual(summary["top_amounts"], [])

    def test_amount_becomes_available_once_classified(self):
        inbox = load_inbox(SAMPLE)
        ranks = amount_ranks(inbox)
        record = {"status": "ok", "classification": {"label": "구매 승인 검토 필요 이메일", "urgency": "low"}}
        items = [
            build_briefing(e, record, amount_rank=ranks.get(e["case_id"]), amount_pool=len(ranks))
            for e in inbox
        ]
        summary = summarize(inbox, items)
        self.assertEqual(summary["classified"], len(inbox))
        self.assertGreater(summary["amount_total"], 0)
        self.assertTrue(summary["top_amounts"])

    def test_amount_sort_ignores_unclassified_items(self):
        big = briefing("big", amount=999, index=0)
        big["classified"] = False
        small = briefing("small", amount=1, index=1)
        order = [i["case_id"] for i in rank_briefings([big, small], mode="금액순")]
        self.assertEqual(order, ["small", "big"])

    def test_summary_counts_come_from_classification(self):
        inbox = load_inbox(SAMPLE)
        items = [briefing(f"c{i}", label="구매 승인 검토 필요 이메일", urgency="high", amount=100, index=i)
                 for i in range(3)]
        summary = summarize(inbox, items)
        self.assertEqual(summary["urgent"], 3)
        self.assertEqual(summary["needs_reply"], 3)
        self.assertEqual(summary["amount_total"], 300)

    def test_needs_reply_matches_decision_rule_routing(self):
        for label in LABELS:
            item = briefing("x", label=label)
            self.assertEqual(item["needs_reply"], label in REPLY_LABELS)
            self.assertEqual(item["is_purchase"], label in PURCHASE_LABELS)


class ProgressLineTests(unittest.TestCase):
    """진행 로그는 메일 제목이 아니라 우리가 한 일을 적는다.

    제목을 그대로 찍으면 `Approve the Requisition...`이 나와서 시스템이 승인을 한 것처럼
    읽힌다.
    """

    def test_reads_as_a_sentence_about_what_we_did(self):
        from main_service.render import classified_line

        line = classified_line("최유리 (Ariba)", "구매 승인 검토 필요 이메일", ok=True)
        self.assertEqual(line, "✅ 최유리 (Ariba) 님이 보낸 메일을 구매 승인 검토 필요 이메일로 분류했어요.")
        self.assertNotIn("Approve", line)

    def test_picks_the_korean_particle_by_final_consonant(self):
        from main_service.render import classified_line

        def label_of(text: str) -> str:
            return classified_line("a", text, ok=True).split("메일을 ")[1]

        self.assertEqual(label_of("구매 승인 검토 필요 이메일"), "구매 승인 검토 필요 이메일로 분류했어요.")
        self.assertEqual(label_of("논의 내용 요약 필요 이메일"), "논의 내용 요약 필요 이메일로 분류했어요.")
        self.assertEqual(label_of("일반 이메일"), "일반 이메일로 분류했어요.")

    def test_every_taxonomy_label_gets_a_particle(self):
        from main_service.render import classified_line

        for label in LABELS:
            self.assertIn("분류했어요", classified_line("보낸이", label, ok=True))

    def test_extracts_a_display_name_from_an_address(self):
        from main_service.render import display_name

        self.assertEqual(display_name('"Google 학술검색 알리미" <x@google.com>'), "Google 학술검색 알리미")
        self.assertEqual(display_name("Google <no-reply@accounts.google.com>"), "Google")
        self.assertEqual(display_name("<solo@example.invalid>"), "solo")
        self.assertEqual(display_name("최유리 (Ariba)"), "최유리 (Ariba)")
        self.assertEqual(display_name(""), "알 수 없는 사람")

    def test_failure_says_so_plainly(self):
        from main_service.render import classified_line

        self.assertEqual(
            classified_line("최유리", "", ok=False), "❌ 최유리 님이 보낸 메일은 분류하지 못했어요."
        )


class ConfirmationTests(unittest.TestCase):
    """펼친 카드에는 판단 근거 대신 사람이 확인할 것만 남긴다."""

    def test_keeps_only_the_user_confirmation_bucket(self):
        from main_service.render import confirmation_items

        classification = {
            "evidence": [
                {"type": "확인된 사실", "value": "총액이 본문에 있음"},
                {"type": "추론", "value": "정기 계약으로 보임"},
                {"type": "누락 정보", "value": "산정 근거 없음"},
                {"type": "사용자 확인 필요", "value": "지연이자 기준을 확인해야 함"},
            ]
        }
        self.assertEqual(confirmation_items(classification), ["지연이자 기준을 확인해야 함"])

    def test_accepts_the_bucketed_dict_shape(self):
        from main_service.render import confirmation_items

        items = confirmation_items(
            {"evidence": {"확인된 사실": ["a"], "사용자 확인 필요": ["b", "c"]}}
        )
        self.assertEqual(items, ["b", "c"])

    def test_accepts_a_separate_user_confirmation_field(self):
        from main_service.render import confirmation_items

        self.assertEqual(confirmation_items({"user_confirmation": ["예산 코드"]}), ["예산 코드"])

    def test_empty_when_nothing_needs_confirming(self):
        from main_service.render import confirmation_items

        self.assertEqual(confirmation_items({"evidence": [{"type": "추론", "value": "x"}]}), [])
        self.assertEqual(confirmation_items({}), [])


class TaxonomyTests(unittest.TestCase):
    """taxonomy.md와 decision-rules.md가 갈라지면 라우팅 절반이 도달 불가능해진다.

    주입된 taxonomy가 skill 자체 규칙을 이기기 때문에, 조용히 어긋나면 라우팅과
    `is_purchase` 판정이 무너진다.
    """

    @staticmethod
    def _labels(path: Path, section: str | None = None) -> set[str]:
        text = path.read_text(encoding="utf-8")
        if section is not None:
            # decision-rules.md에는 같은 불릿 형태를 쓰는 절이 여럿(증거 구분, 긴급도 판단)
            # 있으므로 해당 절만 잘라낸다.
            body = re.search(rf"^## {re.escape(section)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
            text = body.group(1) if body else ""
        return set(re.findall(r"^- `([^`]+)`:", text, re.MULTILINE))

    def test_taxonomy_labels_match_decision_rules(self):
        taxonomy = self._labels(PROJECT_ROOT / "shared/taxonomy.md")
        rules = self._labels(
            PROJECT_ROOT / "skills/email-classifier/references/decision-rules.md",
            section="분류 유형",
        )
        self.assertEqual(taxonomy, rules)
        self.assertEqual(taxonomy, set(LABELS))

    def test_single_label_precedence_covers_changed_thread_before_approval(self):
        taxonomy = (PROJECT_ROOT / "shared/taxonomy.md").read_text(encoding="utf-8")
        rules = (
            PROJECT_ROOT / "skills/email-classifier/references/decision-rules.md"
        ).read_text(encoding="utf-8")
        for text in (taxonomy, rules):
            self.assertIn("이전 값과 최신 값이 실제로 달라졌다면", text)
            self.assertIn("승인·예산 집행 요청", text)
            self.assertIn("`논의 내용 요약 필요 이메일`로 분류", text)
            self.assertIn("단일 메시지이거나 해당 변경 이력이 없고", text)


if __name__ == "__main__":
    unittest.main()
