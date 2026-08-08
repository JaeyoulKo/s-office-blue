"""계약이 실제로 계약 노릇을 하는지."""

import pytest

from harness import contracts, gmail


def test_fixture_snapshot_satisfies_contract(snapshot):
    assert contracts.validate(contracts.SNAPSHOT, snapshot) == []


def test_snapshot_message_ids_are_unique(snapshot):
    ids = [m["message_id"] for m in snapshot["messages"]]
    assert len(ids) == len(set(ids))


def test_ground_truth_is_never_leaked_into_snapshot(snapshot):
    """모델이 정답을 훔쳐볼 수 있으면 실험 전체가 무의미해진다."""
    blob = str(snapshot)
    assert "expected" not in blob
    assert "priority_top" not in blob


def test_seed_header_is_stripped():
    """주입 메일의 케이스 표식은 스냅샷에 남으면 안 된다."""
    dirty = {
        "snapshot_id": "x", "collected_at": "", "adapter": "fixture", "query": "",
        "messages": [{
            "message_id": "m1", "thread_id": "t1", "from": "a@b.test", "to": "c@d.test",
            "subject": "X-OfficeBlue-Case: C99\n제목", "date": "",
            "body": "X-OfficeBlue-Case: C99\n본문", "attachments": [], "labels": [],
        }],
    }
    clean = gmail.normalize(dirty)
    assert "X-OfficeBlue" not in clean["messages"][0]["subject"]
    assert "X-OfficeBlue" not in clean["messages"][0]["body"]


def test_perfect_result_satisfies_contract(perfect_result):
    assert contracts.validate(contracts.TRIAGE, perfect_result) == []


@pytest.mark.parametrize("broken", [
    {"items": [], "briefing": {}},                       # briefing 하위 필드 누락
    {"items": [], "notes": []},                          # briefing 자체가 없음
])
def test_incomplete_output_is_rejected(broken):
    assert contracts.validate(contracts.TRIAGE, broken) != []


def test_structured_output_requires_every_property():
    """--output-schema 는 OpenAI structured outputs를 쓴다. 선택 필드가 있으면 400이 난다.

    스키마를 고칠 때 required 에 키를 빠뜨리는 실수를 여기서 잡는다.
    """
    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" and "properties" in node:
            assert set(node["properties"]) == set(node.get("required", [])), (
                f"required 가 properties 와 다릅니다: {sorted(node['properties'])}"
            )
            assert node.get("additionalProperties") is False
        for value in node.values():
            if isinstance(value, dict):
                walk(value)
            elif isinstance(value, list):
                for entry in value:
                    walk(entry)

    for name in (contracts.SNAPSHOT, contracts.TRIAGE):
        walk(contracts.load(name))
