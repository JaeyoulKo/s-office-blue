# 아카이빙 판단 규칙

## 판단 우선순위

1. 사용자의 현재 대화에서 명시한 선택
2. 제공된 조직 보존 정책 또는 법적 보존 기준
3. 메일의 업무상 추후 참고 가치
4. 불확실하면 사용자 확인

사용자의 아카이빙 선택은 분석 진행 여부에 우선한다. 다만 명시적 선택은 곧바로 외부 저장을 승인한 것으로 해석하지 않는다.

## 결과 값

### `archive_recommended`

다음 신호 중 하나 이상이 문맥상 분명하고 추후 추적 가치가 있을 때 권장한다.

- 승인, 결정, 합의, 책임 배정 또는 공식 요청을 포함한다.
- 프로젝트, 고객, 공급사, 계약, 구매, 비용, 일정 또는 업무 변경을 기록한다.
- Action item, 담당자 또는 Due date가 있다.
- 중요한 금액, 조건, reference number 또는 증빙 첨부파일이 있다.
- 향후 분쟁, 감사, 인수인계 또는 반복 업무에 근거로 사용할 가능성이 있다.
- 기존 Archive Record의 상태나 값을 변경한다.

### `archive_not_needed`

다음 조건이 명확하고 보존 정책과 충돌하지 않을 때 적용한다.

- 업무 기록 가치가 없는 개인적·사교적 대화다.
- 실질 내용 없이 단순 수신 확인, 자동 알림 또는 중복 전달에 그친다.
- 이미 동일 내용이 완전하게 보관되었고 새 정보나 변경이 없다.
- 사용자가 명시적으로 제외했고 강제 보존 근거가 제공되지 않았다.

자동 알림이라도 승인 결과, 장애, 결제, 마감, 보안 사건 등 중요한 상태를 증명하면 불필요로 보지 않는다.

### `needs_user_confirmation`

다음 상황에서는 임의 결정하지 않는다.

- 업무와 개인 내용이 섞여 있다.
- 기존 기록과 중복인지, 새 변경이 있는지 판단할 자료가 부족하다.
- 보존 정책 적용 대상인지 불명확하다.
- 민감정보가 포함되어 저장 위치나 접근 범위를 결정해야 한다.
- 아카이빙 가치 신호와 제외 신호가 상충한다.

## 판단 출력

```yaml
archive_decision:
  recommendation: archive_recommended | archive_not_needed | needs_user_confirmation
  user_selection: selected | excluded | not_provided
  rationale:
    - evidence: ""
      source: ""
      evidence_status: confirmed | inferred
  policy_basis: unknown
  storage_approved: false
```

키워드 수나 단일 문구만으로 결론 내리지 않는다. 사용자 선택과 저장 승인, 아카이빙 권고를 별도 필드로 유지한다.
