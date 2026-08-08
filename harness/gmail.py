"""메일 수집 → 스냅샷 정규화. 어댑터 3종.

수집과 분석을 분리하는 것이 이 설계의 핵심이다.

    [1회] 수집 → snapshot.json (동결) → [N회] 분석 ×arm → 비교
          MCP 필요                       MCP 불필요, 파일 in / JSON out

분석이 Gmail에 접속하지 않으므로 재현 가능하고, 오프라인이며, 메일함 상태가 바뀌어도
결과가 오염되지 않는다. Gmail 경로가 아직 안 정해졌어도 fixture로 전 과정을 돌릴 수 있다.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import RUNS_DIR, contracts
from .codex import codex_bin

KST = timezone(timedelta(hours=9))
ADAPTERS = ("fixture", "connector", "local-mcp")

# 실험용 주입 메일에 실어 보내는 케이스 표식. 모델이 정답을 훔쳐보지 못하도록
# 스냅샷을 만들기 전에 지운다. 매핑은 experiments/ 쪽이 따로 들고 있다.
_SEED_HEADER = re.compile(r"^X-OfficeBlue-[^\n]*\n?", re.MULTILINE)

_COLLECT_PROMPT = """\
연결된 Gmail 도구의 **읽기 전용** 기능만 사용해서 수신함을 조회해라.
발송·초안 생성·라벨 변경·삭제·보관을 하지 않는다.

검색 조건: {query}
최대 {max_results}건.

각 메일에서 message_id, thread_id, from, to, subject, date(ISO8601), body(평문),
attachments(파일명·MIME·크기 메타데이터만), labels 를 수집한다.
본문을 요약하거나 편집하지 말고 원문 그대로 넣는다.

최종 응답은 주어진 출력 스키마를 만족하는 JSON 객체 하나만 출력한다.
snapshot_id 는 "{snapshot_id}", adapter 는 "{adapter}", query 는 "{query}" 로 채운다.
"""


def new_snapshot_id() -> str:
    return datetime.now(KST).strftime("%Y%m%d-%H%M%S")


def _clean(text: str) -> str:
    return _SEED_HEADER.sub("", text or "").strip()


def normalize(snapshot: dict) -> dict:
    """어떤 어댑터에서 왔든 계약에 맞는 모양으로 다듬는다."""
    for message in snapshot.get("messages", []):
        message["subject"] = _clean(message.get("subject", ""))
        message["body"] = _clean(message.get("body", ""))
        message.setdefault("attachments", [])
        message.setdefault("labels", [])
        for key in ("to", "from", "thread_id"):
            message.setdefault(key, "")
    return snapshot


# ------------------------------------------------------------------ fixture


def from_cases(cases_path: Path, snapshot_id: str | None = None, max_results: int = 50) -> dict:
    """Gmail을 쓰지 않고 experiments/cases.yaml 에서 스냅샷을 만든다.

    정답 라벨(`expected`)은 스냅샷에 넣지 않는다. 모델은 정답을 볼 수 없고,
    채점기만 케이스 파일에서 따로 읽는다.
    """
    import yaml

    cases = yaml.safe_load(cases_path.read_text(encoding="utf-8")) or []
    messages = []
    for case in cases[:max_results]:
        messages.append({
            "message_id": f"msg-{case['id']}",
            "thread_id": case.get("thread_id") or f"thr-{case['id']}",
            "from": case.get("from", ""),
            "to": case.get("to", "me@example.com"),
            "subject": case.get("subject", ""),
            "date": case.get("date", ""),
            "body": case.get("body", ""),
            "attachments": case.get("attachments", []),
            "labels": case.get("labels", ["INBOX", "UNREAD"]),
        })
    return normalize({
        "snapshot_id": snapshot_id or new_snapshot_id(),
        "collected_at": datetime.now(KST).isoformat(),
        "adapter": "fixture",
        "query": str(cases_path).replace("\\", "/"),
        "messages": messages,
    })


# ------------------------------------------------- connector / local-mcp


def from_gmail(
    adapter: str,
    query: str = "in:inbox is:unread newer_than:7d",
    max_results: int = 50,
    snapshot_id: str | None = None,
    timeout: int = 600,
) -> dict:
    """Codex를 통해 Gmail MCP로 읽는다.

    분석 단계와 달리 여기서는 `--ignore-user-config`를 쓰지 않는다. MCP 서버 설정이
    사용자 config에 있기 때문이다. 대신 `--sandbox read-only`로 쓰기를 막는다.
    """
    if adapter not in ("connector", "local-mcp"):
        raise ValueError(f"Gmail 어댑터가 아닙니다: {adapter}")

    snapshot_id = snapshot_id or new_snapshot_id()
    out_path = RUNS_DIR / f".collect-{snapshot_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        codex_bin(), "exec",
        "--ephemeral",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--output-schema", str(contracts.path_of(contracts.SNAPSHOT)),
        "--output-last-message", str(out_path),
        "--color", "never",
        "-",
    ]
    prompt = _COLLECT_PROMPT.format(
        query=query, max_results=max_results, snapshot_id=snapshot_id, adapter=adapter
    )
    subprocess.run(command, input=prompt, text=True, encoding="utf-8", timeout=timeout, check=False)

    if not out_path.exists():
        raise RuntimeError(
            "Gmail 수집이 결과를 내지 못했습니다. `codex mcp list`로 인증 상태를 먼저 확인하세요 "
            "(docs/setup.md 참고)."
        )
    snapshot = json.loads(out_path.read_text(encoding="utf-8"))
    out_path.unlink(missing_ok=True)
    return normalize(snapshot)


# ------------------------------------------------------------------ 공통


def collect(adapter: str, cases_path: Path | None = None, **kwargs) -> dict:
    if adapter == "fixture":
        if cases_path is None:
            raise ValueError("fixture 어댑터에는 cases_path가 필요합니다.")
        return from_cases(cases_path, kwargs.get("snapshot_id"), kwargs.get("max_results", 50))
    return from_gmail(adapter, **kwargs)


def save(snapshot: dict) -> Path:
    """스냅샷을 run 디렉터리에 동결한다. 이후 모든 arm이 이 파일을 본다."""
    run_dir = RUNS_DIR / snapshot["snapshot_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_dir


def load(run_dir: Path) -> dict:
    return json.loads((run_dir / "snapshot.json").read_text(encoding="utf-8"))


def list_runs() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(
        (p for p in RUNS_DIR.iterdir() if p.is_dir() and (p / "snapshot.json").exists()),
        reverse=True,
    )
