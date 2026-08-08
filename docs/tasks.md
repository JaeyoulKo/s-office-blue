# 멘티 task

뼈대는 **이미 돌아간다.** 빈 폴더를 채우는 게 아니라 동작하는 시스템을 깊게 만드는 일이다.
그래서 내가 만진 것이 좋아졌는지 나빠졌는지 숫자로 확인할 수 있다.

## 규칙 넷

1. **한 사람이 task 하나와 브랜치 하나를 소유한다.** 소유 경로가 서로 겹치지 않으므로 충돌이 안 난다.
2. **소유 경로 밖은 건드리지 않는다.** 남의 경로를 고쳐야 하면 먼저 말한다.
3. **`main`에 직접 push하지 않는다.** 브랜치 → PR → mentor 병합.
4. **`contracts/`와 `harness/`는 mentor 소유다.** 바꿔야 하면 요청한다. 여기가 흔들리면 모든 실험 결과를 다시 내야 한다.

## 배정표

| Task | 트랙 | 브랜치 | 소유 경로 |
| --- | --- | --- | --- |
| [T1 분류 스킬](#t1--분류-스킬) | B · 하니스 | `task/01-classify` | `skills/mail-classify/` |
| [T2 우선순위·브리핑 스킬](#t2--우선순위브리핑-스킬) | B · 하니스 | `task/02-brief` | `skills/mail-prioritize/`, `skills/mail-brief/` |
| [T3 서비스 UI](#t3--서비스-ui) | A · 서비스 | `task/03-ui` | `ui/` |
| [T4 실험 환경](#t4--실험-환경) | 실험 | `task/04-experiment` | `experiments/cases.yaml`, `experiments/seed_gmail.py` |
| [T5 사용자 플로우 문서](#t5--사용자-플로우-문서) | 문서 | `task/05-user-flow` | `docs/user-flow/` |

2~3명이면 각자 T1 / T2 / T3을 하나씩 갖는다. T4·T5는 먼저 끝난 사람이 이어받거나 mentor가 맡는다.

**T5는 코드가 없다.** git이 처음이면 여기부터 시작하는 게 좋다.

## 시작하기 전에

[`docs/setup.md`](setup.md)를 끝까지 따라 하고 이게 통과해야 한다.

```powershell
pytest -q                                            # 26 passed
python -m experiments.seed_gmail --mode fixture
python -m experiments.ablation --arms A0,A3 --reps 1  # report.md 가 생긴다
```

그다음 [`docs/architecture.md`](architecture.md)를 읽는다. 5분이면 된다.

---

## T1 · 분류 스킬

### 목적
메일을 4갈래로 분류하는 스킬을 정확하게 만든다. **이 프로젝트에서 가장 중요한 스킬이다.**
스토리보드에 `분류 skills (작성 예정)`이라고 적혀 있던 그 항목이다.

### 소유 경로
`skills/mail-classify/` — `SKILL.md`, `references/taxonomy.md`

### 금지
- `contracts/`, `harness/` 수정 (mentor 소유)
- `docs/user-flow/criteria.yaml`에 없는 판정 기준을 새로 만드는 것 — 기준이 필요하면 **T5에게 요청**해서 `criteria.yaml`을 먼저 고친다
- `experiments/cases.yaml`의 정답을 스킬에 맞춰 바꾸는 것 (시험지를 고치는 셈이다)

### 입력
- [`docs/user-flow/criteria.yaml`](user-flow/criteria.yaml)의 `classification`, `important_email`, `purchase_approval`, `discussion`, `notice`
- [`skills/README.md`](../skills/README.md) — SKILL.md 쓰는 법
- 현재 `report.md`의 **틀린 분류** 목록

### 할 일
1. 현재 상태를 먼저 잰다: `python -m experiments.ablation --arms A0,A1 --reps 3`
2. `report.md`에서 `A1`이 틀린 케이스를 찾는다
3. 그 케이스가 요구하는 판단이 `taxonomy.md`에 **적혀 있는지** 본다
   - 안 적혀 있다 → 판정 기준을 추가한다
   - 적혀 있는데 틀렸다 → 문장이 모호하거나 다른 규칙에 묻혔다. 순서·표현을 고친다
4. 다시 재고 비교한다

### 완료 조건
- [ ] `A1`의 정확도가 `A0`보다 **높다** (3회 중앙값)
- [ ] 근거 인용률이 `A0`보다 낮지 않다
- [ ] 환각 id가 0이다
- [ ] 함정 케이스 `C03`, `C04`, `C17`을 3회 모두 맞힌다
- [ ] `pytest -q` 통과
- [ ] PR 본문에 **개선 전후 숫자**와 무엇을 고쳐서 그렇게 됐는지 적었다

### 막혔을 때
정확도가 안 오르면 `SKILL.md`에 규칙을 더 밀어 넣기 전에 **`references/taxonomy.md`로 옮겨보라.**
SKILL.md는 항상 읽히고 references는 필요할 때 읽힌다. 본문이 길어지면 정작 중요한 지시가 묻힌다.

---

## T2 · 우선순위·브리핑 스킬

### 목적
분류된 메일에 처리 순서를 매기고, 사람이 30초 안에 읽는 브리핑을 만든다.

### 소유 경로
`skills/mail-prioritize/`, `skills/mail-brief/`

### 금지
T1과 동일. 추가로 `skills/mail-classify/`를 건드리지 않는다 (T1 소유).

### 입력
- [`docs/user-flow/criteria.yaml`](user-flow/criteria.yaml)의 `briefing_priority`
  — **티어 순서는 보드에 없어서 해석한 것**이다 (`certainty: interpreted`). 더 나은 순서를 찾으면 근거와 함께 제안한다
- `experiments/cases.yaml`의 `expected.priority_top`

### 할 일
1. `python -m experiments.ablation --arms A1,A2,A3 --reps 3`
2. `A2`가 `A1`보다 우선순위 재현율을 올렸는지, `A3`가 `A2`보다 counts 합계 일치를 올렸는지 본다
3. 금액 정규화(`1,500만원`, `USD 5,000`)와 기한 환산(`오늘까지`)이 맞는지 결과 JSON에서 직접 확인한다

### 완료 조건
- [ ] `A2`의 우선순위 재현율이 `A1`보다 높다
- [ ] `A3`의 counts 합계 일치가 3/3이다
- [ ] `C12`(한글 금액)에서 `amount_krw == 15000000`
- [ ] `C14`(외화)에서 `amount_krw == null`이고 `notes`에 기록됐다
- [ ] `C07`(금액 미기재)에서 금액을 추정하지 않았다
- [ ] PR 본문에 개선 전후 숫자

### 막혔을 때
브리핑 요약에 없는 숫자가 나오면 `mail-brief/references/format.md`의 **금지 표** 항목을 늘린다.
모델은 "쓰지 말 것"을 구체적으로 적어줄 때 가장 잘 지킨다.

---

## T3 · 서비스 UI

### 목적
실험 과정이 **눈에 보이게** 만든다. 이 화면의 목적은 예쁜 게 아니라
*왼쪽엔 스킬이 없고 오른쪽엔 있다*가 보이는 것이다.

### 소유 경로
`ui/`

### 금지
- `harness/`, `experiments/` 수정 — UI는 `run_arm()` **하나만** 호출한다.
  다른 게 필요하면 mentor에게 요청한다. 이 규칙이 깨지면 두 트랙을 나눈 의미가 없어진다.

### 입력
- [`docs/architecture.md`](architecture.md)의 계약 규율
- 현재 `ui/app.py` — 3탭이 이미 동작한다

### 할 일 (골라서)
1. **②탭 개선** — 작업공간 파일 트리를 실제 디렉터리에서 읽어 그린다 (지금은 예상 목록)
2. **반복 실행** — 지금은 arm당 1회다. 3회 돌려 중앙값을 보여준다
3. **①탭** — 스토리보드의 `기본값 읽지 않음 / 리스트에서 읽음·읽지않음 선택`을 반영
4. **③탭** — 브리핑 두 개를 나란히 놓고 다른 부분을 강조
5. **관찰 기록** — 사람이 본 것을 `observation.md`로 저장하는 폼

### 완료 조건
- [ ] `ui/` 밖의 파일을 하나도 고치지 않았다
- [ ] `run_arm()` 외의 harness 함수를 부르지 않았다 (`gmail.load` 같은 읽기 헬퍼는 괜찮다)
- [ ] 실행 중 로그가 실시간으로 흐른다
- [ ] 실행된 `codex exec` 명령 전문을 화면에서 볼 수 있다
- [ ] 스냅샷 없이 켜도 안내 문구가 나오고 죽지 않는다
- [ ] PR에 화면 캡처 첨부

### 막혔을 때
Streamlit은 버튼을 누를 때마다 스크립트를 처음부터 다시 실행한다. 값을 유지하려면
`st.session_state`에 넣는다. 현재 코드에 예시가 있다.

---

## T4 · 실험 환경

### 목적
실험이 **믿을 만한지**를 책임진다. 케이스가 부실하면 위 세 사람의 숫자가 전부 의미 없어진다.

### 소유 경로
`experiments/cases.yaml`, `experiments/seed_gmail.py`

### 금지
- `experiments/metrics.py`, `ablation.py` 수정 (mentor 소유 — 채점 기준을 바꾸면 이전 결과와 비교가 안 된다)
- **실제 메일을 `cases.yaml`에 넣는 것.** 전부 지어낸 데이터여야 한다. 실제 회사명·사람 이름 금지

### 할 일
1. 케이스를 20건에서 **40건으로** 늘린다. 늘릴 때 다음을 지킨다
   - 라벨이 한쪽으로 쏠리지 않게 (지금은 notice가 많다)
   - **함정을 늘린다** — 키워드는 맞지만 라벨이 다른 것, 본문이 애매한 것
   - prompt injection 변종을 하나 더 (`C17` 참고)
2. `--mode insert`로 실제 Gmail에 주입하는 경로를 검증한다 ([docs/setup.md](setup.md) 7절)
3. 주입 → 수집 → ablation → `--cleanup`이 한 바퀴 도는지 확인한다

### 완료 조건
- [ ] 케이스 40건, 라벨별 최소 5건
- [ ] 각 케이스에 `expected`와 `note`가 있다
- [ ] `pytest -q` 통과 (정답 매핑이 깨지지 않았다)
- [ ] `--mode insert` → 수집 → `--cleanup`을 실제로 한 바퀴 돌렸다
- [ ] 실제 메일·실제 이름이 하나도 들어 있지 않다
- [ ] PR 본문에 늘린 케이스가 **무엇을 시험하는지** 적었다

### 막혔을 때
`--mode insert`가 안 되면 `--mode fixture`로 케이스 늘리는 일부터 한다. 그것만으로도 충분히 값이 있다.
Gmail 연결은 나중에 붙여도 된다.

---

## T5 · 사용자 플로우 문서

### 목적
스토리보드 PNG를 사람과 LLM이 함께 읽을 수 있는 명세로 유지한다.
**코드가 없다. git이 처음이면 여기부터 시작한다.**

### 소유 경로
`docs/user-flow/` — `flow.yaml`, `criteria.yaml`, `README.md`

### 금지
- **`docs/storyboard/`의 PNG 수정·삭제.** 원본은 증거다. 절대 건드리지 않는다
- 보드에 없는 규칙을 `criteria.yaml`에 확정으로 넣는 것 — 해석이면 `certainty: interpreted`를 붙인다
- **추론으로 안전 경계를 넓히는 것** (예: 발송을 허용하는 쪽으로 해석)

### 입력
- `docs/storyboard/`의 PNG 6장 (`overview.png`가 전체 그림)
- 현재 `flow.yaml`, `criteria.yaml`

### 할 일
1. PNG를 하나씩 열고 `flow.yaml`의 노드와 **한 줄씩 대조한다**
2. 빠진 노드·엣지를 추가하고, 각 노드의 `source.region`이 실제 위치와 맞는지 확인한다
3. `certainty`를 재검토한다. 그림에 그대로 있으면 `confirmed`, 읽어내며 해석이 들어갔으면 `interpreted`
4. `README.md`의 mermaid를 `flow.yaml`과 일치시킨다
5. **미해결 목록을 갱신한다** — 주황 별이 붙은 것, 보드에서도 안 정해진 것

### 완료 조건
- [ ] PNG 6장을 모두 열어 대조했다
- [ ] 모든 노드에 `source.asset`과 `certainty`가 있다
- [ ] `criteria.yaml`의 규칙이 `skills/*/references/`의 내용과 일치한다 (다르면 T1·T2에게 알린다)
- [ ] mermaid가 GitHub에서 정상 렌더된다 (PR 미리보기로 확인)
- [ ] 미해결 목록에 **누가 결정해야 하는지**가 적혀 있다
- [ ] PNG를 하나도 수정하지 않았다 (`git status`로 확인)

### 막혔을 때
그림이 애매해서 판단이 안 서면 **그것 자체가 산출물이다.** 억지로 해석하지 말고
`certainty: undecided`로 두고 미해결 목록에 "무엇이 애매한지"를 적는다.
정확한 질문을 남기는 것이 틀린 답을 적는 것보다 훨씬 값지다.

---

## PR 쓰는 법

```markdown
## 무엇을 했나
한두 줄.

## 숫자 (스킬·실험 task만)
| 지표 | 전 | 후 |
| --- | --- | --- |
| 정확도 | 0.85 | 0.95 |
| 근거 인용률 | 1.00 | 1.00 |

## 왜 그렇게 고쳤나
어떤 케이스가 틀렸고, 무엇을 바꿔서 맞게 됐는지.

## 확인한 것
- [ ] pytest -q 통과
- [ ] experiments/runs/ 가 커밋에 안 들어갔다
- [ ] 내 소유 경로 밖을 안 건드렸다
```

**숫자가 나빠졌어도 그대로 적는다.** 결과를 숨기면 다음 사람이 같은 곳에서 또 막힌다.
"이렇게 해봤는데 안 됐다"는 이 프로젝트에서 완전히 유효한 PR이다.
