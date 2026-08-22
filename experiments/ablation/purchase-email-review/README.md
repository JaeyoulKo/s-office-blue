# Purchase email review ablation

개발 중인 `purchase-email-review` Skill의 적용 전후를 같은 조건에서 사람이 비교한다.

```powershell
python experiments/ablation/run.py purchase-email-review
```

Streamlit 비교 페이지는 다음 명령으로 실행한다.

```powershell
streamlit run experiments/ablation/purchase-email-review/streamlit_app.py --server.port 8502
```

- baseline: 대상 Skill 없음
- treatment: `dev/02-purchase-review/work/purchase-email-review/`만 노출
- 공통 조건: 입력, prompt, `experiment.json`의 `model`, reasoning effort `low`
- 실행: 두 조건을 병렬로 돌리므로 소요 시간은 둘 중 느린 쪽이다
- 조건별 상한: `experiment.json`의 `condition_timeout_seconds` (기본 150초)
- 처리 등급: `service_tier`가 `priority`면 대기 시간이 줄지만 사용량을 더 쓴다.
  모델과 출력은 같다. 한 번만 끄려면 `--service-tier ""`를 넘긴다.
- 결과: `experiments/instances/<run-id>/`

`--case` 없이 실행하면 `cases[0]`의 30건이 한 번에 한 요청으로 들어가 150초를 넘길 수 있다.
UI와 같은 1건 단위로 보려면 `--case`로 이메일 한 건을 넘긴다.

이 실험에는 구매 판단이나 결과 보정용 Python 코드를 두지 않는다.
