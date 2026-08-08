# Gmail test seed

이 폴더는 가상 메일 시나리오와 향후 테스트 계정 injection adapter를 두는 자리다.

현재 `inject.py`는 Gmail API를 호출하지 않고 RFC 822 `.eml` 파일만
`data/gmail_seed/outbox/`에 만든다. 실제 injection을 추가할 때는 별도 테스트 계정,
`[OFFICE-BLUE-TEST]` 제목, 전용 label, 명시적 write 확인을 모두 요구한다.

```powershell
python data/gmail_seed/inject.py
```
