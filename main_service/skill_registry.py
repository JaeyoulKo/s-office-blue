from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / "skills"

SKILLS = {
    "email-classifier": SKILLS_ROOT / "email-classifier",
    "purchase-email-review": SKILLS_ROOT / "purchase-email-review",
    "clarification-draft": SKILLS_ROOT / "clarification-draft",
}


def resolve_skill(name: str) -> Path:
    """Return an approved Skill folder and reject unknown names."""
    try:
        path = SKILLS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown Skill: {name}") from exc
    if not (path / "SKILL.md").is_file():
        raise FileNotFoundError(f"Missing Skill: {path}")
    return path
