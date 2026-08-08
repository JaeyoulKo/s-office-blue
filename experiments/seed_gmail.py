"""실험 환경 구성 — 정답이 붙은 가짜 메일을 준비한다.

`cases.yaml`의 케이스에는 정답 라벨이 달려 있다. 그래서 "두 arm이 서로 얼마나 다른가"가
아니라 **"어느 쪽이 맞았는가"**를 잴 수 있다. 이것이 이 실험의 힘이다.

세 가지 모드:

    fixture  Gmail을 쓰지 않고 cases.yaml → 스냅샷 직접 생성   (기본, 오늘 바로 됨)
    insert   Gmail API users.messages.insert 로 메일함에 삽입   (권장, From 재현 가능)
    smtp     앱 비밀번호로 자기 자신에게 발송                    (가장 쉬움, From 재현 불가)

주의 — 최소 권한 분리:
    이 스크립트는 이 저장소에서 **유일하게 쓰기를 하는 코드**이고, 사람이 직접 실행한다.
    에이전트에게는 절대 도구로 노출하지 않으며 자격증명도 분리한다.
    에이전트의 Gmail 접근은 끝까지 읽기 전용이다. (AGENTS.md)

실행:
    python -m experiments.seed_gmail --mode fixture
    python -m experiments.seed_gmail --mode insert --label OFFICEBLUE-TEST
    python -m experiments.seed_gmail --cleanup
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import contracts, gmail  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "cases.yaml"
DEFAULT_LABEL = "OFFICEBLUE-TEST"
SCOPES = ["https://www.googleapis.com/auth/gmail.insert", "https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = Path(__file__).resolve().parent / ".seed-token.json"


def load_cases() -> list[dict]:
    import yaml

    return yaml.safe_load(CASES_PATH.read_text(encoding="utf-8")) or []


def build_message(case: dict, to_addr: str, label: str) -> EmailMessage:
    """케이스 하나를 RFC822 메일로 만든다.

    케이스 id는 X-OfficeBlue-Case 헤더에 싣는다. harness/gmail.py 의 normalize()가
    스냅샷을 만들기 전에 이 헤더를 지우므로 **모델은 정답을 볼 수 없고**, 채점기만
    cases.yaml 에서 매핑을 안다.
    """
    msg = EmailMessage()
    msg["From"] = case.get("from", "noreply@example.test")
    msg["To"] = to_addr
    msg["Subject"] = case.get("subject", "")
    msg["Date"] = case.get("date", "")
    msg["X-OfficeBlue-Case"] = case["id"]
    msg["X-OfficeBlue-Label"] = label
    msg.set_content(case.get("body", ""))
    return msg


# ------------------------------------------------------------------ fixture


def seed_fixture(max_results: int) -> Path:
    snapshot = gmail.from_cases(CASES_PATH, max_results=max_results)
    errors = contracts.validate(contracts.SNAPSHOT, snapshot)
    if errors:
        raise SystemExit("스냅샷이 계약을 위반했습니다:\n  " + "\n  ".join(errors))
    run_dir = gmail.save(snapshot)
    print(f"스냅샷 {len(snapshot['messages'])}건 생성 → {run_dir / 'snapshot.json'}")
    print(f"run-id: {snapshot['snapshot_id']}")
    return run_dir


# ------------------------------------------------------------- Gmail 쓰기


def _service():
    """쓰기 권한을 가진 Gmail 클라이언트. 에이전트가 쓰는 것과 다른 자격증명이다."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "이 모드는 추가 패키지가 필요합니다:\n"
            "  pip install google-api-python-client google-auth-oauthlib"
        ) from exc

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        secret = os.environ.get("OFFICEBLUE_SEED_CLIENT_SECRET")
        if not secret:
            raise SystemExit(
                "OAuth 클라이언트 파일 경로를 환경변수로 지정하세요:\n"
                '  $env:OFFICEBLUE_SEED_CLIENT_SECRET = "C:\\path\\client_secret.json"\n'
                "만드는 법은 docs/setup.md 를 보세요."
            )
        creds = InstalledAppFlow.from_client_secrets_file(secret, SCOPES).run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def _label_id(service, label: str) -> str:
    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    for item in existing:
        if item["name"] == label:
            return item["id"]
    created = service.users().labels().create(userId="me", body={"name": label}).execute()
    return created["id"]


def seed_insert(label: str, max_results: int) -> None:
    """발송하지 않고 메일함에 직접 삽입한다. From 헤더를 자유롭게 재현할 수 있고 스팸에 걸리지 않는다."""
    service = _service()
    to_addr = service.users().getProfile(userId="me").execute()["emailAddress"]
    label_id = _label_id(service, label)

    for case in load_cases()[:max_results]:
        raw = base64.urlsafe_b64encode(build_message(case, to_addr, label).as_bytes()).decode()
        service.users().messages().insert(
            userId="me", internalDateSource="dateHeader",
            body={"raw": raw, "labelIds": [label_id, "UNREAD", "INBOX"]},
        ).execute()
        print(f"  삽입 {case['id']}  {case.get('subject', '')[:50]}")
    print(f"\n라벨 '{label}'에 삽입 완료. 이제 수집하세요:")
    print('  python -m experiments.ablation --collect connector --query "label:%s is:unread"' % label)


def seed_smtp(label: str, max_results: int) -> None:
    """앱 비밀번호로 자기 자신에게 발송. From 재현이 안 되므로 발신인 규칙 케이스는 검증되지 않는다."""
    import smtplib

    user = os.environ.get("OFFICEBLUE_SEED_GMAIL")
    password = os.environ.get("OFFICEBLUE_SEED_APP_PASSWORD")
    if not (user and password):
        raise SystemExit(
            "환경변수를 설정하세요:\n"
            '  $env:OFFICEBLUE_SEED_GMAIL = "you@gmail.com"\n'
            '  $env:OFFICEBLUE_SEED_APP_PASSWORD = "앱 비밀번호 16자리"'
        )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, password)
        for case in load_cases()[:max_results]:
            msg = build_message(case, user, label)
            del msg["From"]
            msg["From"] = user  # SMTP는 임의 From을 허용하지 않는다
            server.send_message(msg)
            print(f"  발송 {case['id']}  {case.get('subject', '')[:50]}")
    print("\n주의: smtp 모드는 발신인이 전부 본인이라 '발신인 규칙' 케이스(C01/C11/C20)가 검증되지 않습니다.")


def cleanup(label: str) -> None:
    """주입한 메일을 회수한다. 실험이 끝나면 반드시 실행한다."""
    service = _service()
    query = f"label:{label}"
    listed = service.users().messages().list(userId="me", q=query, maxResults=500).execute()
    ids = [m["id"] for m in listed.get("messages", [])]
    if not ids:
        print(f"라벨 '{label}'에 삭제할 메일이 없습니다.")
        return
    service.users().messages().batchDelete(userId="me", body={"ids": ids}).execute()
    print(f"라벨 '{label}'의 메일 {len(ids)}건을 삭제했습니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="실험용 가짜 메일 준비")
    parser.add_argument("--mode", choices=["fixture", "insert", "smtp"], default="fixture")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="주입 대상 라벨 (insert/smtp)")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--cleanup", action="store_true", help="주입한 메일을 삭제하고 끝낸다")
    args = parser.parse_args()

    if args.cleanup:
        cleanup(args.label)
    elif args.mode == "fixture":
        seed_fixture(args.max_results)
    elif args.mode == "insert":
        seed_insert(args.label, args.max_results)
    else:
        seed_smtp(args.label, args.max_results)


if __name__ == "__main__":
    main()
