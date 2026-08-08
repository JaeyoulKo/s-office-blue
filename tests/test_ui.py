"""UI 스모크 테스트 — 화면이 예외 없이 그려지는가.

Streamlit은 버튼을 누를 때마다 스크립트를 처음부터 다시 실행한다. 그래서 조건 분기 하나만
어긋나도 빈 화면이나 빨간 에러가 뜬다. UI를 고치는 사람이 그걸 바로 알 수 있게 못을 박아둔다.

LLM을 부르지 않는다. 초 단위로 끝난다.
"""

import pytest

pytest.importorskip("streamlit", reason="pip install -e .[ui] 필요")

from streamlit.testing.v1 import AppTest  # noqa: E402

from harness import ROOT  # noqa: E402

APP = str(ROOT / "ui" / "app.py")


def _run():
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception, [str(e) for e in app.exception]
    return app


def test_app_renders_without_snapshot():
    """스냅샷이 하나도 없어도 죽지 않고 안내를 띄워야 한다."""
    app = _run()
    assert len(app.tabs) == 3


def test_app_renders_with_snapshot(tmp_path, snapshot, monkeypatch):
    """스냅샷이 있으면 ②·③ 탭이 실제 내용을 그린다."""
    import harness.gmail as gmail_mod

    monkeypatch.setattr(gmail_mod, "RUNS_DIR", tmp_path)
    gmail_mod.save(snapshot)

    app = AppTest.from_file(APP, default_timeout=60)
    app.session_state["run_dir"] = str(tmp_path / snapshot["snapshot_id"])
    app.run()
    assert not app.exception, [str(e) for e in app.exception]


def test_ui_only_calls_the_agreed_harness_entry_point():
    """UI가 하니스 내부를 직접 쓰기 시작하면 두 트랙을 나눈 의미가 사라진다."""
    source = (ROOT / "ui" / "app.py").read_text(encoding="utf-8")
    for forbidden in ("build_command(", "workspace.build(", "subprocess", "from harness.codex import codex_bin"):
        assert forbidden not in source, f"ui/app.py 가 하니스 내부를 직접 호출한다: {forbidden}"
    assert "run_arm(" in source
