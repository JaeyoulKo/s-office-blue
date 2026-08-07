# Email Archive Runtime

The runtime keeps Gmail ingestion, LLM extraction, deterministic record matching, and Excel persistence separate.

```text
Gmail MCP → GmailGateway → GmailAdapter → EmailThread
EmailThread → ArchiveAnalyzer → ExcelRecordRepository search
→ RecordMatcher → new/update/ambiguous → preview → approved atomic write
```

## Current capability

No Gmail message/thread/attachment MCP tool is available in the current Codex environment. `UnavailableGmailGateway` reports that state and no production mock is substituted. A future `McpGmailGateway` must be added only after the real MCP tool schema is known.

No connected spreadsheet document session is available. The approved fallback is a repository-local `.xlsx` workbook. Paths outside the repository are rejected.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

## Run

Streamlit review UI:

```bash
streamlit run streamlit_app.py
```

The UI uses `tests/fixtures` only as a temporary development input provider while Gmail MCP is
unavailable. `Analyze Archive` is preview-only. Only an explicit `Save Archive` click writes to the
repository-local `artifacts/email_archive_streamlit.xlsx` workbook. Ambiguous matches show candidate
evidence and disable saving.

CLI preview does not create or modify a workbook:

```bash
python -m archive.cli --input tests/fixtures/thread_initial.json \
  --analysis-fixture tests/fixtures/analysis_initial.json
```

Explicitly approved local write:

```bash
python -m archive.cli --input tests/fixtures/thread_initial.json \
  --analysis-fixture tests/fixtures/analysis_initial.json \
  --workbook data/email_archive.xlsx --write
```

For real LLM analysis, omit `--analysis-fixture`, set `OPENAI_API_KEY`, and optionally set `OPENAI_MODEL`. The implementation uses OpenAI Responses Structured Outputs and validates the result as `ThreadAnalysis`.

`--gmail-thread-id` currently returns a clear unavailable error. It does not fabricate Gmail data.

## Workbook repository

The workbook contains `Records`, `Action Items`, `Attachments`, `Source Emails`, and `Change History`. Updates retain the existing Record ID, replace the current child rows for that record, and append new change-history rows. Writes use a temporary file, reopen and validate it, then atomically replace the target workbook.
