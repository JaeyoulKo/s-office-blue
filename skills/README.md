# skills/ — Codex가 읽는 절차서

여기 있는 것은 **코드가 아니라 문서**다. Codex가 실행 중에 읽고 그대로 따르는 절차서다.
`harness/workspace.py`가 이 폴더를 작업공간에 통째로 복사해 넣으면 Codex가 읽을 수 있게 된다.

> **`.agents/skills/`와 헷갈리지 말 것.** 저장소 루트에 `.agents/skills/purchase-email-agent/`가
> 따로 있다. Ariba 구매 검토를 다루는 이전 스킬이고 이번 범위 밖이다. 건드리지 않는다.
> 이 실험이 주입하는 스킬은 **`skills/` 아래 셋뿐**이다. 두 폴더를 나눈 이유는 실험 대상을
> 명확히 하기 위해서다 — `workspace.py`는 `skills/`만 복사한다.

## 왜 하나가 아니라 셋인가

스토리보드의 `AI 분석: 메일 유형 분류 → 우선 순위 판별 → 브리핑 생성` 체인을 그대로 셋으로 잘랐다.

| 스킬 | 입력 | 출력 | 채우는 필드 |
| --- | --- | --- | --- |
| [`mail-classify`](mail-classify/SKILL.md) | 스냅샷 | 메일별 4갈래 라벨 + 인용 근거 | `category`, `category_reason`, `evidence` |
| [`mail-prioritize`](mail-prioritize/SKILL.md) | 분류 결과 | 처리 순위 + 사유 | `priority_rank`, `priority_reason`, `amount_krw`, `deadline`, `owner` |
| [`mail-brief`](mail-brief/SKILL.md) | 위 둘 | 브리핑 | `briefing.*` |

쪼갠 이유는 두 가지다.

1. **멘티 한 사람이 스킬 하나를 온전히 소유할 수 있다.** 작아서 통째로 이해되고, 남의 파일을 건드릴 일이 없다.
2. **쪼갠 단위가 곧 실험 단위가 된다.** 스킬을 하나씩 얹어가며 측정하면 *어느 스킬이 실제로 값을 만드는지*가 분리되어 보인다. 있음/없음 2개짜리 비교로는 절대 알 수 없는 것이다.

| arm | 주입 스킬 | 묻는 질문 |
| --- | --- | --- |
| `A0` | 없음 | 스킬 없이 스키마만 주면 어디까지 되나 |
| `A1` | classify | 분류 스킬 하나의 기여분 |
| `A2` | classify + prioritize | 우선순위 스킬의 추가 기여분 |
| `A3` | 셋 다 | 전체 하니스 |

## SKILL.md 쓰는 법

Codex 스킬은 **YAML frontmatter + 마크다운 본문**이다.

```markdown
---
name: mail-classify
description: 언제 이 스킬을 써야 하는지. 모델이 이 한 줄을 보고 읽을지 말지 정한다.
---

# 제목
## 목적 / 절차 / 판정 기준 / 자체 검토
```

지켜야 할 것 넷:

1. **`description`은 "무엇을 하는가"가 아니라 "언제 쓰는가"를 쓴다.** 이게 스킬 선택의 유일한 단서다.
2. **SKILL.md는 얇게, 세부는 `references/`로.** 본문은 항상 읽히고 참조 문서는 필요할 때만 읽힌다. 처음부터 다 밀어 넣으면 정작 중요한 지시가 묻힌다.
3. **판정 기준은 문장이 아니라 규칙으로.** "중요해 보이면"이 아니라 "다음 키워드 중 하나가 제목에 있으면".
4. **모호할 때 무엇을 할지 반드시 적는다.** 안 적으면 모델이 지어낸다.

판정 기준의 원본은 [`docs/user-flow/criteria.yaml`](../docs/user-flow/criteria.yaml)이다.
스킬 문서는 그 규칙을 옮겨 쓰되, 기준 자체를 새로 만들지 않는다. 기준을 바꿔야 하면
`criteria.yaml`을 먼저 고치고 근거(스토리보드 어느 부분인지)를 남긴다.

## 고치고 나서 확인할 것

```powershell
python -m experiments.ablation --arms A0,A3 --reps 1   # 빠른 확인
python -m experiments.ablation --arms A0,A1,A2,A3      # 사다리 전체
```

`experiments/runs/<run-id>/report.md`에서 내가 만진 스킬이 담당하는 지표가 움직였는지 본다.
**안 움직였거나 나빠졌으면 그것도 결과다.** 그대로 기록하고 왜인지 쓴다.
