# Archive Record 매칭 규칙

## 원칙

동일 레코드 판단은 독립적인 여러 근거와 시간적 연속성을 함께 사용한다. 제목이나 키워드 하나만 같다는 이유로 병합하지 않는다. 검색하지 못한 상태를 검색 결과 없음으로 표현하지 않는다.

## 매칭 신호

### 강한 신호

- 동일한 시스템 Thread ID 또는 원본 메시지 체인이 이어진다.
- 동일한 고유 reference number, 계약번호, 티켓번호, 주문번호가 확인된다.
- 기존 레코드가 보존한 source message ID와 reply/reference 관계가 확인된다.
- 현재 메일이 기존 결정·기한·Action item을 명시적으로 인용해 변경한다.

### 보조 신호

- 정규화한 제목이 동일하거나 회신/전달 접두사를 제외하면 유사하다.
- 프로젝트, 업무 목적, 요청자, 주요 참여자가 일치한다.
- 공급사·거래처, 금액·조건, 첨부파일 또는 기간이 연속된다.
- 메시지 날짜가 기존 기록의 최근 업데이트와 합리적으로 이어진다.

### 충돌 신호

- 동일 제목이지만 프로젝트, 고객, 공급사 또는 reference number가 다르다.
- 요청 목적과 산출물, 기간 또는 핵심 참여자가 별개다.
- 동일한 식별자처럼 보이지만 출처 시스템이나 형식이 다르다.
- 하나의 후보로 병합하면 서로 양립할 수 없는 현재 상태가 된다.

## 판단 결과

### `same_record`

다음 중 하나를 충족하고 중대한 충돌 신호가 없을 때만 사용한다.

- 하나 이상의 강한 신호가 출처와 함께 확인됨
- 여러 보조 신호가 서로 독립적으로 일치하고 시간적·업무적 연속성이 명확함

### `new_record`

- 검색 가능한 범위에서 적합한 후보가 없고 현재 메일이 독립 업무를 시작함
- 후보가 있더라도 고유 식별자나 업무 목적이 명백히 다름
- 같은 공급사나 요청자의 반복 업무지만 별개의 요청·기간·산출물임

### `ambiguous`

- 제목 또는 키워드만 일치함
- 복수 후보가 비슷한 근거를 가짐
- 강한 일치 신호와 중대한 충돌 신호가 함께 존재함
- 원문, 기존 기록 또는 식별자가 부족해 책임 있게 병합할 수 없음

`ambiguous`에서는 후보와 확인 질문을 제공하고 새 레코드 생성이나 기존 기록 병합을 확정하지 않는다.

## 후보 평가 구조

```yaml
record_match:
  search_status: completed | search_unavailable | partial
  decision: same_record | new_record | ambiguous
  selected_record_id: unknown
  candidates:
    - record_id: ""
      matching_evidence:
        - field: "thread_id"
          current_value: ""
          existing_value: ""
          source: ""
      conflicting_evidence: []
      confidence: high | medium | low
  user_confirmation_required: false
```

정량 점수나 임계값은 조직 데이터로 검증되기 전까지 도입하지 않는다. 향후 검색 기능은 후보 생성과 최종 동일성 판단을 분리한다.
