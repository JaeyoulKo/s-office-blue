# experiments/ — 스킬 하니스가 실제로 효과가 있는가

이 폴더는 **측정**을 위한 곳이다. 코드가 안 깨졌는지 보는 [`tests/`](../tests/)와는 목적이 다르다.

| | `experiments/` | `tests/` |
| --- | --- | --- |
| 묻는 것 | 스킬을 넣으면 결과가 좋아지는가 | 코드가 계약대로 동작하는가 |
| 답 | 숫자와 리포트 | 통과/실패 |
| 실행 | `python -m experiments.ablation` | `pytest` |
| 걸리는 시간 | 분 단위 (LLM 호출) | 초 단위 |

## 무엇을 어떻게 재는가

같은 스냅샷을 여러 번, 조건만 바꿔가며 분석시킨다. **조작 변수는 작업공간에 스킬이 있느냐 하나뿐이다.**

```
[1회] 수집 → snapshot.json (동결) → [N회] 분석 ×arm → 지표 → report.md
      MCP 필요                       MCP 불필요, 파일 in / JSON out
```

분석 단계가 Gmail에 접속하지 않기 때문에 재현 가능하고, 오프라인이며, 메일함이 바뀌어도
결과가 오염되지 않는다.

### arm

스킬 3개를 하나씩 얹어가며 **각자의 기여분을 분리**해 본다. 있음/없음 2개짜리 비교로는
"어느 스킬이 값을 만드는지"를 알 수 없다.

| arm | 주입 스킬 | 묻는 질문 |
| --- | --- | --- |
| `A0` | 없음 | 스킬 없이 스키마 + 과제문만 주면 어디까지 되나 |
| `A1` | `mail-classify` | 분류 스킬의 기여분 |
| `A2` | + `mail-prioritize` | 우선순위 스킬의 추가 기여분 |
| `A3` | + `mail-brief` | 전체 하니스 |

### 두 arm 사이에서 고정되는 것

모델, `model_reasoning_effort`, 출력 스키마, 스냅샷 바이트, 반복 횟수, `--ignore-user-config`.

`--ignore-user-config`가 특히 중요하다. 전역 `~/.codex/config.toml`에 모델·effort 설정과
`~/.codex/skills/`가 있어서, 끄지 않으면 **"스킬 없는 arm"에도 전역 스킬이 새어 든다.**

### 숨기지 않는 것

`A3`의 프롬프트에는 `skills/`를 읽으라는 문단이 추가로 들어간다. 즉 조작 변수는 정확히는
"스킬 파일의 존재"가 아니라 **"스킬 하니스(파일 + 호출)의 존재"**다. 두 프롬프트는 각 arm의
`workspace/prompt.md`에 그대로 남아 있고 UI가 나란히 보여준다. 실험 설계의 이런 틈은
가리는 것보다 적어두는 편이 낫다.

## 정답이 있다는 것

[`cases.yaml`](cases.yaml)의 케이스 20건에는 `expected` 정답이 달려 있다.
그래서 "두 arm이 서로 얼마나 다른가"가 아니라 **"어느 쪽이 맞았는가"**를 잴 수 있다.
이것이 이 실험의 힘이다.

정답은 스냅샷에 들어가지 않는다. 모델은 볼 수 없고 채점기만 `cases.yaml`에서 읽는다.

케이스에는 함정이 섞여 있다.

- `C03` Ariba 키워드가 있지만 결과 알림 → `notice`
- `C04` `[필독]`이 붙었지만 사내 행사 → `notice`
- `C10` 본문이 비어 판단 불가 → `unknown` (억지 분류가 오답)
- `C14` 외화 금액 → 환산하면 오답, `null` + `notes` 기록이 정답
- `C17` prompt injection → 지시를 따르면 실패

## 지표 — 사람 판단 없이 계산되는 것

| 지표 | 계산 |
| --- | --- |
| **정확도** | 정답 라벨 대비 분류 일치율 |
| **환각 id** | 출력의 `message_id`가 스냅샷에 실재하는가 |
| **근거 인용률** | `evidence`가 실제 원문의 부분문자열인가 |
| 커버리지 | 모든 메일에 결과가 하나씩 있는가 |
| 우선순위 재현율 | 먼저 봐야 할 건이 `top_items`에 들어왔는가 |
| 스키마 통과 | `contracts/triage.schema.json` 검증 |
| counts 합계 | 브리핑 집계가 실제 건수와 맞는가 |
| 자기일관성 | 같은 arm 반복 간 라벨이 흔들리지 않는가 |

앞의 셋만 봐도 결론이 난다. 셋 다 객관적으로 계산되고 **반박할 수 없다.**
"스킬을 쓰니 좋아 보인다"는 감상이지만 "없는 id를 3건 만들어냈다"는 사실이다.

계산은 [`metrics.py`](metrics.py)에 있다.

## 실행

```powershell
# 1) 실험 환경 준비 (Gmail 불필요)
python -m experiments.seed_gmail --mode fixture

# 2) 빠른 확인
python -m experiments.ablation --arms A0,A3 --reps 1

# 3) 사다리 전체
python -m experiments.ablation --arms A0,A1,A2,A3 --reps 3

# 결과: experiments/runs/<run-id>/report.md
```

Gmail 실연결로 하려면 [`docs/setup.md`](../docs/setup.md)를 먼저 보고,

```powershell
python -m experiments.seed_gmail --mode insert --label OFFICEBLUE-TEST
python -m experiments.ablation --collect connector --query "label:OFFICEBLUE-TEST is:unread"
python -m experiments.seed_gmail --cleanup      # 끝나면 반드시 회수
```

## 산출물

```
experiments/runs/<run-id>/          ← .gitignore. 실제 메일은 여기서 나가지 않는다.
├─ snapshot.json                    수집 결과. 한 번 만들어지면 불변
├─ A0/
│  ├─ workspace/                    이 arm이 실제로 본 것 전부 (증거로 보존)
│  │  ├─ snapshot.json
│  │  └─ prompt.md
│  └─ rep-1/
│     ├─ command.txt                실행된 codex 명령 전문
│     ├─ prompt는 workspace/prompt.md 참조
│     ├─ events.jsonl               codex --json 이벤트 원본
│     ├─ stdout.log                 사람이 읽는 로그
│     ├─ result.json                모델 출력
│     └─ outcome.json               성공 여부·소요·토큰·스키마 오류
├─ A3/  (workspace/ 아래에 skills/ 가 더 있다 — 이것이 조작 변수)
├─ results.json                     계산된 지표 전체
└─ report.md                        읽는 문서
```

`A0/workspace/`와 `A3/workspace/`의 파일 목록을 나란히 놓고 보는 것이
이 실험을 이해하는 가장 빠른 길이다.

## 결과 기록

`experiments/runs/`는 `.gitignore`에 있어서 저장소에 남지 않는다. **남길 가치가 있는 결론은
[`results-log.md`](results-log.md)에 손으로 옮긴다.** 이 프로젝트가 쌓여가는 곳이다.

첫 측정(#001) 요약: `A0` 0.933 → `A1` 0.983 → `A2` **1.000** → `A3` 0.950.
스킬을 얹을수록 좋아지다가 **마지막에 떨어졌다.** 그게 이번 실험에서 가장 값진 발견이다.

## 결과를 읽을 때

**결과가 예상과 다르면 그것이 결과다.**

스킬이 baseline을 이기지 못했다면 그대로 기록한다. 결론을 정해놓고 맞추는 순간 이 실험은
가치를 잃는다. 지지 않았더라도 다음을 확인하면 다음 할 일이 나온다.

- `report.md`의 **틀린 분류** 목록 — 어느 케이스에서 밀렸는가
- 그 케이스가 요구하는 판단이 스킬 문서에 **적혀 있는가**
- 적혀 있는데도 틀렸다면 문장이 모호한가, 아니면 참조 문서에 묻혀 있는가

표본이 작다 (메일 20건 × 반복 3회). **소수점 둘째 자리 차이는 노이즈로 본다.**
확실한 신호는 환각 건수, 스키마 실패, 정확도의 0.1 이상 차이 정도다.

## 안전

`seed_gmail.py`는 이 저장소에서 **유일하게 쓰기를 하는 코드**이고 사람이 직접 실행한다.
에이전트에게는 도구로 노출하지 않으며 자격증명도 분리한다. 에이전트의 Gmail 접근은
끝까지 읽기 전용이다. 자세한 내용은 [`AGENTS.md`](../AGENTS.md).
