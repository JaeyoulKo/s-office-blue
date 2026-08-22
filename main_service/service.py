from __future__ import annotations

import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Sequence

from .archive_result import (
    ARCHIVE_FORMAT_ERROR_MESSAGE,
    ArchiveResultFormatError,
    archive_output_contract,
    normalize_archive_result,
)
from .codex_runner import CodexResult, CodexRunError, codex_version, run_codex
from .emails import for_codex, normalize_email
from .gmail_mcp import DEFAULT_QUERY as GMAIL_DEFAULT_QUERY
from .gmail_mcp import fetch_messages
from .replies import can_reply, extract_draft, reply_route, supported_labels
from .skill_registry import PROJECT_ROOT

# 이메일 1건당 codex 프로세스 1개가 뜬다. 30건 기준 실측(gpt-5.4, priority, 실패 0건):
#
#   워커  4 → 194.5s (건당 23.8s)
#   워커  8 →  97.7s (건당 23.7s)   동시성을 2배로 올려도 건당 시간이 그대로다
#   워커 16 →  56.6s (건당 26.4s)   가장 빠름
#   워커 30 →  58.6s (건당 49.4s)   전체 소요가 오히려 나빠지고 건당은 2배
#
# 16이 포화 지점이다. 그 위로는 프로세스가 서로를 느리게 만들 뿐 총 처리량이 늘지 않으므로
# 상한을 16에 둔다. "메일 수만큼" 띄우는 건 30건에서 이미 손해다.
DEFAULT_MAX_WORKERS = 16
MAX_PARALLEL = 16
CLASSIFY_TIMEOUT_SECONDS = 120
# 회신 초안은 분류보다 훨씬 무겁다. 구매 검토는 네 항목 판정에 이전 계약 조회까지 한다.
REPLY_TIMEOUT_SECONDS = 240
CLASSIFY_REASONING_EFFORT = "low"
CLASSIFY_SERVICE_TIER = "priority"
ARCHIVE_MAX_WORKERS = 3

# 다시 시도해서 결과가 달라질 수 있는 실패만 재시도한다. CLI가 없는데 다시 보내봐야
# 같은 속도로 N번 더 실패할 뿐이다.
RETRYABLE_KINDS = frozenset({"timeout", "exit", "no_output"})

CLASSIFY_PROMPT = (
    "input.json의 이메일을 제공된 국문 taxonomy로 분류하고 "
    "분류 근거와 다음 단계를 JSON으로 반환하세요. "
    "함께 `urgency` 필드에 `high`, `medium`, `low` 중 하나를 담아 "
    "이 메일을 얼마나 먼저 처리해야 하는지 판단하세요."
)


def _taxonomy() -> str:
    return (PROJECT_ROOT / "shared" / "taxonomy.md").read_text(encoding="utf-8")


def codex_available() -> bool:
    """배치를 시작하기 전에 확인한다. 없으면 30건이 똑같은 이유로 실패한다."""
    return codex_version() != "unavailable"


def fetch_inbox(
    query: str = GMAIL_DEFAULT_QUERY, *, max_results: int = 50
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Gmail에서 읽기 전용 스냅샷을 가져와 목록 화면이 쓰는 형태로 정규화한다.

    조회는 로컬 MCP 서버를 직접 부른다. 목록을 가져오는 데는 판단이 없어서 모델을 끼울
    이유가 없고, 끼우면 느리고 조용히 빈 목록이 나올 수 있다.

    UI가 MCP를 직접 부르지 않도록 여기서 감싼다 (AGENTS.md: UI는 service.py만 호출한다).
    읽기 전용이고 발송·라벨 변경·삭제는 하지 않는다.

    `(inbox, errors)`를 돌려준다. 도구를 못 쓴 경우에도 빈 목록이 나오므로, 그냥 0건인지
    조회가 깨진 건지 UI가 구분해서 말할 수 있어야 한다.
    """
    messages, errors = fetch_messages(query, max_results=max_results)
    inbox: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, message in enumerate(messages):
        email = normalize_email(message)
        case_id = email["case_id"]
        if case_id in seen:
            seen[case_id] += 1
            email["case_id"] = f"{case_id}#{seen[case_id]}"
        else:
            seen[case_id] = 0
        email["index"] = index
        inbox.append(email)
    return inbox, errors


def classify_email(
    email: dict[str, Any],
    model: str | None = None,
    *,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: int = 300,
) -> CodexResult:
    return run_codex(
        prompt=CLASSIFY_PROMPT,
        payload={"email": for_codex(email), "taxonomy": _taxonomy()},
        skill="email-classifier",
        model=model,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        timeout_seconds=timeout_seconds,
    )


def _classify_one(
    email: dict[str, Any],
    index: int,
    *,
    model: str | None,
    reasoning_effort: str | None,
    service_tier: str | None,
    timeout_seconds: int,
    retries: int,
) -> dict[str, Any]:
    """이메일 1건을 분류한다. 절대 예외를 올리지 않는다.

    한 건의 실패가 배치를 죽이면 29건의 성공이 함께 버려진다. 실패는 결과 레코드가 된다.
    재시도 대기도 여기(워커 스레드)에서 한다 — 메인 스레드를 재우면 UI가 멈춘다.
    """
    started = time.perf_counter()
    case_id = str(email.get("case_id") or email.get("message_id") or index)
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            result = classify_email(
                email,
                model,
                reasoning_effort=reasoning_effort,
                service_tier=service_tier,
                timeout_seconds=timeout_seconds,
            )
        except CodexRunError as exc:
            last_error = str(exc)
            if getattr(exc, "kind", "unknown") not in RETRYABLE_KINDS or attempt > retries:
                break
            time.sleep(2 + random.random() * 2)
        except Exception as exc:  # noqa: BLE001 - 배치는 어떤 이유로도 멈추지 않는다
            last_error = f"{type(exc).__name__}: {exc}"
            break
        else:
            parsed = result.parsed if isinstance(result.parsed, dict) else None
            return {
                "case_id": case_id,
                "index": index,
                "status": "ok" if parsed else "error",
                "classification": parsed,
                "text": result.text,
                "error": None if parsed else "JSON 객체로 해석할 수 없는 응답입니다.",
                "attempts": attempt,
                "elapsed_seconds": round(time.perf_counter() - started, 1),
            }
    return {
        "case_id": case_id,
        "index": index,
        "status": "error",
        "classification": None,
        "text": "",
        "error": last_error or "알 수 없는 실패",
        "attempts": attempt,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }


def classify_emails(
    emails: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    reasoning_effort: str | None = CLASSIFY_REASONING_EFFORT,
    service_tier: str | None = CLASSIFY_SERVICE_TIER,
    timeout_seconds: int = CLASSIFY_TIMEOUT_SECONDS,
    retries: int = 1,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """이메일 여러 건을 동시에 분류한다.

    `run_codex`는 호출마다 자기 임시 워크스페이스를 쓰고 공유 상태가 없어서 스레드에서
    안전하다. 실제 작업은 서브프로세스 대기라 GIL도 문제가 되지 않는다.

    `on_event`는 **호출자 스레드에서만** 실행된다. Streamlit 워커 스레드에는
    ScriptRunContext가 없어 `st.*` 호출이 깨지므로, 진행 표시를 그리는 콜백은
    반드시 메인 스레드에서 돌아야 한다.

    반환은 완료 순서가 아니라 **입력 순서**다. 그래야 같은 입력이 같은 목록이 된다.
    """
    if not emails:
        return []

    workers = max(1, min(max_workers, MAX_PARALLEL, len(emails)))
    total = len(emails)
    results: list[dict[str, Any] | None] = [None] * total
    started = time.perf_counter()

    def emit(**event: Any) -> None:
        if on_event is None:
            return
        on_event({"total": total, "workers": workers,
                  "elapsed_seconds": time.perf_counter() - started, **event})

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="classify")
    try:
        futures = [
            executor.submit(
                _classify_one,
                email,
                index,
                model=model,
                reasoning_effort=reasoning_effort,
                service_tier=service_tier,
                timeout_seconds=timeout_seconds,
                retries=retries,
            )
            for index, email in enumerate(emails)
        ]
        emit(state="submitted", done=0, failed=0)
        done = failed = 0
        for future in as_completed(futures):
            record = future.result()  # _classify_one은 예외를 올리지 않는다
            results[record["index"]] = record
            done += 1
            failed += record["status"] == "error"
            emit(state=record["status"], done=done, failed=failed, record=record)
    finally:
        # `with` 블록은 __exit__에서 shutdown(wait=True)를 부른다. 진행 중 Streamlit이
        # rerun을 던지면 서브프로세스 전부를 timeout만큼 기다리며 UI가 멈춘다.
        executor.shutdown(wait=False, cancel_futures=True)

    return [record for record in results if record is not None]


def draft_reply(
    email: dict[str, Any],
    classification: Any,
    *,
    model: str | None = None,
    timeout_seconds: int = REPLY_TIMEOUT_SECONDS,
    service_tier: str | None = CLASSIFY_SERVICE_TIER,
) -> dict[str, Any]:
    """분류 라벨에 맞는 Skill로 회신 초안을 만든다.

    어떤 Skill을 쓸지는 `replies.REPLY_ROUTES`가 정한다. 지원하지 않는 라벨이면 빈 초안을
    지어내지 않고 그대로 거절한다.
    """
    label = ""
    if isinstance(classification, dict):
        label = str(classification.get("label") or "")
    route = reply_route(label)
    if route is None:
        raise ValueError(f"회신 초안을 지원하지 않는 분류입니다: {label or '미분류'}")

    result = run_codex(
        prompt=route.prompt,
        payload={"email": for_codex(email), "classification": classification},
        skill=route.skill,
        model=model,
        reasoning_effort=CLASSIFY_REASONING_EFFORT,
        service_tier=service_tier,
        timeout_seconds=timeout_seconds,
    )
    output = result.parsed if isinstance(result.parsed, dict) else None
    return {
        "label": label,
        "skill": route.skill,
        "action": route.action,
        "review": output,
        "draft": extract_draft(route, output),
        "text": result.text,
    }


def draft_replies(
    targets: Sequence[tuple[dict[str, Any], Any]],
    *,
    model: str | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    timeout_seconds: int = REPLY_TIMEOUT_SECONDS,
    service_tier: str | None = CLASSIFY_SERVICE_TIER,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """선택한 메일들의 회신 초안을 동시에 만든다.

    `classify_emails`와 같은 규약이다 — 입력 순서로 반환하고, 개별 실패는 레코드가 되며,
    `on_event`는 호출자 스레드에서만 실행된다.
    """
    if not targets:
        return []

    workers = max(1, min(max_workers, MAX_PARALLEL, len(targets)))
    total = len(targets)
    results: list[dict[str, Any] | None] = [None] * total
    started = time.perf_counter()

    def emit(**event: Any) -> None:
        if on_event is None:
            return
        on_event({"total": total, "workers": workers,
                  "elapsed_seconds": time.perf_counter() - started, **event})

    def one(email: dict[str, Any], classification: Any, index: int) -> dict[str, Any]:
        case_id = str(email.get("case_id") or index)
        began = time.perf_counter()
        try:
            record = draft_reply(
                email, classification, model=model,
                timeout_seconds=timeout_seconds, service_tier=service_tier,
            )
        except Exception as exc:  # noqa: BLE001 - 한 건이 배치를 멈추지 않는다
            return {"case_id": case_id, "index": index, "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_seconds": round(time.perf_counter() - began, 1)}
        return {**record, "case_id": case_id, "index": index, "status": "ok",
                "error": None, "elapsed_seconds": round(time.perf_counter() - began, 1)}

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="reply")
    try:
        futures = [
            executor.submit(one, email, classification, index)
            for index, (email, classification) in enumerate(targets)
        ]
        emit(state="submitted", done=0, failed=0)
        done = failed = 0
        for future in as_completed(futures):
            record = future.result()
            results[record["index"]] = record
            done += 1
            failed += record["status"] == "error"
            emit(state=record["status"], done=done, failed=failed, record=record)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return [record for record in results if record is not None]


def review_purchase_email(
    email: dict[str, Any], classification: Any, model: str | None = None
) -> CodexResult:
    return run_codex(
        prompt=(
            "input.json의 구매·승인·계약 이메일을 검토하세요. 필요한 경우 Skill의 국문 "
            "템플릿으로 회신 초안을 포함하고 외부 작업은 하지 마세요."
        ),
        payload={"email": for_codex(email), "classification": classification},
        skill="purchase-email-review",
        model=model,
    )


def review_discussion_email(
    email: dict[str, Any], classification: Any, model: str | None = None
) -> CodexResult:
    return run_codex(
        prompt=(
            "input.json의 논의·질의 이메일과 스레드를 검토하세요. 결정, 미결 사항, 담당자, "
            "기한을 구분하고 필요한 경우 국문 회신 초안을 포함하세요."
        ),
        payload={"email": for_codex(email), "classification": classification},
        skill="discussion-email-review",
        model=model,
    )


def archive_discussion_email(
    email: dict[str, Any], classification: Any, model: str | None = None
) -> CodexResult:
    """선택한 이메일 Thread를 승인된 Email Archive Agent로 정리한다."""
    result = run_codex(
        prompt=(
            "input.json의 email에 있는 최신 메시지와 thread의 이전 메시지를 합쳐 전체 이메일 "
            "스레드를 시간순으로 복원하세요. Email Archive Agent의 회사 규칙과 "
            "references/output-schema.md를 적용하고 외부 저장은 수행하지 마세요. "
            + archive_output_contract()
        ),
        payload={"email": for_codex(email), "classification": classification},
        skill="email-archive-agent",
        model=model,
    )
    canonical = normalize_archive_result(result.parsed, email)
    return CodexResult(text=result.text, parsed=canonical)


def archive_discussion_emails(
    targets: Sequence[tuple[dict[str, Any], Any]],
    *,
    model: str | None = None,
    max_workers: int = ARCHIVE_MAX_WORKERS,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """선택한 Thread를 최대 3개씩 독립 분석하고 선택 순서로 반환한다."""
    if not targets:
        return []
    workers = max(1, min(max_workers, ARCHIVE_MAX_WORKERS, len(targets)))
    total = len(targets)
    results: list[dict[str, Any] | None] = [None] * total

    def one(email: dict[str, Any], classification: Any, index: int) -> dict[str, Any]:
        case_id = str(email.get("case_id") or email.get("message_id") or index)
        run_id = uuid.uuid4().hex
        if on_event is not None:
            on_event(
                {
                    "state": "running",
                    "total": total,
                    "record": {
                        "case_id": case_id,
                        "index": index,
                        "run_id": run_id,
                        "status": "running",
                    },
                }
            )
        try:
            result = archive_discussion_email(email, classification, model)
        except ArchiveResultFormatError:
            return {
                "case_id": case_id,
                "index": index,
                "run_id": run_id,
                "status": "error",
                "email": email,
                "error": ARCHIVE_FORMAT_ERROR_MESSAGE,
            }
        except Exception as exc:  # noqa: BLE001 - 한 건의 실패가 나머지를 중단하지 않는다
            return {
                "case_id": case_id,
                "index": index,
                "run_id": run_id,
                "status": "error",
                "email": email,
                "error": f"{type(exc).__name__}: 분석에 실패했습니다.",
            }
        if not isinstance(result.parsed, dict):
            return {
                "case_id": case_id,
                "index": index,
                "run_id": run_id,
                "status": "error",
                "email": email,
                "error": "분석 결과를 구조화하지 못했습니다.",
            }
        return {
            "case_id": case_id,
            "index": index,
            "run_id": run_id,
            "status": "ok",
            "email": email,
            "result": result,
            "error": None,
        }

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="archive")
    try:
        futures = [
            executor.submit(one, email, classification, index)
            for index, (email, classification) in enumerate(targets)
        ]
        if on_event is not None:
            on_event({"state": "submitted", "total": total, "done": 0, "failed": 0})
        done = failed = 0
        for future in as_completed(futures):
            record = future.result()
            results[record["index"]] = record
            done += 1
            failed += record["status"] == "error"
            if on_event is not None:
                on_event(
                    {
                        "state": record["status"],
                        "total": total,
                        "done": done,
                        "failed": failed,
                        "record": record,
                    }
                )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return [record for record in results if record is not None]
