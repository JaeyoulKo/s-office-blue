"""Track B — Codex 하니스.

UI가 아는 것은 `run_arm()` 하나뿐이다. 내부가 codex exec에서 SDK나 HTTP로 바뀌어도
호출부는 바뀌지 않는다.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "contracts"
SKILLS_DIR = ROOT / "skills"
RUNS_DIR = ROOT / "experiments" / "runs"

__all__ = ["ROOT", "CONTRACTS_DIR", "SKILLS_DIR", "RUNS_DIR"]
