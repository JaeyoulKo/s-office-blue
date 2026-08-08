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

## A/B 실험

```powershell
python experiments/ablation/email-classifier/run.py
```

동일한 요청문과 입력을 baseline에는 Skill 없이, treatment에는 `email-classifier`만 둔 채
실행합니다. 결과는 `experiments/instances/<run-id>/`에 저장하며 자동 점수나 통계적 결론을
만들지 않습니다.

새 작업은 `dev/<task-id>/work/`에서 진행하고 검토된 결과만 정식 폴더로 승격합니다. 실제
Gmail snapshot, 실행 결과, 토큰과 provider ID는 Git에 저장하지 않습니다.
