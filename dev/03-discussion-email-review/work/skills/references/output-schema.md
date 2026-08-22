# Archive 출력 스키마

## 공통 규칙

- 확인되지 않은 단일 값은 `unknown`, 반복 값은 빈 배열로 둔다.
- 날짜는 확인 가능한 경우 ISO 8601로 정규화하고 원문과 시간대를 출처에 보존한다.
- 금액은 숫자, 통화, 단위, 기간과 원문 출처를 분리한다.
- Action item, 결정, 첨부파일, 변경 이력은 반복 가능한 별도 항목으로 유지한다.
- `record_id`는 기존 시스템 값 또는 저장 성공 결과가 있을 때만 확정한다.

## A/B 분석용 정규화 결과

A/B 실험이 아래 필드를 요청하면 키 순서와 JSON 자료형을 그대로 지킨다. 분석용 단일 값에
설명 문장을 합치지 않고, 설명은 복합 필드에 둔다.

| 필드 | JSON 자료형 | 정규화 원칙 |
| --- | --- | --- |
| `thread_id` | string | 입력의 `email_thread.thread_id`를 그대로 사용 |
| `발신자` | string | 실제 최신 메시지의 `이름 <주소>` 형식을 보존 |
| `날짜` | string | 최신 메시지 날짜를 `YYYY-MM-DD`로 기록하고 시간·timezone 제거 |
| `Topic` | string | 핵심 안건을 짧은 한 문장으로 기록 |
| `금액` | integer 또는 null | 최신 유효 금액을 최소 통화 단위의 정수로 기록; 불명확하면 `null` |
| `통화` | string 또는 null | 확인된 ISO 4217 코드(`KRW`, `USD` 등); 불명확하면 `null` |
| `Business Impact` | object | `confirmed`와 `estimated` 문자열 배열을 별도로 유지 |
| `Thread 진행 중 변경된 내용` | array | `{field, from, to}` 객체 배열로 최초 유효값부터 최신값까지 기록 |
| `결정된 내용` | array | 실제 확정 근거가 있는 문자열만 기록 |
| `Open Item` | array | 현재 미승인·미확정·담당자 확인 필요 항목만 기록 |
| `승인 상태` | string | 아래 허용 enum 중 하나만 사용 |
| `적용 규칙` | array | 실제 trigger된 AR ID를 오름차순으로 기록; 없으면 `[]` |

허용 승인 상태는 다음과 같다.

- `APPROVED`: 현재 금액·Vendor·Scope에 필요한 최종 승인 근거가 확인됨
- `REAPPROVAL_REQUIRED`: 기존 승인 뒤 AR-01, AR-04 등 적용 규칙이 재승인을 명시적으로 요구함
- `PENDING`: 필요한 최초 승인 또는 필수 gate가 아직 완료되지 않음
- `REJECTED`: 현재 안의 명시적 거절 근거가 확인됨
- `NOT_APPLICABLE`: 해당 Thread에 승인 workflow가 적용되지 않음
- `UNKNOWN`: 승인 필요 여부나 현재 상태를 근거로 판정할 수 없음

Legal 재검토, Finance 승인, Investment Committee 승인 또는 contract execution 같은 필수 gate가
미완료인 사실만 확인되고 적용 규칙이 재승인을 명시적으로 요구하지 않으면 `PENDING`을 사용한다.

`금액`에 쉼표, 원 기호, 통화명, 승인 설명을 넣지 않는다. 예를 들어 3억 1,800만원은
`금액: 318000000`, `통화: KRW`로 기록한다. 변경 이력의 금액도 가능한 경우 같은 정수 단위를
사용한다. `Business Impact`의 확인된 운영 사건은 `confirmed`, vendor 예상·목표·미검증 효과는
`estimated`에 둔다. 긍정적 의견, 준비 활동, draft, signature request는 `결정된 내용`에 넣지
않는다.

## 전체 결과

```yaml
archive_result:
  result_status: new_record_ready | record_update_ready | additional_confirmation_required | archive_not_needed | storage_tool_unavailable | saved
  archive_decision: {}
  input_inventory: {}
  thread_analysis: {}
  record_match: {}
  archive_record: {}
  record_update: {}
  excel_output: {}
  conflicts: []
  limitations: []
  storage:
    requested: false
    user_approved: false
    tool_available: false
    executed: false
    destination: unknown
    saved_record_id: unknown
    tool_result_source: unknown
```

## 스레드 분석

```yaml
thread_analysis:
  subject: unknown
  senders: []
  recipients: []
  email_dates: []
  initial_request: unknown
  chronological_events:
    - event_date: unknown
      event_type: request | discussion | change | decision | action | completion
      summary: ""
      source_message_id: unknown
  key_discussions: []
  thread_summary: unknown
  decisions: []
  open_items: []
  action_items:
    - action_id_candidate: unknown
      description: ""
      owner: unknown
      due_date: unknown
      status: open | in_progress | completed | blocked | unknown
      source_message_id: unknown
  important_numbers:
    - label: ""
      value: unknown
      unit_or_currency: unknown
      period: unknown
      source_message_id: unknown
  attachments:
    - file_name: ""
      file_type: pdf | spreadsheet | document | image | other | unknown
      access_status: analyzed | unverified | failed
      summary: unknown
      source_message_id: unknown
  changes_in_thread: []
```

## 신규 Archive Record

```yaml
archive_record:
  record_id: unknown
  record_id_candidate: unknown
  title: unknown
  thread_summary: unknown
  requester: unknown
  participants: []
  start_date: unknown
  latest_update_date: unknown
  key_points: []
  decisions: []
  action_items: []
  due_dates: []
  important_numbers: []
  attachments: []
  open_items: []
  current_status: unknown
  source_emails:
    - message_id: unknown
      thread_id: unknown
      subject: unknown
      sent_at: unknown
      source_type: user_provided | mcp_tool_result
```

## 기존 Record 업데이트

```yaml
record_update:
  target_record_id: unknown
  retained_summary: unknown
  proposed_current_record: {}
  field_changes:
    - field_path: ""
      change_type: added | changed | completed | reopened | removed
      previous_value: unknown
      new_value: unknown
      effective_date: unknown
      evidence_date: unknown
      evidence_message_id: unknown
      rationale: ""
  unchanged_fields: []
  new_decisions: []
  new_action_items: []
  completed_action_items: []
  unresolved_items: []
```

예를 들어 Due date가 바뀌면 `previous_value`, `new_value`, `evidence_date`, `evidence_message_id`를 모두 보존한다. 현재 기록만 덮어쓰지 않는다.

## Excel 저장 준비

### 요약 행

| Excel 컬럼 | 원본 필드 | 원칙 |
| --- | --- | --- |
| Record ID | `record_id` 또는 `target_record_id` | 후보 ID와 확정 ID를 구분 |
| 제목 | `title` | 원문 제목을 보존하고 필요 시 정규화 제목 별도 관리 |
| 요청자 | `requester` | 확인 불가 시 `unknown` |
| 최초 요청일 | `start_date` | 스레드 최초 요청 기준 |
| 최근 업데이트일 | `latest_update_date` | 근거가 있는 최신 변경일 |
| 핵심 요약 | `thread_summary` | 현재 상태 중심의 간결한 요약 |
| 결정사항 | `decisions` | 복수 값은 상세 시트 또는 안정된 직렬화 규칙 사용 |
| Action Item | `action_items` | 항목별 행 권장 |
| 담당자 | `action_items[].owner` | Action item과 관계 유지 |
| Due Date | `action_items[].due_date` | 담당 작업과 관계 유지 |
| 주요 금액 | `important_numbers` | 금액·통화·기간 분리 |
| 현재 상태 | `current_status` | 조직 표준 값이 없으면 원문 기반 |
| 변경 내용 | `field_changes` | 변경 이력 시트 참조 권장 |
| Source / Thread identifier | `source_emails` | message/thread ID와 출처 보존 |

### 권장 논리 구조

```yaml
excel_output:
  record_row: {}
  action_item_rows: []
  attachment_rows: []
  change_history_rows: []
  source_email_rows: []
```

실제 시트명, 셀 구분자, ID 생성 규칙은 저장 계층이 정한다. MCP 저장을 우선하되, MCP가 없고 사용자가 명시적으로 승인하면 repository에서 관리하는 지정된 `.xlsx` 저장 계층을 사용할 수 있다.
