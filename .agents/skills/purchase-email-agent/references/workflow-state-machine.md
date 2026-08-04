# 구매 이메일 업무 상태 머신

이 문서는 [workflow.md](workflow.md)의 업무 흐름을 상태와 전이로 표현한다. 분류·판단·필수정보 규칙은 변경하지 않는다.

## 기본 흐름

```text
EMAIL_RECEIVED
  ↓
EMAIL_CLASSIFIED
  ├─ 공지 / 일반 업무 이메일 → BRIEFING_READY → DONE
  ├─ 분류 불가 → USER_CONFIRMATION_NEEDED → DONE
  └─ 구매 요청 / 구매 승인 요청 / 계약 관련
       ↓
PURCHASE_EMAIL
       ↓
BODY_ANALYZED
       ↓
ATTACHMENT_ANALYZED (첨부파일이 제공된 경우)
       ↓
THREAD_ANALYZED (스레드가 제공된 경우)
       ↓
VALIDATION
       ├─ 정보 부족 → CLARIFICATION_DRAFT_READY
       │              ↓
       │         WAITING_FOR_USER_APPROVAL
       │              ↓
       │   SEND_OR_EXTERNAL_UPDATE (외부 MCP 쓰기 경로, Skill은 실행하지 않음)
       │
       ├─ 과거 계약 비교 필요 → HISTORICAL_COMPARISON_NEEDED
       │                       ↓
       │                  WAITING_FOR_COMPARISON_DATA
       │                       └─ 자료 수신 시 BODY_ANALYZED로 재검토
       │
       └─ 검토 가능 / 승인 검토 가능 → REVIEW_BRIEF_READY
                                        ↓
                                   WAITING_FOR_USER_APPROVAL
                                        ↓
                                 EXTERNAL_ACTION_APPROVED
                                        ↓
                           SEND_OR_EXTERNAL_UPDATE (외부 MCP 쓰기 경로)
                                        ↓
                                      DONE
```

## 상태 정의와 전이 조건

| 상태 | 의미 | 다음 상태 | 전이 조건 |
| --- | --- | --- | --- |
| `EMAIL_RECEIVED` | 이메일 또는 사용자가 제공한 관련 자료를 수신함 | `EMAIL_CLASSIFIED` | 입력 자료 목록화 완료 |
| `EMAIL_CLASSIFIED` | 전체 문맥으로 이메일 유형을 분류함 | `BRIEFING_READY`, `USER_CONFIRMATION_NEEDED`, `PURCHASE_EMAIL` | 공지/일반, 분류 불가, 구매·승인·계약 관련 여부 |
| `PURCHASE_EMAIL` | 구매·승인·계약 관련 검토 경로에 진입함 | `BODY_ANALYZED` | 구매 관련성 확인 |
| `BODY_ANALYZED` | 본문과 메타데이터 분석 완료 | `ATTACHMENT_ANALYZED`, `THREAD_ANALYZED`, `VALIDATION` | 첨부파일·스레드 제공 여부 |
| `ATTACHMENT_ANALYZED` | 접근 가능한 첨부파일을 본문과 별도 분석함 | `THREAD_ANALYZED`, `VALIDATION` | 첨부파일 분석 완료 |
| `THREAD_ANALYZED` | 최초 요청·논의·결정·미결·담당자·기한을 요약함 | `VALIDATION` | 스레드 분석 완료 또는 스레드 미제공 |
| `VALIDATION` | 필수 정보, 기대효과, 비교 필요성, 위험을 검증함 | `CLARIFICATION_DRAFT_READY`, `HISTORICAL_COMPARISON_NEEDED`, `REVIEW_BRIEF_READY` | 검증 결과 |
| `CLARIFICATION_DRAFT_READY` | 보완 요청 이메일 초안을 준비함 | `WAITING_FOR_USER_APPROVAL` | 초안 검토 대상 확정 |
| `HISTORICAL_COMPARISON_NEEDED` | 과거 계약 비교가 필요하나 자료가 부족함 | `WAITING_FOR_COMPARISON_DATA` | 비교 자료 미제공 또는 비교 불가 |
| `WAITING_FOR_COMPARISON_DATA` | 사용자 또는 사용 가능한 읽기 MCP Tool의 비교 자료를 기다림 | `BODY_ANALYZED`, `REVIEW_BRIEF_READY` | 새 자료 수신 또는 비교 불가 결론 |
| `REVIEW_BRIEF_READY` | 검토 브리핑과 필요한 초안을 완성함 | `WAITING_FOR_USER_APPROVAL`, `DONE` | 사용자가 외부 작업을 요청했는지 여부 |
| `WAITING_FOR_USER_APPROVAL` | 초안 발송·Ariba 처리·저장 등 외부 작업의 명시적 승인 대기 | `EXTERNAL_ACTION_APPROVED`, `DONE` | 승인 또는 보류/종료 |
| `EXTERNAL_ACTION_APPROVED` | 외부 작업에 대한 사용자 명시 승인이 기록됨 | `SEND_OR_EXTERNAL_UPDATE` | 해당 쓰기 MCP Tool의 사용 가능·권한·입력 검증 |
| `SEND_OR_EXTERNAL_UPDATE` | 외부 MCP Tool이 수행할 수 있는 발송·Ariba 처리·기록 작업 | `DONE` | 제품/외부 실행 주체의 성공 또는 실패 기록 |
| `USER_CONFIRMATION_NEEDED` | 분류 또는 사람의 판단이 필요한 상태 | `DONE` 또는 재검토 상태 | 사용자 확인 또는 새 자료 수신 |
| `BRIEFING_READY` | 공지/일반 이메일의 간결한 브리핑 준비 완료 | `DONE` | 브리핑 제공 완료 |
| `DONE` | 이 Skill의 분석·초안 범위가 완료됨 | — | 종료 |

## MCP 및 Human-in-the-loop 경계

- `EMAIL_RECEIVED`부터 `REVIEW_BRIEF_READY`까지는 사용자 제공 자료 또는 읽기 전용 MCP Tool 결과만 사용한다.
- `SEND_OR_EXTERNAL_UPDATE`는 이 Skill이 실행하는 상태가 아니다. 향후 제품 또는 별도 실행 주체가 실제 쓰기 MCP Tool과 함께 처리할 수 있는 외부 상태다.
- `WAITING_FOR_USER_APPROVAL`을 건너뛰어 쓰기 MCP Tool을 호출하지 않는다. 사용자 승인이 있어도 이 Skill은 분석·권고·초안만 제공한다.
- 쓰기 MCP Tool이 없거나 권한·입력·승인이 불충분하면 `SEND_OR_EXTERNAL_UPDATE`로 전이하지 않고 `WAITING_FOR_USER_APPROVAL` 또는 `DONE`에 남긴다.
- MCP Tool 오류, 빈 결과, 권한 거부는 사실이나 성공 상태가 아니다. 필요한 자료가 없으면 `VALIDATION`의 정보 보완 또는 과거 계약 비교 경로로 되돌린다.
