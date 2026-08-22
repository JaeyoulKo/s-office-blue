# 03 · 논의 이메일 검토 Skill

- 목적: 논의·질의 스레드 판단과 국문 회신 템플릿을 개선한다.
- 작업 위치: `dev/03-discussion-email-review/work/`
- 실험용 Skill 경로: `dev/03-discussion-email-review/work/skills/`
- A/B 실험 경로: `experiments/ablation/skill_ab_test/`
- 입력: 분류 결과, 이메일 스레드, 접근 가능한 첨부파일
- 승격 대상: `skills/email-archive-agent/`
- 결정된 내용: 개발 중인 Skill의 소유 작업은 `dev/03-discussion-email-review/`로 두고,
  고유 이름은 `email-archive-agent`로 유지한다. A/B 비교 코드는 실험 정의 경로에 둔다.
- 미결 사항: 검토 완료 후 승인 Skill로 승격할지와 최종 승격 경로는 별도로 결정한다.
- 검증 기준: 결정된 내용과 미결 사항, 담당자, 기한을 구분하고 실제 발송하지 않는다.
  스레드 중 금액 및 승인 상태가 바뀐 경우 이전 값부터 현재 값까지 변경 이력을 복원한다.
