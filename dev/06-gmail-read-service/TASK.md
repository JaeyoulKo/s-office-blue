# 06 · Gmail 읽기 서비스

- 목적: 연결된 OpenAI Gmail connector로 받은편지함을 읽기 전용 조회한다.
- 작업 위치: `dev/06-gmail-read-service/work/`
- 입력: Gmail 검색어와 최대 조회 개수
- 승격 대상: `main_service/gmail_reader.py`, Gmail 출력 Schema
- 완료: `codex exec`가 Gmail 읽기 도구만 사용하고 원문이나 provider ID를 Git에 저장하지 않는다.
