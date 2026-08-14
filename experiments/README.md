# Experiments

`ablation/`에는 다시 실행할 수 있는 실험 정의를 두고 `instances/`에는 매번 생성되는 입력,
baseline, treatment, 관찰 메모를 둔다. instance는 Git에 커밋하지 않는다.

서비스와 실험은 모두 `main_service/codex_runner.py`를 사용한다. 실험은 품질 점수나 통계적
유의성을 계산하지 않고 사람이 차이를 기록하는 exploratory 비교다.

모든 실험은 공용 Harness를 사용한다.

```powershell
python experiments/ablation/run.py email-classifier
```

실험 폴더에는 실행 코드 대신 `experiment.json`, `prompt.md`, 관찰 양식만 둔다. baseline과
treatment는 입력, 요청문, 모델, reasoning effort가 같고 treatment에만 대상 Skill을 노출한다.
