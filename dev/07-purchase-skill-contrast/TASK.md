# 07 · 구매 Skill A/B 대비 개선

- 목적: 일반 LLM 리뷰와 구분되는 구매 검토 규칙을 Skill에 명시하고 Codex A/B로 검수한다.
- 작업 위치: `dev/07-purchase-skill-contrast/work/purchase-email-review/`
- 입력: 복합 합성 구매 승인 이메일
- 승격 대상: `skills/purchase-email-review/`
- 완료: Python 후처리 없이 treatment가 상태 우선순위, 증거 등급, 누락 코드, 회신 조건을 적용한다.
