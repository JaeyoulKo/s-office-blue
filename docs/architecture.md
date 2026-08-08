# 아키텍처 — 두 트랙

이 프로젝트는 **두 갈래로 갈라져 있고, 한 곳에서만 만난다.** 폴더를 열었을 때 내가 어느 쪽
일을 하는지 바로 알 수 있어야 하고, 남의 트랙을 몰라도 내 트랙 일이 되어야 한다.

```
┌──────────────────────────────────────────────────────────┐
│  Track A · 서비스                            ui/app.py   │
│                                                          │
│  사람이 보는 Streamlit 화면. 버튼 하나 = 실행 하나.       │
│  Codex도 MCP도 모른다. run_arm() 하나만 부른다.           │
└────────────────────────┬─────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │   contracts/        │   ← 두 트랙이 만나는 유일한 지점
              │   snapshot.schema   │
              │   triage.schema     │
              └──────────┬──────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│  Track B · 하니스                             harness/   │
│                                                          │
│  gmail.py      메일 수집 → 스냅샷 정규화 (어댑터 3종)     │
│  workspace.py  격리 작업공간을 만들고 스킬을 주입          │
│  codex.py      codex exec 호출 + --json 이벤트 스트리밍   │
│  run.py        run_arm() — 바깥이 아는 유일한 함수         │
├──────────────────────────────────────────────────────────┤
│  Track B · 스킬                                skills/   │
│                                                          │
│  Codex가 실행 중에 읽는 절차서. 코드가 아니라 문서다.      │
│  mail-classify → mail-prioritize → mail-brief            │
└──────────────────────────────────────────────────────────┘

experiments/   두 트랙을 가로질러 "정말 효과가 있나"를 측정한다
tests/         코드가 계약대로 동작하는가를 확인한다 (실험과 별개)
docs/          왜 이렇게 만들었는가, 무엇을 만들어야 하는가
```

## 계약 규율 — 이것 하나만 지킨다

`ui/app.py`는 `harness.run.run_arm()` **하나만** 호출한다.

```python
run_arm(run_dir, arm_id, skills, snapshot) -> dict
```

이 시그니처가 인터페이스의 전부다. 내부가 `codex exec` 서브프로세스에서 SDK나 HTTP 백엔드로
바뀌어도 UI는 한 줄도 바뀌지 않는다.

거꾸로도 참이다. 화면을 어떻게 그리든 하니스는 모른다. 그래서 **UI 담당과 스킬 담당이 서로를
기다리지 않고 동시에 일할 수 있다.**

## 왜 codex exec 인가

LLM을 부르는 방법은 여러 가지다. 여기서는 **터미널에서 손으로 치는 것과 완전히 같은 명령**을
`subprocess`로 실행한다.

```bash
codex exec --ephemeral --ignore-user-config --sandbox read-only \
  --model <M> --config model_reasoning_effort="<E>" \
  --output-schema contracts/triage.schema.json \
  --output-last-message <run>/<arm>/rep-<n>/result.json \
  --cd <격리 작업공간> --json --color never -
```

이유가 셋 있다.

1. **UI가 마법이 아니라는 걸 보여준다.** 화면에 이 명령 전문이 그대로 뜬다. 멘티가 복사해
   터미널에 붙여 넣으면 똑같이 동작한다. 디버깅 경로가 하나다.
2. **스킬을 파일 시스템으로 주입할 수 있다.** `--cd`로 작업 디렉터리를 지정하면 Codex는 그
   안에 있는 것만 본다. 그래서 "스킬이 있는 세계"와 "없는 세계"를 폴더 하나로 가를 수 있다.
3. **`--output-schema`가 출력 형태를 강제한다.** 두 arm이 같은 모양으로 답해야 비교가 성립한다.

## 수집과 분석을 나눈다

```
[1회] 수집 → snapshot.json (동결) → [N회] 분석 ×arm → 지표
      MCP 필요                       MCP 불필요, 파일 in / JSON out
```

분석 단계는 Gmail에 접속하지 않는다. 결과가 셋 따라온다.

- **재현 가능하다.** 같은 스냅샷으로 몇 번이든 다시 돌린다.
- **오프라인이다.** Gmail 인증이 안 되어 있어도 `fixture` 어댑터로 전 과정이 돌아간다.
- **오염되지 않는다.** 실험 도중 메일함에 새 메일이 와도 결과가 흔들리지 않는다.

수집 어댑터는 세 개이고 전부 같은 `snapshot.schema.json`을 만든다.

| 어댑터 | 경로 | 쓸 때 |
| --- | --- | --- |
| `fixture` | `experiments/cases.yaml` | 개발·CI·데모. Gmail 불필요 |
| `connector` | OpenAI Gmail 커넥터 `mcp__codex_apps__gmail_*` | 실메일, 읽기 전용 |
| `local-mcp` | `~/.codex/mcp/gmail-local/server.mjs` | 실메일, 초안 생성까지 필요할 때 |

**어느 경로를 표준으로 할지는 아직 정하지 않았다.** 그래서 스냅샷 계약만 고정하고 어댑터는
갈아 끼울 수 있게 두었다. 정해지면 한 줄만 바꾸면 된다.

## 격리 — 실험이 성립하느냐가 여기서 갈린다

`workspace.py`가 arm마다 임시 디렉터리를 새로 만들고, 그 arm이 봐도 되는 것만 복사한다.

```
A0 workspace/            A3 workspace/
├─ snapshot.json         ├─ snapshot.json      ← 같은 바이트 (해시로 검증)
└─ prompt.md             ├─ prompt.md          ← 과제문 공유, 스킬 지시 문단만 추가
                         └─ skills/            ← 이것이 조작 변수
                            ├─ mail-classify/
                            ├─ mail-prioritize/
                            └─ mail-brief/
```

두 arm에 **고정**되는 것: 모델, `model_reasoning_effort`, 출력 스키마, 스냅샷 바이트,
반복 횟수, `--ignore-user-config`.

마지막 것이 특히 중요하다. 전역 `~/.codex/config.toml`에는 모델·effort 설정과
`~/.codex/skills/`가 있다. 끄지 않으면 **"스킬 없는 arm"에도 전역 스킬이 새어 든다.**
이 격리는 [`tests/test_workspace.py`](../tests/test_workspace.py)가 지킨다. 그 테스트가
깨지면 실험 결과 전체가 무효다.

## 스킬을 셋으로 쪼갠 이유

스토리보드의 `유형 분류 → 우선순위 판별 → 브리핑 생성` 체인을 그대로 셋으로 잘랐다.

| 스킬 | 채우는 필드 |
| --- | --- |
| `mail-classify` | `category`, `category_reason`, `evidence` |
| `mail-prioritize` | `priority_rank`, `priority_reason`, `amount_krw`, `deadline`, `owner` |
| `mail-brief` | `briefing.*` |

두 가지를 동시에 얻는다.

1. **멘티 한 사람이 스킬 하나를 온전히 소유한다.** 작아서 통째로 이해되고 남의 파일을 안 건드린다.
2. **쪼갠 단위가 곧 실험 단위가 된다.** 스킬을 하나씩 얹어가며 (`A0`→`A1`→`A2`→`A3`) 각자의
   기여분을 분리해 볼 수 있다. 있음/없음 2개짜리 비교로는 알 수 없는 것이다.

## 데이터 경계

| | 커밋한다 | 커밋하지 않는다 |
| --- | --- | --- |
| 메일 | `experiments/cases.yaml`의 합성 데이터 | 실제 메일 본문·제목·발신인 |
| 식별자 | 없음 | provider의 message_id·thread_id |
| 자격증명 | 없음 | OAuth 토큰, client secret |
| 실행 결과 | 없음 | `experiments/runs/` 전체 |

`experiments/runs/`는 `.gitignore`에 있다. 실제 메일은 이 폴더 밖으로 나가지 않는다.
자세한 것은 [`AGENTS.md`](../AGENTS.md).

## 쓰기 권한은 한 곳뿐

이 저장소에서 **쓰기를 하는 코드는 `experiments/seed_gmail.py` 하나**다.
실험용 가짜 메일을 테스트 라벨에 주입하는 스크립트이고, 사람이 직접 실행하며,
에이전트의 도구로 노출되지 않는다. 자격증명도 에이전트가 쓰는 것과 분리한다.

에이전트의 Gmail 접근은 끝까지 읽기 전용이다. 최소 권한 분리의 실제 예다.

## 이 설계가 빚진 것

`run_job()` 하나만 노출하는 계약, `codex exec --json` 이벤트 스트리밍, `--output-schema`로
출력을 강제하는 방식, 임시 파일에 받아 성공했을 때만 제자리로 옮기는 원자적 교체 —
이 패턴들은 앞선 MVP에서 검증된 것을 가져왔다.
