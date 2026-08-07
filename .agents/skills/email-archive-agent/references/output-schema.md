# Archive 출력 스키마

## 공통 규칙

- 확인되지 않은 단일 값은 `unknown`, 반복 값은 빈 배열로 둔다.
- 날짜는 확인 가능한 경우 ISO 8601로 정규화하고 원문과 시간대를 출처에 보존한다.
- 금액은 숫자, 통화, 단위, 기간과 원문 출처를 분리한다.
- Action item, 결정, 첨부파일, 변경 이력은 반복 가능한 별도 항목으로 유지한다.
- `record_id`는 기존 시스템 값 또는 저장 성공 결과가 있을 때만 확정한다.

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
