import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.seed_gmail import CASES_PATH, load_cases  # noqa: E402
from harness import gmail  # noqa: E402


@pytest.fixture(scope="session")
def cases():
    return load_cases()


@pytest.fixture(scope="session")
def snapshot():
    return gmail.from_cases(CASES_PATH, snapshot_id="test")


@pytest.fixture
def perfect_result(snapshot, cases):
    """모든 지표를 만점 받는 가짜 결과. 지표 계산이 옳은지 확인하는 기준선이다."""
    expected = {c["subject"]: c["expected"] for c in cases if c.get("subject")}
    items, rank = [], 0
    for message in snapshot["messages"]:
        answer = expected.get(message["subject"], {})
        top = answer.get("priority_top")
        rank += 1 if top else 0
        items.append({
            "message_id": message["message_id"],
            "category": answer.get("category", "unknown"),
            "category_reason": "테스트",
            "evidence": message["subject"] or message["body"][:20],
            "priority_rank": rank if top else None,
            "priority_reason": "",
            "amount_krw": answer.get("amount_krw"),
            "deadline": None,
            "owner": None,
        })
    counts = {k: 0 for k in ("important", "ariba_approval", "discussion", "notice", "unknown")}
    for item in items:
        counts[item["category"]] += 1
    return {
        "items": items,
        "briefing": {
            "counts": counts,
            "top_items": [
                {"message_id": i["message_id"], "subject": "", "why": ""}
                for i in items if i["priority_rank"]
            ],
            "summary": "테스트",
        },
        "notes": [],
    }
