# 05 · 공용 A/B Harness

- 목적: Skill별 Python 실행 코드를 만들지 않고 동일한 Codex Harness로 A/B 실험을 실행한다.
- 작업 위치: `dev/05-ablation-harness/work/`
- 입력: 실험별 `experiment.json`, `prompt.md`, 합성 데이터
- 승격 대상: `experiments/ablation/run.py`, `main_service/codex_runner.py`
- 완료: baseline과 treatment의 유일한 차이가 대상 Skill 노출 여부이다.
