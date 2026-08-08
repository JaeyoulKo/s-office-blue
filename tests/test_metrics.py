"""지표가 정말 잡아내는지 — 지표를 못 믿으면 실험 결과도 못 믿는다."""

import copy

from experiments import metrics


def test_every_case_has_ground_truth(snapshot, cases):
    truth = metrics.ground_truth(snapshot, cases)
    assert len(truth) == len(snapshot["messages"])


def test_perfect_result_scores_full_marks(snapshot, cases, perfect_result):
    score = metrics.score(perfect_result, snapshot, metrics.ground_truth(snapshot, cases))
    assert score["accuracy"] == 1.0
    assert score["evidence_rate"] == 1.0
    assert score["coverage"] == 1.0
    assert score["priority_recall"] == 1.0
    assert score["hallucinated_ids"] == []
    assert score["counts_consistent"] is True


def test_invented_message_id_is_caught(snapshot, cases, perfect_result):
    broken = copy.deepcopy(perfect_result)
    broken["items"][0]["message_id"] = "msg-DOES-NOT-EXIST"
    score = metrics.score(broken, snapshot, metrics.ground_truth(snapshot, cases))
    assert score["hallucinated_ids"] == ["msg-DOES-NOT-EXIST"]
    assert score["hallucination_free"] is False
    assert score["coverage"] < 1.0


def test_paraphrased_evidence_does_not_count(snapshot, cases, perfect_result):
    """근거를 요약하면 인용이 아니다. 원문 부분문자열이어야 한다."""
    broken = copy.deepcopy(perfect_result)
    broken["items"][0]["evidence"] = "제목에 긴급이라고 적혀 있었음"
    score = metrics.score(broken, snapshot, metrics.ground_truth(snapshot, cases))
    assert score["evidence_rate"] < 1.0


def test_whitespace_differences_are_forgiven(snapshot, cases, perfect_result):
    """줄바꿈·공백 차이까지 오답으로 잡으면 지표가 너무 예민해진다."""
    good = copy.deepcopy(perfect_result)
    good["items"][0]["evidence"] = "  " + good["items"][0]["evidence"].replace(" ", "  ") + "\n"
    score = metrics.score(good, snapshot, metrics.ground_truth(snapshot, cases))
    assert score["evidence_rate"] == 1.0


def test_missing_and_duplicated_items_are_caught(snapshot, cases, perfect_result):
    broken = copy.deepcopy(perfect_result)
    broken["items"].append(copy.deepcopy(broken["items"][0]))
    dropped = broken["items"].pop(1)
    score = metrics.score(broken, snapshot, metrics.ground_truth(snapshot, cases))
    assert dropped["message_id"] in score["missing_ids"]
    assert score["duplicated_ids"] == [broken["items"][0]["message_id"]]


def test_wrong_label_lowers_accuracy(snapshot, cases, perfect_result):
    broken = copy.deepcopy(perfect_result)
    target = broken["items"][0]
    target["category"] = "notice" if target["category"] != "notice" else "discussion"
    score = metrics.score(broken, snapshot, metrics.ground_truth(snapshot, cases))
    assert score["accuracy"] < 1.0
    assert score["wrong"][0]["message_id"] == target["message_id"]


def test_failed_run_scores_zero_not_crash(snapshot, cases):
    """실패도 실험 결과다. 채점기가 죽으면 실행 전체가 날아간다."""
    score = metrics.score(None, snapshot, metrics.ground_truth(snapshot, cases))
    assert score["coverage"] == 0.0
    assert score["accuracy"] is None
    assert score["counts_consistent"] is False


def test_self_consistency_detects_flapping():
    stable = [{"labels": {"m1": "notice", "m2": "important"}}] * 3
    assert metrics.self_consistency(stable) == 1.0

    flapping = [
        {"labels": {"m1": "notice"}},
        {"labels": {"m1": "important"}},
        {"labels": {"m1": "discussion"}},
    ]
    assert metrics.self_consistency(flapping) < 0.5
    assert metrics.self_consistency([{"labels": {"m1": "notice"}}]) is None
