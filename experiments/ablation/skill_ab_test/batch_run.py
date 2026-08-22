from __future__ import annotations

from pathlib import Path

from .excel_export import ABResultExcelRepository
from .runner import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT, run_ab_test
from .synthetic_fixtures import load_synthetic_scenarios


SCENARIO_IDS = tuple(f"presentation_very_hard_{index:02d}" for index in range(1, 6))
EXPERIMENT_ROOT = Path(__file__).resolve().parent
RESULT_PATH = EXPERIMENT_ROOT / "results" / "email_archive_ab_results.csv"


def main() -> None:
    scenarios = {item.scenario_id: item for item in load_synthetic_scenarios()}
    missing = [scenario_id for scenario_id in SCENARIO_IDS if scenario_id not in scenarios]
    if missing:
        raise RuntimeError(f"missing presentation fixtures: {missing}")
    records = []
    for scenario_id in SCENARIO_IDS:
        scenario = scenarios[scenario_id]
        print(f"Running {scenario_id}...")
        result = run_ab_test(
            scenario.thread.to_dict(),
            model=DEFAULT_MODEL,
            reasoning_effort=DEFAULT_REASONING_EFFORT,
        )
        for condition, result_key in (("WITH_SKILL", "with_skill"), ("WITHOUT_SKILL", "without_skill")):
            records.append({
                "condition": condition,
                "source": "synthetic_fixture",
                "thread_id": scenario.thread.thread_id,
                "model": result["model"],
                "reasoning_effort": result["reasoning_effort"],
                "result": result[result_key],
            })
    ABResultExcelRepository(RESULT_PATH, EXPERIMENT_ROOT).replace_results(records)
    print(f"Saved {len(records)} rows to {RESULT_PATH.relative_to(EXPERIMENT_ROOT)}")


if __name__ == "__main__":
    main()
