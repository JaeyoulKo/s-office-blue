# 08 · Gmail Streamlit UI

- 목적: 읽기 전용 Gmail 서비스를 Streamlit 받은편지함 UI에 연결한다.
- 작업 위치: `dev/08-gmail-streamlit-ui/work/`
- 입력: `main_service/service.py`의 Gmail 읽기 함수와 테스트용 Gmail 응답
- 승격 대상: `main_service/service.py`, `main_service/streamlit_app.py`, `tests/test_gmail_reader.py`
- 완료: Gmail 메시지를 새로 불러오고 선택할 수 있으며 외부 쓰기 작업을 수행하지 않는다.
