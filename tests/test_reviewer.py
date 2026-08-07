import unittest

from office_blue.models import EmailMessage
from office_blue.gmail_adapter import message_from_gmail_mcp
from office_blue.reviewer import review_email


def email(subject: str, body: str) -> EmailMessage:
    return EmailMessage(
        message_id="msg-1",
        thread_id="thread-1",
        sender="requester@example.com",
        recipients=["buyer@example.com"],
        subject=subject,
        body=body,
    )


class ReviewEmailTests(unittest.TestCase):
    def test_gmail_mcp_message_is_normalized(self) -> None:
        message = message_from_gmail_mcp(
            {
                "id": "gmail-1",
                "threadId": "thread-1",
                "from": "requester@example.com",
                "to": "buyer@example.com",
                "subject": "구매 요청",
                "body_text": "품목: 노트북",
            }
        )
        self.assertEqual(message.message_id, "gmail-1")
        self.assertEqual(message.recipients, ["buyer@example.com"])

    def test_missing_supplier_and_amount_creates_draft(self) -> None:
        result = review_email(
            email(
                "노트북 구매 요청",
                "품목: 노트북\n목적: 신규 입사자 업무용\n수량: 3개\n납기: 8월 20일까지",
            )
        )
        self.assertEqual(result.classification, "구매 요청")
        self.assertEqual(result.status, "정보 보완 필요")
        self.assertEqual(result.workflow_state, "WAITING_FOR_USER_APPROVAL")
        self.assertEqual({item.field for item in result.missing_fields}, {"supplier", "amount"})
        self.assertIsNotNone(result.reply_draft)
        self.assertEqual(result.reply_draft.to, "requester@example.com")

    def test_complete_purchase_is_ready_without_draft(self) -> None:
        result = review_email(
            email(
                "소프트웨어 구매 요청",
                "품목: 분석 서비스\n목적: 업무 효율화를 위해 필요\n공급사: Blue Co\n"
                "금액: KRW 1,200,000\n수량: 10 licenses\n납기: 8월 20일까지",
            )
        )
        self.assertEqual(result.status, "검토 가능")
        self.assertEqual(result.workflow_state, "REVIEW_BRIEF_READY")
        self.assertIsNone(result.reply_draft)

    def test_notice_does_not_generate_purchase_questions(self) -> None:
        result = review_email(email("시스템 점검 공지", "금요일 저녁에 시스템 점검을 안내드립니다."))
        self.assertEqual(result.classification, "공지")
        self.assertEqual(result.workflow_state, "BRIEFING_READY")
        self.assertEqual(result.missing_fields, [])

    def test_empty_required_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EmailMessage.from_dict({"message_id": "1", "sender": "a@example.com", "subject": "", "body": "x"})


if __name__ == "__main__":
    unittest.main()
