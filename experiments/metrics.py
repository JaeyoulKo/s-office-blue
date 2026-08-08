"""지표 계산 — 사람 판단 없이 계산되는 것만 담는다.

여기 있는 지표는 전부 **객관적으로 계산되고 반박할 수 없다.** 이것이 중요하다.
"스킬을 쓰니 좋아 보인다"는 감상이지만, "없는 message_id를 3건 만들어냈다"는 사실이다.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

CATEGORIES = ("important", "ariba_approval", "discussion", "notice", "unknown")


def _flat(text: str) -> str:
    """비교용 정규화. 공백·대소문자 차이까지 오답으로 잡으면 지표가 너무 예민해진다.

    한글은 NFC로 맞춘다. 자모가 분리된 NFD로 오면 눈에는 같아 보여도 부분문자열
    비교가 실패해서, 멀쩡한 인용이 근거 없음으로 처리된다.
    """
    normalized = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", normalized).strip().lower()


def ground_truth(snapshot: dict, cases: list[dict]) -> dict[str, dict]:
    """message_id → 정답. 제목으로 맞추고, 안 되면 id 접미사로 맞춘다.

    fixture든 실제 주입 메일이든 같은 방식으로 동작한다.
    """
    by_subject = {_flat(c.get("subject", "")): c for c in cases if c.get("subject")}
    by_id = {c["id"]: c for c in cases}

    truth: dict[str, dict] = {}
    for message in snapshot.get("messages", []):
        case = by_subject.get(_flat(message.get("subject", "")))
        if case is None:
            suffix = message["message_id"].rsplit("-", 1)[-1]
            case = by_id.get(suffix)
        if case and case.get("expected"):
            truth[message["message_id"]] = case["expected"]
    return truth


def score(result: dict, snapshot: dict, truth: dict[str, dict]) -> dict[str, Any]:
    """결과 하나를 채점한다. result가 None이면 전 지표가 0/실패로 잡힌다."""
    messages = snapshot.get("messages", [])
    valid_ids = {m["message_id"] for m in messages}
    text_of = {
        m["message_id"]: _flat(m.get("subject", "") + " " + m.get("body", ""))
        for m in messages
    }

    items = (result or {}).get("items") or []
    seen = [i.get("message_id", "") for i in items]

    # 2. 환각 — 스냅샷에 없는 id를 만들어냈는가
    hallucinated = sorted({mid for mid in seen if mid not in valid_ids})

    # 5. 커버리지 — 빠짐없이 정확히 하나씩인가
    missing = sorted(valid_ids - set(seen))
    duplicated = sorted({mid for mid, n in Counter(seen).items() if n > 1})

    # 3. 근거 인용률 — evidence가 원문에서 잘라낸 것인가
    quotable = [i for i in items if i.get("message_id") in valid_ids]
    cited = [
        i for i in quotable
        if (ev := _flat(i.get("evidence", ""))) and ev in text_of.get(i["message_id"], "")
    ]

    # 1. 정확도 — 정답 라벨 대비
    graded = [i for i in quotable if i["message_id"] in truth]
    wrong = [i for i in graded if i.get("category") != truth[i["message_id"]].get("category")]

    # 7. 우선순위 규칙 준수 — 먼저 봐야 할 것이 top_items에 들어왔는가
    briefing = (result or {}).get("briefing") or {}
    top_ids = [t.get("message_id") for t in briefing.get("top_items") or []]
    must_top = {mid for mid, exp in truth.items() if exp.get("priority_top")}
    top_hit = must_top & set(top_ids)

    # counts 합계가 실제 메일 수와 맞는가
    counts = briefing.get("counts") or {}
    counts_sum = sum(v for v in counts.values() if isinstance(v, int))

    return {
        "accuracy": _ratio(len(graded) - len(wrong), len(graded)),
        "hallucinated_ids": hallucinated,
        "hallucination_free": not hallucinated,
        "evidence_rate": _ratio(len(cited), len(quotable)),
        "coverage": _ratio(len(valid_ids) - len(missing), len(valid_ids)),
        "missing_ids": missing,
        "duplicated_ids": duplicated,
        "priority_recall": _ratio(len(top_hit), len(must_top)),
        "counts_consistent": counts_sum == len(messages),
        "graded_n": len(graded),
        "labels": {i["message_id"]: i.get("category") for i in quotable},
        "wrong": [
            {
                "message_id": i["message_id"],
                "got": i.get("category"),
                "expected": truth[i["message_id"]].get("category"),
            }
            for i in wrong
        ],
    }


def _ratio(hit: int, total: int) -> float | None:
    return None if total == 0 else round(hit / total, 3)


def self_consistency(scores: list[dict]) -> float | None:
    """같은 arm을 여러 번 돌렸을 때 라벨이 얼마나 흔들리지 않는가.

    메일마다 최빈 라벨이 차지하는 비율의 평균. 1.0이면 매번 같은 답.
    """
    if len(scores) < 2:
        return None
    per_message: dict[str, list[str]] = {}
    for s in scores:
        for mid, label in (s.get("labels") or {}).items():
            per_message.setdefault(mid, []).append(label)
    stable = [
        Counter(labels).most_common(1)[0][1] / len(labels)
        for labels in per_message.values() if labels
    ]
    return round(sum(stable) / len(stable), 3) if stable else None


def aggregate(outcomes: list[dict], scores: list[dict]) -> dict[str, Any]:
    """한 arm의 반복 실행을 하나의 숫자 묶음으로 접는다."""
    ok = [o for o in outcomes if o["ok"]]
    return {
        "reps": len(outcomes),
        "schema_pass": f"{len(ok)}/{len(outcomes)}",
        "accuracy": _mean(s["accuracy"] for s in scores),
        "evidence_rate": _mean(s["evidence_rate"] for s in scores),
        "coverage": _mean(s["coverage"] for s in scores),
        "priority_recall": _mean(s["priority_recall"] for s in scores),
        "hallucinated_total": sum(len(s["hallucinated_ids"]) for s in scores),
        "counts_consistent": f"{sum(1 for s in scores if s['counts_consistent'])}/{len(scores)}",
        "self_consistency": self_consistency(scores),
        "elapsed_median": _median([o["elapsed_sec"] for o in outcomes]),
        "output_tokens": sum(o.get("usage", {}).get("output_tokens", 0) for o in outcomes) or None,
    }


def _mean(values) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return round(sum(nums) / len(nums), 3) if nums else None


def _median(values: list[float]) -> float | None:
    nums = sorted(v for v in values if isinstance(v, (int, float)))
    if not nums:
        return None
    mid = len(nums) // 2
    return nums[mid] if len(nums) % 2 else round((nums[mid - 1] + nums[mid]) / 2, 2)
