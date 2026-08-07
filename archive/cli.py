from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import FixtureArchiveAnalyzer, OpenAIArchiveAnalyzer
from .gmail_adapter import GmailAdapter, GmailUnavailableError, UnavailableGmailGateway
from .models import EmailThread, ThreadAnalysis
from .service import ArchiveService
from .storage import ExcelRecordRepository

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze an email thread and preview or write its archive record.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Normalized EmailThread JSON input.")
    source.add_argument("--gmail-thread-id", help="Gmail thread ID; requires an available Gmail gateway.")
    parser.add_argument(
        "--workbook",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "email_archive.xlsx",
        help="Repository-local archive workbook.",
    )
    parser.add_argument("--write", action="store_true", help="Explicitly approve writing the repository-local workbook.")
    parser.add_argument(
        "--analysis-fixture",
        type=Path,
        help="Offline verification only: use a precomputed ThreadAnalysis JSON instead of an LLM call.",
    )
    parser.add_argument("--model", help="OpenAI model override; otherwise OPENAI_MODEL is used.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        thread = _load_thread(args)
        analyzer = _load_analyzer(args)
        repository = ExcelRecordRepository(args.workbook, REPOSITORY_ROOT)
        result = ArchiveService(analyzer, repository).process(thread, write=args.write)
        print(result.model_dump_json(indent=2))
        return 0 if result.result_status != "additional_confirmation_required" else 2
    except (ValueError, GmailUnavailableError, FileNotFoundError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


def _load_thread(args: argparse.Namespace) -> EmailThread:
    if args.gmail_thread_id:
        return GmailAdapter(UnavailableGmailGateway()).fetch_normalized_thread(args.gmail_thread_id)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    return EmailThread.model_validate(payload)


def _load_analyzer(args: argparse.Namespace):
    if args.analysis_fixture:
        payload = json.loads(args.analysis_fixture.read_text(encoding="utf-8"))
        return FixtureArchiveAnalyzer(ThreadAnalysis.model_validate(payload))
    return OpenAIArchiveAnalyzer(model=args.model)


if __name__ == "__main__":
    raise SystemExit(main())
