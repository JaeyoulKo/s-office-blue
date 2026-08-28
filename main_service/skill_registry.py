from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / "skills"

SKILLS = {
    "email-classifier": SKILLS_ROOT / "email-classifier",
    "purchase-email-review": SKILLS_ROOT / "purchase-email-review",
    "discussion-email-review": SKILLS_ROOT / "discussion-email-review",
    "email-archive-agent": SKILLS_ROOT / "email-archive-agent",
}


def resolve_skill(name: str) -> Path:
    """승인된 Skill 폴더를 반환하고 알 수 없는 이름은 거부한다."""
    try:
        path = SKILLS[name]
    except KeyError as exc:
        raise ValueError(f"알 수 없는 Skill: {name}") from exc
    if not (path / "SKILL.md").is_file():
        raise FileNotFoundError(f"Skill 파일이 없습니다: {path}")
    return path
