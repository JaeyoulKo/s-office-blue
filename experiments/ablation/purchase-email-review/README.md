# Purchase email review ablation

개발 중인 `purchase-email-review` Skill의 적용 전후를 같은 조건에서 사람이 비교한다.

```powershell
python experiments/ablation/run.py purchase-email-review
```

- baseline: 대상 Skill 없음
- treatment: `dev/02-purchase-review/work/purchase-email-review/`만 노출
- 공통 조건: 입력, prompt, `gpt-5.4`, reasoning effort `low`
- 결과: `experiments/instances/<run-id>/`

이 실험에는 구매 판단이나 결과 보정용 Python 코드를 두지 않는다.
