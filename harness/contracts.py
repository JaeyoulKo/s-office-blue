"""contracts/ 의 JSON Schema를 읽고 검증한다. 두 트랙이 만나는 유일한 지점."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from . import CONTRACTS_DIR

SNAPSHOT = "snapshot"
TRIAGE = "triage"


def path_of(name: str):
    return CONTRACTS_DIR / f"{name}.schema.json"


@lru_cache(maxsize=8)
def load(name: str) -> dict[str, Any]:
    return json.loads(path_of(name).read_text(encoding="utf-8"))


def validate(name: str, payload: Any) -> list[str]:
    """스키마 위반 목록을 돌려준다. 빈 리스트면 통과."""
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema 미설치 — pip install -e .[dev] 를 실행하세요"]

    validator = jsonschema.Draft7Validator(load(name))
    return [
        f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(payload)
    ]
