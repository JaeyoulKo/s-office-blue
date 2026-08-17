from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .excel_export import EXPORT_FIELDS
from .result_schema import COMPLEX_FIELDS, RESULT_FIELDS, validate_result


EXPECTED_THREADS = tuple(f"thread-pvh{index:02d}" for index in range(1, 6))
EXPECTED_CONDITIONS = ("WITH_SKILL", "WITHOUT_SKILL")
EXPECTED_PRIMARY_RULES = {
    "thread-pvh01": {"AR-01", "AR-06"},
    "thread-pvh02": {"AR-02"},
    "thread-pvh03": {"AR-03"},
    "thread-pvh04": {"AR-04"},
    "thread-pvh05": {"AR-07", "AR-09"},
}


def validate_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPORT_FIELDS:
            raise ValueError("CSV header does not match EXPORT_FIELDS")
        rows = list(reader)
    if len(rows) != 10:
        raise ValueError(f"expected 10 A/B rows, got {len(rows)}")
    keys = [(row["thread_id"], row["condition"]) for row in rows]
    expected_keys = [(thread, condition) for thread in EXPECTED_THREADS for condition in EXPECTED_CONDITIONS]
    if keys != expected_keys or len(keys) != len(set(keys)):
        raise ValueError("rows are duplicated, missing, or not deterministically ordered")
    for row in rows:
        if row["model"] != "gpt-5.4" or row["reasoning_effort"] != "low":
            raise ValueError("model or reasoning effort differs across conditions")
        result = _deserialize_result(row)
        validate_result(result, row["thread_id"])
        rules = set(result["적용 규칙"])
        if row["condition"] == "WITH_SKILL":
            missing = EXPECTED_PRIMARY_RULES[row["thread_id"]] - rules
            if missing:
                raise ValueError(f"{row['thread_id']} is missing expected rules: {sorted(missing)}")
        elif rules:
            raise ValueError("WITHOUT_SKILL must not claim unavailable company rule IDs")
    return rows


def _deserialize_result(row: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in RESULT_FIELDS:
        value: Any = row[field]
        if field == "금액":
            value = int(value) if value else None
        elif field == "통화":
            value = value or None
        elif field in COMPLEX_FIELDS:
            value = json.loads(value)
        result[field] = value
    return result


def main() -> None:
    path = Path(__file__).resolve().parent / "results" / "email_archive_ab_results.csv"
    rows = validate_csv(path)
    print(f"Validated {len(rows)} normalized A/B rows: {path}")


if __name__ == "__main__":
    main()
