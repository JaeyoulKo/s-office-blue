# Gmail MCP 연결 문제 해결

## 가장 먼저 확인할 증상

다음 오류는 Gmail API 조회 실패가 아니라 MCP 전송 단계에서 인증 정보가 전달되지
않았다는 뜻이다.

```text
tool call failed for `gmail/list_labels`
Transport send error: Auth required
```

2026-08-06의 `feat/gmail-mcp-integration` 검증에서는 OAuth를 재연결한 뒤에도
직접 등록된 `gmail/list_labels` 호출에서 같은 오류가 재현됐다. 반면 같은 세션에서
OpenAI Gmail 커넥터의 `mcp__codex_apps__gmail_list_labels` 호출은 성공했다.

## 원인: 이름이 비슷한 두 연결 경로

| 경로 | 설정 위치 | 인증 | 새 컴퓨터로 자동 이전 |
| --- | --- | --- | --- |
| `mcp__codex_apps__gmail_*` | OpenAI Gmail 커넥터 | 커넥터 OAuth | 보장되지 않음. 동일 계정 로그인 후 활성화와 OAuth 상태를 확인해야 함 |
| `mcp__gmail__*` | 보통 `~/.codex/config.toml`의 `mcp_servers.gmail` | 해당 MCP 서버가 요구하는 별도 인증 | 아니요. 로컬 전역 설정임 |

OpenAI Gmail 커넥터에서 OAuth를 완료해도 직접 등록한 Gmail MCP 서버에 그 토큰이
전달되는 것은 아니다. 두 경로가 동시에 노출되면 이름만 보고 잘못된 도구를 호출할
수 있다.

## 새 환경의 안전한 확인 순서

1. 동일한 OpenAI 계정으로 Codex에 로그인한다.
2. Codex에서 Gmail 커넥터가 활성화되어 있고 원하는 Gmail 계정으로 OAuth 연결되어
   있는지 확인한다.
3. 프로젝트나 메일 작업을 시작하기 전에 메일 본문을 읽지 않는 최소 테스트로
   `mcp__codex_apps__gmail_list_labels`만 호출한다.
4. 라벨 조회가 성공한 뒤에만 검색, 메시지, 스레드, 첨부파일 조회를 진행한다.
5. 검색·조회 도구가 지원한다면 `METADATA_ONLY` 또는 ID 전용 검색을 우선한다.
6. 초안, 발송, 라벨 변경, 보관, 삭제 같은 쓰기 도구는 작업자가 명시적으로 요청하지
   않는 한 호출하지 않는다.

## `Auth required`가 발생할 때

먼저 어떤 경로가 실패했는지 확인한다.

```bash
codex mcp list
codex mcp get gmail
```

다음과 비슷하게 표시되면 직접 등록된 전역 MCP 서버를 보고 있는 것이다.

```text
gmail  https://gmailmcp.googleapis.com/mcp/v1  enabled  Unsupported
```

이 경우 OpenAI Gmail 커넥터 OAuth를 반복해서 재연결해도 직접 등록 서버의 인증은
고쳐지지 않는다. 우선 `mcp__codex_apps__gmail_*` 경로로 라벨 조회를 다시 테스트한다.

직접 등록된 서버가 함께 보이더라도 이 프로젝트의 연결 검증을 위해 제거하거나 전역
설정을 수정하지 않는다. `~/.codex/config.toml`의 Gmail MCP 등록을 변경하면 다른
프로젝트와 Codex 세션에도 영향을 줄 수 있다. 이 프로젝트에서는 전역 설정을 그대로
둔 채 `mcp__codex_apps__gmail_*` 커넥터 경로를 명시적으로 사용한다.

## 검증 결과 기록 기준

연결 검증 시 다음을 함께 기록한다.

- 사용한 도구의 전체 네임스페이스
- 라벨, 검색, 개별 메시지, 스레드, 첨부파일 단계별 성공 여부
- `METADATA_ONLY` 지원 여부와 실제 본문 접근 여부
- 쓰기 도구 호출 여부
- 오류 원문과 발생 단계

OAuth 토큰, 메시지 ID, 첨부파일 ID, 메일 본문 등 민감한 값은 Git에 커밋하지 않는다.

## 2026-08-06 확인 결과

- `mcp__gmail__list_labels`: `Transport send error: Auth required`
- `mcp__codex_apps__gmail_list_labels`: 성공
- ID 전용 이메일 검색: 성공
- 개별 메시지 조회: 성공
- 스레드 조회: 성공
- 첨부파일 대상 검색: 성공했으나 대상 메시지가 없어 실제 파일 조회는 미검증
- Gmail 쓰기 호출: 없음
- 전역 Codex 설정 변경: 없음
