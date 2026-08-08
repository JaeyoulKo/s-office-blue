# Office Blue

Office Blue는 이메일 업무 Skill을 작은 단위로 개발하고 Streamlit 서비스 또는 일회성
A/B 실험에서 같은 Codex runner로 실행하는 템플릿입니다.

```text
skills/                  승인된 Skill 원본
main_service/            Streamlit 서비스와 공용 codex exec runner
dev/                     task별 작업 공간
experiments/ablation/    반복 가능한 실험 정의
experiments/instances/   실행 때마다 생기는 결과, Git 제외
data/                    합성 데이터, Gmail snapshot, test seed
shared/                  공통 taxonomy
```

## 실행

Python 3.10 이상, 로그인된 Codex CLI가 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[ui]
streamlit run main_service/streamlit_app.py
```

화면에서 합성 메일을 선택하고 분류, 구매 검토, 보완 초안을 차례로 실행합니다. UI는
`service.py`만 호출하고, runner가 선택한 Skill을 임시 `.agents/skills/` 공간에 배치한 뒤
읽기 전용·ephemeral `codex exec`를 실행합니다.

## A/B 실험

```powershell
python experiments/ablation/email-classifier/run.py
```

동일한 prompt와 입력을 baseline에는 Skill 없이, treatment에는 `email-classifier`만 둔 채
실행합니다. 결과는 `experiments/instances/<run-id>/`에 저장되며 자동 점수나 통계적 결론을
만들지 않습니다.

## 작업 승격

새 작업은 먼저 `dev/<task-id>/TASK.md` 범위 안에서 작성합니다. 검토가 끝나면 필요한 파일만
`skills/`, `main_service/`, `experiments/`로 옮깁니다. 폴더가 일차적인 업무 경계이며 Git
커밋과 PR은 변경 이력을 남기는 최소 단위로 사용합니다.

합성 데이터는 `data/synthetic/`에 커밋할 수 있습니다. 실제 Gmail snapshot, 실행 결과,
토큰과 provider ID는 커밋하지 않습니다. `data/gmail_seed/`의 현재 도구는 테스트 메일을
`.eml`로 렌더링할 뿐 Gmail 쓰기를 수행하지 않습니다.
