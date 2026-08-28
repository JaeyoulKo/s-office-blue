from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from main_service.render import render_draft
from main_service.service import purchase_draft_fingerprint


class FakeColumn:
    def __init__(self, app):
        self.app = app

    def caption(self, message):
        self.app.captions.append(message)

    def button(self, _label, *, disabled=False, **_kwargs):
        return self.app.clicked and not disabled


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.values = {}
        self.clicked = False
        self.captions = []
        self.successes = []
        self.errors = []
        self.warnings = []

    def text_input(self, _label, *, value, key):
        return self.values.get(key, value)

    def text_area(self, _label, *, value, key, **_kwargs):
        return self.values.get(key, value)

    def columns(self, *_args, **_kwargs):
        return FakeColumn(self), FakeColumn(self)

    def spinner(self, _message):
        return nullcontext()

    def success(self, message):
        self.successes.append(message)

    def error(self, message):
        self.errors.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def caption(self, message):
        self.captions.append(message)


class RenderPurchaseDraftTests(unittest.TestCase):
    def setUp(self):
        self.st = FakeStreamlit()
        self.save = Mock(return_value={"draftId": "private", "messageId": "private"})
        self.record = {
            "case_id": "purchase-1",
            "status": "ok",
            "draft": {
                "to": "original@example.com",
                "subject": "원래 제목",
                "body": "원래 본문",
            },
        }

    def render(self):
        with patch("main_service.render.st", self.st):
            render_draft(
                self.record,
                save_draft=self.save,
                draft_fingerprint=purchase_draft_fingerprint,
            )

    def test_no_click_makes_no_draft(self):
        self.render()
        self.save.assert_not_called()

    def test_click_passes_current_edits_exactly_once(self):
        self.st.values.update(
            {
                "draft_to_purchase-1": "edited@example.com",
                "draft_subject_purchase-1": "수정 제목",
                "draft_body_purchase-1": "수정 본문",
            }
        )
        self.st.clicked = True
        self.render()
        self.save.assert_called_once_with(
            to="edited@example.com", cc="", bcc="", subject="수정 제목", body="수정 본문"
        )
        self.assertEqual(
            self.st.successes,
            ["Gmail 임시보관함에 저장되었습니다. 아직 발송되지 않았습니다."],
        )

    def test_same_edit_is_blocked_on_rerun_but_body_edit_can_save_again(self):
        self.st.clicked = True
        self.render()
        self.render()
        self.assertEqual(self.save.call_count, 1)

        self.st.values["draft_body_purchase-1"] = "새 본문"
        self.render()
        self.assertEqual(self.save.call_count, 2)

    def test_synthetic_address_is_disclosed_before_click(self):
        self.st.values["draft_to_purchase-1"] = "fixture@example.invalid"
        self.render()
        self.save.assert_not_called()
        self.assertTrue(any("합성 주소" in warning for warning in self.st.warnings))


if __name__ == "__main__":
    unittest.main()
