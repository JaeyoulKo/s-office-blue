# office-blue

## Gmail MCP 연결을 시작하기 전에

새 Codex 환경에서 Gmail을 사용하거나 아래 오류가 발생하면 다른 작업보다 먼저
[Gmail MCP 연결 문제 해결](docs/gmail-mcp-troubleshooting.md)을 확인한다.

```text
Transport send error: Auth required
```

이 프로젝트에서 검증된 Gmail 경로는 OAuth로 연결한 OpenAI Gmail 커넥터의
`mcp__codex_apps__gmail_*` 도구다. `~/.codex/config.toml`에 직접 등록한
`mcp__gmail__*` 서버는 별도의 로컬 설정과 인증 경로이며, 커넥터 OAuth를 공유하지
않는다.

Git clone만으로 Gmail 인증이 이전되지는 않는다. 새 컴퓨터에서는 동일한 OpenAI
계정으로 로그인한 뒤 Gmail 커넥터의 활성화와 OAuth 연결을 확인하고, 메일 본문을
읽지 않는 `list_labels` 호출로 먼저 검증한다.

## Streamlit 이메일 검토 화면

구매·승인·계약 이메일의 미비 항목을 확인하고 보완 답장 초안을 만들 수 있다.
초안은 자동 발송되지 않으며 `WAITING_FOR_USER_APPROVAL` 상태에서 멈춘다.

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

브라우저에서 발신자, 제목, 본문을 입력하고 `미비 항목 검토`를 누른다. Gmail MCP로
조회한 메일도 같은 필드로 정규화해 `office_blue.review_email()`에 전달할 수 있다.

`Gmail MCP 받은편지함`에서 검색 범위를 확인하고 `Gmail 새로고침`을 누르면 인증된
Codex CLI가 Gmail 읽기 MCP를 실행한다. 별도 Gmail 토큰은 앱에 저장하지 않으며,
검색·본문 읽기 외의 발송·라벨·보관·삭제 작업은 수행하지 않는다.

테스트는 다음과 같이 실행한다.

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

