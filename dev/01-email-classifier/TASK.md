# 01 · 메일 분류 Skill

- 목적: 3종 국문 분류(`구매 승인 검토 필요 이메일`, `논의 내용 요약 필요 이메일`,
  `일반 이메일`)와 근거 구분·긴급도 규칙을 개선한다.
- 작업 위치: `dev/01-email-classifier/work/email-classifier/`
- A/B 실험 경로: `experiments/ablation/email-classifier/`
- 입력: `shared/taxonomy.md`, 합성 이메일
- 승격 대상: `skills/email-classifier/`
- 완료: 전체 문맥으로 분류하고 확인된 사실과 추론을 구분한다.
