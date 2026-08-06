# office-blue

## 개발 구조

처음 참여하는 사람은 [화면 개발 안내](docs/architecture/README.md)부터 읽는다. 개발자는
필요할 때 아래 상세 문서를 함께 확인한다.

- [프런트엔드 아키텍처](docs/architecture/frontend-architecture.md)
- [화면 및 라우트 구성](docs/architecture/screen-route-map.md)
- [역할과 협업 방식](docs/architecture/feature-ownership.md)
- [디자인 시스템](docs/design-system/README.md)

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
