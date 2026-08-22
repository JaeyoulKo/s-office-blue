# 09 · A/B 실행 성능 개선

- 목적: 독립적인 baseline과 treatment를 병렬 실행하고 장시간 정체를 제한한다.
- 작업 위치: `dev/09-ablation-performance/work/`
- 입력: 공용 ablation Harness, 구매 이메일 A/B Streamlit UI
- 승격 대상: `experiments/ablation/run.py`, `experiments/ablation/streamlit_app.py`, 실험 설정
- 완료: 동일 입력·모델·reasoning 및 Skill 격리를 유지하면서 조건별 150초 timeout과 진행 상태를 제공한다.
