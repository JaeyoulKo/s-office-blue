# Office Blue

Office Blue는 기존 구매 이메일 업무 규칙을 기능 단위의 국문 Skill로 나누고, 같은 Codex
runner를 Streamlit 서비스와 일회성 A/B 실험에서 사용하는 템플릿입니다.

```text
skills/                  승인된 국문 Skill 원본
main_service/            Streamlit 서비스와 공용 codex exec runner
dev/                     task별 작업 공간
experiments/ablation/    반복 가능한 실험 정의
experiments/instances/   실행 결과, Git 제외
data/                    합성 데이터, Gmail snapshot, test seed
shared/                  공통 taxonomy
```

`shared/taxonomy.md`의 분류 유형은 `skills/email-classifier/references/decision-rules.md`와
같아야 합니다. 호출자가 준 taxonomy가 Skill 자체 규칙을 이기기 때문에, 둘이 갈라지면 분류 후
라우팅 규칙의 일부가 도달 불가능해집니다. `tests/test_emails.py`가 이를 검사합니다.

## Skill 구성

- `email-classifier`: 메일 분류와 근거·누락 정보 정리
- `purchase-email-review`: 구매·승인·계약 검토와 보완/승인 회신 템플릿
- `discussion-email-review`: 논의·질의 스레드 판단과 회신 템플릿

기존 `purchase-email-agent`의 규칙과 템플릿이 이동한 위치는
`docs/skill-migration.md`에서 확인할 수 있습니다.

## 실행

Python 3.10 이상과 로그인된 Codex CLI가 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[ui]"
streamlit run main_service/streamlit_app.py
```

UI는 `service.py`만 호출하며 runner가 선택한 Skill을 임시 `.agents/skills/`에 배치한 뒤
읽기 전용·ephemeral `codex exec`를 실행합니다.

### 메일 목록 화면

`📥 메일 목록` 탭은 이메일 여러 건을 한 번에 분류합니다. `service.classify_emails()`가
`ThreadPoolExecutor`로 건당 `codex exec` 하나씩을 동시에 돌리며, 진행 콜백은 호출자
스레드에서만 실행됩니다. 한 건이 실패해도 배치는 멈추지 않고 실패 목록에 모입니다.

### Gmail 조회

`main_service/gmail_mcp.py`가 `~/.codex/config.toml`에 등록된 로컬 Gmail MCP 서버를
stdio JSON-RPC로 **직접** 호출합니다. 여기에는 LLM이 없습니다 — 안 읽은 메일 목록을 가져오는
데는 판단이 없고, 모델을 끼우면 느려지는 데다(50건 기준 수 분 vs 13초) 도구를 못 찾았을 때
스키마에 맞는 빈 목록이 조용히 나옵니다. 읽기 도구만 호출하며 발송·라벨 변경·삭제 경로는
모듈에 존재하지 않습니다.

refresh token이 만료되면(External/Testing 앱은 7일) 조회가 실패합니다. 이때는 빈 목록이
아니라 실패 이유가 화면에 표시됩니다.

동시 실행 수는 16이 상한입니다. 30건 실측에서 4→8은 건당 시간이 그대로인 채 소요가 절반이
됐고 16에서 56.6초로 가장 빨랐지만, 30까지 올리면 소요가 58.6초로 되레 나빠지고 건당 시간이
23.7초에서 49.4초로 2배가 됩니다. 포화 지점이 16이라 "메일 수만큼" 띄우는 건 손해입니다.

순서는 모델이 아니라 `main_service/emails.py`가 결정합니다. 모델은 `urgency`를 판단하고,
금액순 상위·세금·지급기일 초과 같은 규칙이 하한을 깔며, 최종 비교자는 입력 순서까지
tiebreak으로 써서 같은 입력이 항상 같은 순서가 되게 합니다. 각 건의 긴급도 근거는
`[규칙]`과 `[AI]`로 출처를 구분해 표시합니다.

## A/B 실험

```powershell
python experiments/ablation/run.py email-classifier
```

테스트는 표준 `unittest`로 돌립니다. `tests/`에 `__init__.py`가 없어 `discover`는 실패하므로
모듈을 명시합니다.

```powershell
python -m unittest tests.test_gmail_mcp tests.test_emails tests.test_service
```

동일한 요청문과 입력을 baseline에는 Skill 없이, treatment에는 `email-classifier`만 둔 채
실행합니다. 결과는 `experiments/instances/<run-id>/`에 저장하며 자동 점수나 통계적 결론을
만들지 않습니다.

새 작업은 `dev/<task-id>/work/`에서 진행하고 검토된 결과만 정식 폴더로 승격합니다. 실제
Gmail snapshot, 실행 결과, 토큰과 provider ID는 Git에 저장하지 않습니다.
