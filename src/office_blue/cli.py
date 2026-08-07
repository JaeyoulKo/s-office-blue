from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import EmailMessage
from .reviewer import review_email


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review a normalized Gmail message and generate a clarification draft."
    )
    parser.add_argument("input", type=Path, help="UTF-8 JSON file containing one normalized email")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        result = review_email(EmailMessage.from_dict(data))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

