# Email Archive Skill A/B 실험

## 실험 목적과 통제 조건

합성 Email Thread에서 `email-archive-agent` Skill이 최신 상태, 변경 이력, company-specific
rule과 승인 gate를 얼마나 안정적으로 복원하는지 비교한다. `presentation_very_hard_01`부터
`05`까지 각각 다른 정책 상황을 사용한다.

두 조건은 `gpt-5.4`, reasoning effort `low`, 입력 Thread, base task, output schema를 동일하게
사용한다. WITH_SKILL에만 `dev/03-discussion-email-review/work/skills`를 임시 workspace의
`.agents/skills/email-archive-agent`로 설치한다. WITHOUT_SKILL에는 회사 정책과 Skill의 세부
정규화 지침을 제공하지 않는다. 양쪽 결과에는 같은 공통 validator와 CSV 직렬화를 적용하며
조건별 후처리는 없다.

## 출력 schema와 정규화

| 필드 | 내부 JSON | 정규화 |
| --- | --- | --- |
| `thread_id` | string | 입력 Thread ID 그대로 사용 |
| `발신자` | string | 최신 메시지의 `이름 <주소>` |
| `날짜` | string | 최신 메시지 날짜 `YYYY-MM-DD` |
| `Topic` | string | 핵심 안건 한 문장 |
| `금액` | integer/null | 최신 유효 금액의 최소 통화 단위; 불명확하면 null |
| `통화` | string/null | ISO 4217 코드 또는 null |
| `Business Impact` | object | `confirmed`와 `estimated` 배열 분리 |
| `Thread 진행 중 변경된 내용` | array | `{field, from, to}` 객체 배열 |
| `결정된 내용` | array | 확정 근거가 있는 사항만 포함 |
| `Open Item` | array | 현재 미승인·미확정 항목만 포함 |
| `승인 상태` | string | `APPROVED`, `REAPPROVAL_REQUIRED`, `PENDING`, `REJECTED`, `NOT_APPLICABLE`, `UNKNOWN` |
| `적용 규칙` | array | WITH_SKILL이 trigger한 AR ID의 정렬 배열; 없으면 `[]` |

내부 검증 CSV에서는 배열과 객체를 compact JSON 문자열로 직렬화한다. 금액·날짜·통화·승인 상태에는
설명 문장을 넣지 않는다. `(thread_id, condition)`을 key로 upsert하고 thread ID와
WITH_SKILL/WITHOUT_SKILL 순으로 정렬하므로 반복 실행해도 중복 행이 누적되지 않는다.

## 01~05 시나리오와 정책 설계

| Fixture / Thread | 최신 메시지 | 최초 → 최신 금액 | 최신 날짜 | 적용 대상 규칙 | 기대 상태 |
| --- | --- | --- | --- | --- | --- |
| `01` / `thread-pvh01` | `pvh01-m8` | 280,000,000 → 318,000,000 KRW; 중간 승인 300,000,000 | 2026-10-19 | AR-01, AR-06 | 6% 증액으로 `REAPPROVAL_REQUIRED`; Compliance 완료는 별도 gate |
| `02` / `thread-pvh02` | `pvh02-m8` | 다온비전 420,000,000 → 405,000,000 KRW | 2026-11-18 | AR-02, AR-05, AR-10 | preferred vendor와 final vendor를 구분하고 Finance gate `PENDING` |
| `03` / `thread-pvh03` | `pvh03-m8` | 560,000,000 → 530,000,000 KRW | 2026-12-09 | AR-03, AR-05, AR-06, AR-10 | budget·Legal·준비 완료와 투자위원회 승인 `PENDING` 구분 |
| `04` / `thread-pvh04` | `pvh04-m8` | 300,000,000 → 303,000,000 KRW | 2027-01-08 | AR-04, AR-05 | 1% 증액이어도 Software→Hardware 포함 scope 변경으로 `REAPPROVAL_REQUIRED` |
| `05` / `thread-pvh05` | `pvh05-m8` | 75,000,000 → 75,000,000 KRW | 2027-02-03 | AR-06, AR-07, AR-09 | Vendor·계약조건 변경으로 Legal을 reopen하고 contract execution `PENDING` |

기존 AR-01~AR-10으로 다섯 상황을 평가할 수 있어 새 회사 규칙은 추가하지 않았다. 모든 회사,
인물, 주소와 업무 내용은 합성 데이터이며 이메일 주소는 `.example` 도메인을 사용한다.

## 실제 A/B 결과

| Fixture / Thread | 적용 규칙(WITH) | WITH_SKILL 판단 | WITHOUT_SKILL 판단 | 업무적으로 의미 있는 차이 | 형식/금액/날짜/상태 |
| --- | --- | --- | --- | --- | --- |
| `01` / `thread-pvh01` | AR-01, AR-03, AR-05, AR-06, AR-10 | 6% 증액을 복원하고 `REAPPROVAL_REQUIRED` | 최신 금액은 찾았지만 `PENDING`; 재승인을 Open Item으로 식별하지 않음 | 있음: AR-01과 승인 유효성 판단 | 준수 / 318000000 / 2026-10-19 / 판정 |
| `02` / `thread-pvh02` | AR-02, AR-05, AR-10 | preferred vendor일 뿐 Finance 승인 전 final vendor가 아님을 명시 | preferred vendor와 Finance 검토 대기를 함께 기록 | 제한적: 최종 상태는 둘 다 `PENDING`; Skill이 gate 의미와 규칙 근거를 더 명시적으로 연결 | 준수 / 405000000 / 2026-11-18 / 판정 |
| `03` / `thread-pvh03` | AR-03, AR-05, AR-06, AR-09, AR-10 | budget·Legal·준비와 투자위원회 승인을 분리해 `PENDING` | 동일하게 투자위원회 승인을 Open Item으로 구분 | 차이 없음: 일반 모델도 핵심 gate와 변경 이력을 복원 | 준수 / 530000000 / 2026-12-09 / 판정 |
| `04` / `thread-pvh04` | AR-04 | scope category 변경을 근거로 재승인을 확정 | 상태 enum은 재승인이나 Open Item에서는 재승인 필요 여부가 미확정이라고 표현 | 있음: WITH는 AR-04로 일관된 확정 판단, WITHOUT는 내부 표현이 불일치 | 준수 / 303000000 / 2027-01-08 / 판정 |
| `05` / `thread-pvh05` | AR-07, AR-09, AR-10 | 새 Vendor의 Legal·계약 gate를 `PENDING`으로 판정 | Legal·계약 미완료를 찾았지만 전체 상태를 `REAPPROVAL_REQUIRED`로 과대 판정 | 있음: AR-07 단독은 gate reopen이지 자동 재승인이 아니라는 상태 매핑 | 준수 / 75000000 / 2027-02-03 / 판정 |

단순 표현 차이는 성과로 계산하지 않았다. 03은 의미 있는 판단 차이가 없고, 02도 결과 상태와
핵심 Open Item이 같아 차이가 제한적이다.

## 폴더 구조와 주요 파일

```text
experiments/ablation/skill_ab_test/
├── README.md                 # 실험 설계와 실제 평가
├── runner.py                 # 동일 조건 A/B Codex 실행
├── result_schema.py          # typed schema와 공통 validator
├── batch_run.py              # 01~05 일괄 실행 및 결과 교체
├── validate_results.py       # 제출 CSV 검증
├── excel_export.py           # 내부 CSV 저장과 사용자용 XLSX 생성
├── presentation.py           # 사용자 화면·Excel용 값 변환
├── streamlit_app.py          # 이메일 본문과 A/B 비교 UI
├── models.py                 # Email Thread 데이터 모델
├── synthetic_fixtures.py     # fixture 로딩과 그룹화
├── gmail_adapter.py          # 이미 가져온 Gmail 형식 정규화; live Gmail 비활성
├── fixtures/                 # presentation_very_hard_01~05 합성 Thread
└── results/email_archive_ab_results.csv
```

UI와 제출 실험에는 `presentation_very_hard_01`부터 `05`까지 정확히 다섯 fixture만 유지한다.
각 fixture는 승인·정책·최신값이 충돌하는 합성 Thread다.

## 사용자 화면과 Excel 다운로드

상단의 **이메일 Thread 보기**를 열면 메시지를 시간순으로 확인할 수 있다. 각 메시지는 별도
하위 expander에서 제목, 발신자, 날짜, 본문과 첨부파일명만 표시하며 내부 ID와 raw JSON은
노출하지 않는다.

A/B 결과는 발신자, 날짜, Topic, 화면용 금액, Business Impact, 변경 내용, 결정 내용과
Open Item만 좌우에 표시한다. 내부 검증에 필요한 승인 상태, 적용 규칙, thread ID, 모델 설정과
실행 시간은 화면에서 숨긴다. **A 결과 Excel 다운로드**는 현재 선택한 fixture의 WITH_SKILL
결과 한 행만 실제 `.xlsx`로 생성한다. 금액은 숫자 셀, 날짜는 Excel 날짜 셀로 저장하고 승인
상태·적용 규칙과 실행 metadata는 제외한다.

## 실행과 결과 활용

01~05 전체를 실행하고 결과 10행을 교체 저장한다.

```bash
python -m experiments.ablation.skill_ab_test.batch_run
```

단일 fixture를 UI에서 확인한다.

```bash
python -m streamlit run experiments/ablation/skill_ab_test/streamlit_app.py
```

제출 CSV를 검증한다.

```bash
python -m experiments.ablation.skill_ab_test.validate_results
```

내부 결과 CSV의 scalar 필드는 분석과 DB 컬럼에 적재할 수 있다. 복합 필드는 JSON parser로 읽어
배열·객체 컬럼에 적재하거나 별도 change/open-item 테이블로 펼친다. 빈 금액과 통화는 0이나
빈 통화로 추정하지 말고 null로 취급한다.

## 테스트 및 검증 결과

- 01~05 실제 A/B 10건을 `gpt-5.4`, low로 실행하고 schema 검증 후 저장했다.
- 날짜, 정수/null 금액, ISO 통화, 승인 enum, 복합 JSON 형식을 검증했다.
- 각 Thread에 WITH_SKILL/WITHOUT_SKILL 한 행씩 있고 중복 key가 없음을 검증했다.
- WITH_SKILL의 핵심 적용 규칙과 WITHOUT_SKILL의 빈 규칙 배열을 검증했다.
- 공통 prompt/schema, CSV 정렬·upsert·원자적 저장과 Python 문법을 검증했다.

## 한계점

- 실행 결과는 비결정적 모델 출력이므로 반복 실행 시 설명 배열의 항목과 세부 AR 목록이 달라질
  수 있다. typed schema와 핵심 rule assertion은 이를 별도로 검증한다.
- 02는 일반 모델도 preferred vendor와 Finance 대기를 구분해 차이가 제한적이고, 03은 의미 있는
  업무 판단 차이가 없었다. 더 큰 차이를 만들기 위해 fixture에 정답 문구나 새 정책을 넣지 않았다.
- 05의 두 조건 모두 ground truth상 resolved로 분류된 tag mapping과 measurement owner를 Open
  Item으로 남겼다. 후속 실험에서는 이 lifecycle 복원 정확도를 별도 평가해야 한다.
- 자동 점수는 제공하지 않으며 결과의 정책 적합성은 fixture ground truth와 사람이 함께 검토한다.
