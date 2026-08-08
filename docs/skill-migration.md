# 기존 구매 이메일 Skill 승계표

기존 `.agents/skills/purchase-email-agent/`의 업무 지식을 삭제하지 않고 기능별 Skill과
서비스 경계로 나눈 결과다.

| 기존 파일 또는 기능 | 새 소유 위치 | 처리 |
| --- | --- | --- |
| `SKILL.md`의 이메일 분류 | `skills/email-classifier/` | 기존 7개 국문 분류와 증거 구분 복원 |
| 구매·승인·계약 검토 | `skills/purchase-email-review/` | 정보 추출, 완결성, 기대효과, 과거 계약 비교 복원 |
| 논의 이메일·첨부파일·긴 스레드 | `skills/discussion-email-review/` | 별도 Skill로 분리하고 국문 회신 템플릿 추가 |
| `decision-rules.md` | classifier 판단 규칙 + purchase 검토 규칙 | 분류와 검토 규칙을 각 기능에 배치 |
| `field-checklist.md` | purchase의 `references/field-checklist.md` | 유형별 필드를 국문 원칙 그대로 복원 |
| `approval-brief.md` | purchase의 `templates/approval-brief.md` | 복원 |
| `clarification-email.md` | purchase의 `templates/clarification-email.md` | 복원 |
| `review-report.md` | purchase의 `templates/review-report.md` | 복원 |
| `workflow.md`, `workflow-state-machine.md` | `docs/skill-workflow.md`, 각 Skill 절차, `main_service/` | 기능 경계와 서비스 분기로 승계 |
| `storyboard-spec.md` | `docs/storyboard/spec.md` | 실행 명세를 Skill 밖의 제품 문서로 복원 |
| `mcp-integration.md` | `AGENTS.md`, `main_service/codex_runner.py` | 시점 의존 도구 목록은 제외하고 읽기/쓰기 안전 경계만 승계 |

Skill 폴더명은 Codex Skill 이름 규칙에 따라 영문 소문자와 하이픈을 사용한다. 설명, 본문,
판단 규칙, taxonomy, 템플릿과 UI 문구는 국문을 기본으로 한다.
