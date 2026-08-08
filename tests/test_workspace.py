"""격리 검증 — 이 파일이 실패하면 실험 결과 전체가 무효다.

두 arm의 차이가 정확히 "skills/ 가 있느냐" 하나여야 한다. 스냅샷이 다르거나, baseline에
스킬이 새어 들어갔거나, 프롬프트의 과제문이 달라지면 무엇을 측정한 건지 알 수 없게 된다.
"""

from harness import workspace
from harness.codex import build_command
from harness.workspace import BASE_PROMPT

ALL_SKILLS = ["mail-classify", "mail-prioritize", "mail-brief"]
BASE_FILES = ["output-schema.json", "prompt.md", "snapshot.json"]


def test_snapshot_is_written_with_bom(tmp_path, snapshot):
    """BOM이 없으면 Windows PowerShell이 CP949로 읽어 한글이 깨진다.

    그러면 모델이 깨진 문자열을 evidence로 인용하고 근거 인용률이 0이 된다.
    실제로 겪은 실패라 여기서 못을 박아둔다.
    """
    info = workspace.build(tmp_path / "ws", snapshot, [])
    raw = (tmp_path / "ws" / "snapshot.json").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert info  # 빌드가 성공했다는 것도 함께 확인


def test_prompt_tells_the_model_the_encoding(snapshot, tmp_path):
    info = workspace.build(tmp_path / "ws", snapshot, [])
    assert "UTF-8" in info["prompt"]


def test_baseline_workspace_has_no_skill_files(tmp_path, snapshot):
    info = workspace.build(tmp_path / "A0", snapshot, [])
    assert info["files"] == BASE_FILES
    assert not any("skills" in f for f in info["files"])


def test_output_schema_is_given_to_both_arms(tmp_path, snapshot):
    """스키마가 작업공간 밖에 있으면 모델이 매번 찾다 실패한다. 두 arm에 똑같이 준다."""
    base = workspace.build(tmp_path / "A0", snapshot, [])
    treat = workspace.build(tmp_path / "A3", snapshot, ALL_SKILLS)
    assert "output-schema.json" in base["files"]
    assert "output-schema.json" in treat["files"]


def test_treatment_workspace_carries_every_skill(tmp_path, snapshot):
    info = workspace.build(tmp_path / "A3", snapshot, ALL_SKILLS)
    for name in ALL_SKILLS:
        assert f"skills/{name}/SKILL.md" in info["files"]
    # 참조 문서도 함께 들어가야 한다. SKILL.md만 가면 판정 기준이 사라진다.
    assert any(f.startswith("skills/mail-classify/references/") for f in info["files"])


def test_only_difference_is_the_skills_directory(tmp_path, snapshot):
    base = workspace.build(tmp_path / "A0", snapshot, [])
    treat = workspace.build(tmp_path / "A3", snapshot, ALL_SKILLS)

    # 스냅샷은 바이트 단위로 동일해야 한다.
    assert base["snapshot_sha"] == treat["snapshot_sha"]

    # 과제문은 공유하고, 스킬 arm에만 문단이 덧붙는다.
    assert base["prompt"] == BASE_PROMPT
    assert treat["prompt"].startswith(BASE_PROMPT)

    extra = set(treat["files"]) - set(base["files"])
    assert extra and all(f.startswith("skills/") for f in extra)
    assert set(base["files"]) - set(treat["files"]) == set()


def test_rebuild_does_not_leave_stale_skills(tmp_path, snapshot):
    """같은 경로를 재사용할 때 이전 arm의 스킬이 남으면 조용히 오염된다."""
    target = tmp_path / "ws"
    workspace.build(target, snapshot, ALL_SKILLS)
    info = workspace.build(target, snapshot, [])
    assert info["files"] == BASE_FILES


def test_command_isolates_from_user_config(tmp_path):
    """전역 ~/.codex 설정과 전역 스킬이 새어 들면 baseline이 baseline이 아니게 된다."""
    command = build_command(tmp_path, tmp_path / "s.json", tmp_path / "o.json")
    assert "--ignore-user-config" in command
    assert "--sandbox" in command and "read-only" in command
    assert "--output-schema" in command


def test_command_is_identical_except_workspace(tmp_path):
    """모델·effort·스키마가 arm마다 달라지면 무엇 때문에 차이가 났는지 알 수 없다."""
    schema, out = tmp_path / "s.json", tmp_path / "o.json"
    a = build_command(tmp_path / "A0", schema, out)
    b = build_command(tmp_path / "A3", schema, out)
    strip = lambda cmd: [c for c in cmd if "A0" not in c and "A3" not in c]  # noqa: E731
    assert strip(a) == strip(b)
