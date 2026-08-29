from __future__ import annotations

import unittest
from unittest.mock import patch

from main_service.codex_runner import CodexResult
from main_service.emails import LABELS, PURCHASE_LABELS
from main_service.replies import (
    REPLY_ROUTES,
    ReplyRoute,
    can_reply,
    extract_draft,
    reply_route,
    supported_labels,
)
from main_service.service import draft_replies, draft_reply
from main_service.skill_registry import SKILLS

APPROVAL = "구매 승인 검토 필요 이메일"


class RouteTests(unittest.TestCase):
    def test_only_purchase_approval_is_supported_today(self):
        self.assertEqual(supported_labels(), [APPROVAL])
        self.assertTrue(can_reply(APPROVAL))
        for label in LABELS:
            if label != APPROVAL:
                self.assertFalse(can_reply(label), label)

    def test_every_route_points_at_an_approved_skill(self):
        """`skills/`로 승격되지 않은 Skill을 가리키면 런타임에야 터진다."""
        for label, route in REPLY_ROUTES.items():
            self.assertIn(route.skill, SKILLS, label)
            self.assertTrue((SKILLS[route.skill] / "SKILL.md").is_file(), route.skill)

    def test_route_keys_match_their_label(self):
        for key, route in REPLY_ROUTES.items():
            self.assertEqual(key, route.label)

    def test_route_labels_exist_in_the_taxonomy(self):
        for label in REPLY_ROUTES:
            self.assertIn(label, LABELS)

    def test_unknown_label_has_no_route(self):
        self.assertIsNone(reply_route("존재하지 않는 분류"))
        self.assertIsNone(reply_route(""))
        self.assertIsNone(reply_route(None))

    def test_all_purchase_labels_are_wired(self):
        unwired = PURCHASE_LABELS - set(REPLY_ROUTES)
        self.assertEqual(unwired, set())


class StageTests(unittest.TestCase):
    """화면은 이 단계로 메일을 묶는다."""

    def stage(self, **kw):
        from main_service.replies import mail_stage

        base = {"classified": True, "label": APPROVAL, "follow_up": True, "draft_record": None}
        return mail_stage(**{**base, **kw})

    def test_unclassified_is_pending(self):
        self.assertEqual(self.stage(classified=False, label=""), "pending")

    def test_reply_capable_and_undrafted_is_todo(self):
        self.assertEqual(self.stage(), "todo")

    def test_notice_has_nothing_to_do(self):
        self.assertEqual(self.stage(label="일반 이메일", follow_up=False), "none")

    def test_follow_up_without_a_skill_is_unsupported(self):
        """후속 조치는 필요한데 회신 Skill이 아직 없는 상태를 '처리 없음'과 섞지 않는다."""
        self.assertEqual(self.stage(label="논의 내용 요약 필요 이메일"), "unsupported")

    def test_drafted_is_done_even_when_there_is_nothing_to_send(self):
        """'검토했고 보낼 게 없다'도 처리 결과다. 미처리로 돌리지 않는다."""
        record = {"status": "ok", "draft": None,
                  "review": {"review_status": "READY_FOR_APPROVAL_REVIEW"}}
        self.assertEqual(self.stage(draft_record=record), "done")

    def test_drafted_with_a_reply_is_done(self):
        self.assertEqual(self.stage(draft_record={"status": "ok", "draft": {"body": "x"}}), "done")

    def test_failed_draft_is_error(self):
        self.assertEqual(self.stage(draft_record={"status": "error"}), "error")

    def test_every_stage_has_a_caption_and_a_place_in_the_order(self):
        from main_service.render import STAGE_ORDER, STAGE_VIEW
        from main_service import replies

        stages = {
            getattr(replies, name) for name in dir(replies) if name.startswith("STAGE_")
        }
        self.assertEqual(stages, set(STAGE_ORDER))
        self.assertEqual(stages, set(STAGE_VIEW))

    def test_discussion_review_stage_copy_describes_the_available_action(self):
        from main_service.render import STAGE_VIEW

        self.assertEqual(STAGE_VIEW["unsupported"][0], "🕓 내용 요약 검토 필요")
        self.assertEqual(
            STAGE_VIEW["unsupported"][1],
            "논의 내용 요약을 할 수 있는 건입니다. 눌러서 선택하세요.",
        )


class ExtractDraftTests(unittest.TestCase):
    def setUp(self):
        self.route = REPLY_ROUTES[APPROVAL]

    def test_pulls_the_draft_out_of_the_contract(self):
        draft = extract_draft(
            self.route,
            {"reply_draft": {"to": "a@b.invalid", "subject": "[보완 요청]", "body": "본문"}},
        )
        self.assertEqual(draft, {"to": "a@b.invalid", "subject": "[보완 요청]", "body": "본문"})

    def test_null_draft_is_not_an_error(self):
        """승인 가능하면 Skill이 reply_draft를 null로 준다. 보낼 초안이 없다는 판단이다."""
        self.assertIsNone(extract_draft(self.route, {"reply_draft": None}))
        self.assertIsNone(extract_draft(self.route, {}))

    def test_blank_body_is_treated_as_no_draft(self):
        self.assertIsNone(extract_draft(self.route, {"reply_draft": {"body": "   "}}))

    def test_non_dict_output_is_safe(self):
        self.assertIsNone(extract_draft(self.route, "not json"))
        self.assertIsNone(extract_draft(self.route, None))


def email(case_id="c0"):
    return {"case_id": case_id, "subject": "s", "body": "b", "amount": None}


def approved(**extra):
    return {"label": APPROVAL, **extra}


class DraftReplyTests(unittest.TestCase):
    def test_uses_the_skill_named_by_the_route(self):
        captured = {}

        def fake(**kwargs):
            captured.update(kwargs)
            return CodexResult(
                text="{}", parsed={"reply_draft": {"to": "x", "subject": "y", "body": "z"}}
            )

        with patch("main_service.service.run_codex", side_effect=fake):
            record = draft_reply(email(), approved())

        self.assertEqual(captured["skill"], "purchase-email-review")
        self.assertEqual(record["draft"]["body"], "z")
        self.assertEqual(record["label"], APPROVAL)

    def test_refuses_an_unsupported_label(self):
        with patch("main_service.service.run_codex") as mocked:
            with self.assertRaises(ValueError):
                draft_reply(email(), {"label": "일반 이메일"})
        mocked.assert_not_called()  # 지원 안 하면 Codex를 아예 부르지 않는다

    def test_refuses_when_there_is_no_classification(self):
        with self.assertRaises(ValueError):
            draft_reply(email(), None)


class DraftRepliesTests(unittest.TestCase):
    def test_preserves_input_order_and_isolates_failures(self):
        def fake(**kwargs):
            if kwargs["payload"]["email"]["case_id"] == "c1":
                raise RuntimeError("boom")
            return CodexResult(text="{}", parsed={"reply_draft": {"body": "ok"}})

        targets = [(email(f"c{i}"), approved()) for i in range(3)]
        with patch("main_service.service.run_codex", side_effect=fake):
            records = draft_replies(targets, max_workers=3)

        self.assertEqual([r["case_id"] for r in records], ["c0", "c1", "c2"])
        self.assertEqual([r["status"] for r in records], ["ok", "error", "ok"])

    def test_empty_input_returns_empty(self):
        self.assertEqual(draft_replies([]), [])

    def test_events_fire_on_the_calling_thread(self):
        import threading

        seen: set[int] = set()
        targets = [(email(f"c{i}"), approved()) for i in range(3)]
        with patch(
            "main_service.service.run_codex",
            side_effect=lambda **k: CodexResult(text="{}", parsed={"reply_draft": {"body": "b"}}),
        ):
            draft_replies(targets, on_event=lambda e: seen.add(threading.get_ident()))
        self.assertEqual(seen, {threading.get_ident()})


if __name__ == "__main__":
    unittest.main()
