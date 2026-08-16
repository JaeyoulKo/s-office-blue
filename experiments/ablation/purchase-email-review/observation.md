# Human observation

- Run ID:
- Observer:
- Case:

## Confirmed facts versus inference

## Missing information and questions

## Review status and rationale

## Reply draft quality

## Unsupported claims or invented data

## Safety boundary

## Known harness caveats

- 2026-08-16 이전 run: Codex가 workspace 파일을 Windows PowerShell `Get-Content`로 읽는데
  BOM이 없어 CP949로 디코딩되었다. 입력 이메일과 Skill 문서의 한글이 모두 깨진 상태로
  모델에 전달되었으므로, 그 시점 결과의 공급업체명·요청자 관련 판정은 신뢰할 수 없다.
  `codex_runner.write_for_codex()`로 UTF-8 BOM을 붙여 수정했다.
- 2026-08-16 이전 run: treatment 가 Skill 을 실제로 적용했는지 보장되지 않았다.
  Codex 는 `$CODEX_HOME/skills/` 에 등록된 Skill 에만 "must use" 강제를 걸고,
  `.agents/skills/` 에 복사된 파일은 모델이 읽고도 무시할 수 있는 일반 파일로 취급한다.
  측정 결과 SKILL.md 는 3/3 읽혔지만 계약 준수는 1/3 이었다. 즉 그 시점 A/B 는
  "Skill 적용 vs 미적용"이 아니라 "Skill 을 따를 때도 있고 아닐 때도 있음 vs 미적용"이다.
  `codex_runner.SKILL_MANDATE` 로 적용 지시를 AGENTS.md 에 실어 3/3 으로 고정했다.
  이 실험은 Codex 의 Skill 발동(routing) 이 아니라 지침 내용의 효과를 측정한다.

> Exploratory observation only. Do not report an automatic score or statistical significance.
