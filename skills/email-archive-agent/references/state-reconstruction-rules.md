# State Reconstruction Rules

회사 Archive 정책을 적용하기 전에 이메일 스레드의 상태를 시간순으로 재구성한다.

## 시간순 재구성

1. 메시지를 실제 발송 시각으로 정렬하고 각 메시지의 제안, 결정, 변경, 완료, 취소를 구분한다.
2. amount, Vendor, Scope, approval gate, Compliance/Legal 상태와 Open Item별로 사건을 분리한다.
3. 각 상태에 `historical`, `current`, `superseded`, `pending`, `resolved`, `reopened` 중 적절한 lifecycle을 부여한다.
4. 현재값마다 이를 만든 최신 유효 근거와 message ID를 보존한다.

## 과거값과 현재값

- 과거 승인·견적·Vendor·Scope를 삭제하지 말고 변경 이력으로 유지한다.
- 최신 메일이 과거 내용을 인용만 한 경우 새 결정으로 취급하지 않는다.
- 명시적 수정, 대체, 취소 또는 더 최신의 유효 결정이 있을 때만 값을 superseded 처리한다.
- 최신 제안값과 최신 승인값을 별도로 유지한다. 제안이 더 최신이라는 이유로 승인된 값으로 바꾸지 않는다.

## Approval 상태

- 누가 어떤 금액, Vendor, Scope와 gate를 승인했는지 범위를 함께 기록한다.
- 승인 후 material change가 생기면 기존 approval을 그대로 승계하지 말고 [company-archive-policy.md](company-archive-policy.md)에 따라 유효성을 다시 평가한다.
- 준비 완료, review 완료, 긍정적 의견, 진행 요청과 formal approval을 구분한다.
- 필요한 최종 gate의 근거가 없으면 `Pending` 또는 `REAPPROVAL_REQUIRED` 상태를 유지한다.

## Open Item lifecycle

- 해결 근거가 확인된 항목만 `resolved`로 전환한다.
- 후속 Vendor, Scope, amount 또는 contract terms 변경으로 다시 검토해야 하면 `resolved → reopened` 변경을 기록한다.
- reopened 항목은 새 근거가 확인될 때까지 최종 `Open Item`에 포함한다.
- 과거에 열려 있었지만 현재 해결된 항목은 변경 이력에는 보존하되 최종 `Open Item`에서는 제외한다.
