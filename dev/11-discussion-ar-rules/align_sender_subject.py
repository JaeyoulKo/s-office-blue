from __future__ import annotations

import json
import re
from pathlib import Path


TARGET = Path("data/synthetic/emails/discussion-email-ar-rules/discussion-email-ar-rules.json")
PROJECTS = {
    "discussion-ar-01": "동부허브 자동분류기 구동부 교체공사",
    "discussion-ar-02": "서부센터 포장필름 안전재고 구매",
    "discussion-ar-03": "중앙공장 비전검사기 증설공사",
    "discussion-ar-04": "북부물류 재고시스템 및 스캐너 교체공사",
    "discussion-ar-05": "남부센터 냉각펌프 교체공사",
    "discussion-ar-06": "연구동 분석장비 연산모듈 설치공사",
    "discussion-ar-07": "고객상담 분석서비스 도입",
    "discussion-ar-08": "온라인 추천엔진 전체 적용",
    "discussion-ar-09": "동남권 긴급운송 용역 갱신",
    "discussion-ar-10": "제2공장 가스감지기 교체공사",
}


def display(sender: str) -> str:
    return sender.rsplit(" <", 1)[0]


def main() -> None:
    records = json.loads(TARGET.read_text())
    print("*** Begin Patch")
    print(f"*** Update File: {TARGET.resolve()}")
    for record in records:
        old_body = record["body"]
        sender = display(record["sender"])
        name = sender.split()[-1]
        body = re.sub(r"\A안녕하세요, [^.]+입니다\.", f"안녕하세요, {sender}입니다.", old_body)
        body = re.sub(r"\n[^\n ]+ 드림\.\Z", f"\n{name} 드림.", body)
        if record["message_id"].endswith("-05"):
            body = re.sub(r"\n\n[^\n]+ [^\n]+입니다\. 유관부서", f"\n\n{sender} {name}입니다. 유관부서", body, count=1)
            body = body.replace(f"{sender} {name}입니다.", f"{sender}입니다.")
        body = body.replace("교체공사을 진행", "교체공사를 진행")
        body = body.replace("증설공사을 진행", "증설공사를 진행")
        body = body.replace("설치공사을 진행", "설치공사를 진행")
        body = body.replace("안전재고 구매을 진행", "안전재고 구매를 진행")
        project = PROJECTS[record["thread_id"]]
        index = int(record["message_id"].rsplit("-", 1)[1])
        subject = f"{project} 사전 검토" if index == 1 else f"Re: {project} 사전 검토"
        if subject != record["subject"]:
            print("@@")
            print(f"-    \"subject\": {json.dumps(record['subject'], ensure_ascii=False)},")
            print(f"+    \"subject\": {json.dumps(subject, ensure_ascii=False)},")
        if body != old_body:
            print("@@")
            print(f"-    \"body\": {json.dumps(old_body, ensure_ascii=False)}")
            print(f"+    \"body\": {json.dumps(body, ensure_ascii=False)}")
    print("*** End Patch")


if __name__ == "__main__":
    main()
