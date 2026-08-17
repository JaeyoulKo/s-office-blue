# Company Archive Policy

이 정책은 Email Archive 결과를 만들 때 반드시 적용한다. 전체 스레드의 현재 상태를 먼저 재구성하고 AR-01부터 AR-10까지 모든 적용 가능성을 평가한다. 이메일에 근거가 부족하면 임의로 trigger하지 말고 `insufficient_evidence`로 남긴다.

## 공통 평가 원칙

- 각 규칙을 `triggered`, `not_triggered`, `insufficient_evidence` 중 하나로 평가하고 근거 message ID와 날짜를 보존한다.
- 기존 approval 이후 amount, Vendor, Scope, 계약 조건 등 material change가 있으면 현재 approval validity를 다시 평가한다.
- 하나라도 재승인을 요구하면 `current_approval_status: REAPPROVAL_REQUIRED`로 판정한다.
- `REAPPROVAL_REQUIRED`는 AR-01이나 AR-04처럼 적용 규칙이 재승인을 명시적으로 요구할 때만
  사용한다. AR-02, AR-03, AR-06, AR-07, AR-09 또는 AR-10의 미완료 gate만 있으면 현재
  안의 명시적 거절이나 재승인 규칙 근거가 없는 한 `PENDING`으로 판정한다.
- `AR-01 = false`여도 `AR-04 = true`이면 결과는 `REAPPROVAL_REQUIRED`다.
- 긍정적 의견, 준비 활동 또는 일부 gate 완료를 최종 승인으로 확대 해석하지 않는다.
- 정책 결과를 `결정된 내용`, `Thread 진행 중 변경된 내용`, `Open Item`에 명시적으로 반영한다.

## AR-01 — 승인 후 금액 변경

최종 승인 이후 현재 금액이 승인 금액에서 절대값 기준 5%를 초과해 변경되면 기존 승인은 변경 금액에 유효하지 않으며 재승인이 필요하다.

```text
change_rate = abs(current_amount - approved_amount) / approved_amount
trigger: change_rate > 0.05
result: REAPPROVAL_REQUIRED
```

변경률이 정확히 5%이거나 5% 이하이면 금액 변경만을 이유로 재승인을 요구하지 않는다. 다만 다른 규칙이 trigger되면 재승인이 필요할 수 있다. 통화, 세금 포함 여부, 기간과 단위가 같은 값끼리만 계산하며 비교할 수 없으면 `insufficient_evidence`로 둔다.

예: `300M → 318M`, 변경률 6%이므로 `REAPPROVAL_REQUIRED`.

## AR-02 — Preferred Vendor

Procurement가 Preferred Vendor 또는 우선협상대상자를 선정한 사실만으로 최종 Vendor가 확정됐다고 기록하지 않는다. 해당 workflow에서 Finance approval이 필요하면 Finance approval 완료 후에만 최종 Vendor로 기록한다. 그 전에는 preferred/proposed Vendor와 `Finance approval pending`을 구분한다.

## AR-03 — Budget Approval

Budget 확보 또는 Budget approval과 Investment approval을 별도 gate로 취급한다. Investment Committee approval이 필요한 건은 예산이 확보됐더라도 위원회 승인 전까지 `Investment approval = Pending`으로 판정하고 이를 Open Item에 남긴다.

## AR-04 — Scope Category Change

최종 승인 이후 Scope Category가 변경되면 금액 변화율과 관계없이 재승인이 필요하다. `Software Upgrade → Software + Hardware Installation`처럼 승인 범주가 달라지면 금액 변화가 1%여도 `REAPPROVAL_REQUIRED`다. AR-01이 trigger되지 않아도 AR-04가 trigger되면 재승인을 요구한다.

## AR-05 — Operational Preparation

다음 활동은 project 또는 investment approval을 의미하지 않는 preparation activity다.

- 설치 일정 준비
- Vendor meeting
- Resource reservation
- Implementation planning
- Site preparation
- 계약 준비
- 운영팀의 “진행해주세요”
- 일정 선점
- 교육 준비

준비가 진행됐다는 이유로 approval requirement를 완료 처리하지 않는다.

## AR-06 — Compliance / Legal Completion

Compliance 또는 Legal review 완료는 해당 review Open Item만 resolved 처리한다. 이를 Investment approval, Purchase approval 또는 Contract execution 완료로 확대 해석하지 않는다. 각각의 gate는 별도 근거로 확인한다.

## AR-07 — Reopened Open Item

한 번 resolved된 Open Item이라도 후속 material change로 재검토가 필요해지면 다시 `open` 또는 `reopened`로 처리한다. 예를 들어 Legal review 완료 뒤 Vendor나 contract terms가 변경되면 새 범위의 Legal review 필요성을 평가하고, 필요하면 Legal review를 reopened Open Item으로 기록한다.

AR-07 단독 trigger는 Legal 등 해당 gate를 `PENDING`으로 되돌린다. 별도의 재승인 요구 규칙이
동시에 trigger되지 않으면 전체 승인 상태를 자동으로 `REAPPROVAL_REQUIRED`로 바꾸지 않는다.

## AR-08 — PoC vs Full Rollout

PoC approval이나 PoC 성공은 Full Investment 또는 Full Rollout approval을 의미하지 않는다. 별도 investment approval이 필요한 경우 그 승인 전까지 `Full Rollout = Pending`으로 판정하고 Open Item에 남긴다.

## AR-09 — Contract Execution

다음 상태만으로 contract execution 완료를 기록하지 않는다.

- contract draft 완료
- Legal review 완료
- commercial terms 합의
- signature request 발송

최종 서명 또는 executed confirmation이 확인된 경우에만 계약 체결 완료로 기록한다.

## AR-10 — Final Approval Gate

여러 approval gate가 있으면 필수 gate가 모두 완료돼야 `Final Approved`로 기록한다. 일부 stakeholder의 긍정적 의견, 중간 approval, “진행”, “확정”, “review 완료” 같은 표현만으로 전체 workflow를 Approved 처리하지 않는다. 각 문구가 어느 gate와 범위에 관한 것인지 확인한다.

## 최종 출력 반영

- `Thread 진행 중 변경된 내용`: 승인 금액과 현재 금액, Vendor, Scope, approval gate의 이전값과 현재값을 명시한다.
- `결정된 내용`: 기존 approval 내용과 범위, 후속 변경에 대한 유효성, trigger된 AR 규칙 및 현재 approval status를 명시한다.
- `Open Item`: 재승인, 필수 Finance/Legal/Compliance/Investment approval, contract execution 및 reopened item 중 실제 unresolved 항목만 기록한다.

정책 평가를 내부 메모로만 남기지 않는다. 최종 8개 필드에서 현재 상태와 미결 gate를 사용자가 확인할 수 있어야 한다.
