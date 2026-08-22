`input.json`을 읽고 제공된 국문 taxonomy에 따라 이메일을 분류하세요.

`case_id`, `label`, `summary`, `evidence`, `missing_information`,
`recommended_action`, `safety_flags`, `errors`, `urgency` 필드가 있는 JSON만 반환하세요.
`urgency`는 `high`, `medium`, `low` 중 하나입니다.
Gmail을 호출하거나 외부 시스템을 변경하지 마세요.
