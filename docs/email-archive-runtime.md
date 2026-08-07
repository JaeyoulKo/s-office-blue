# Email Archive Runtime

The runtime keeps Gmail ingestion, LLM extraction, deterministic record matching, and Excel persistence separate.

```text
Gmail MCP → GmailGateway → GmailAdapter → EmailThread
EmailThread → ArchiveAnalyzer → ExcelRecordRepository search
→ RecordMatcher → new/update/ambiguous → preview → approved atomic write
```

## Current capability

The Archive UI reuses the team's authenticated, read-only Codex Gmail bridge. Inbox search uses
`fetch_gmail_snapshot()`. After a user selects a message, `fetch_gmail_thread()` reads every
accessible message for that exact thread ID, and `CodexGmailGateway` normalizes it through
`GmailAdapter` into `EmailThread`. The bridge does not send, draft, label, archive, or delete mail.

The current verified Gmail snapshot schema provides message/thread IDs, sender, recipients,
subject, body, received time, and attachment file names. It does not provide CC, reference IDs,
attachment MIME/ID, or attachment content. Those values remain empty or `unknown`, and attachment
content is marked `unverified` rather than treated as analyzed.

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

Live Gmail is the default input. `tests/fixtures` remains an explicit development/testing option.
`Analyze Archive` is preview-only. Only an explicit `Save Archive` click writes the exact previewed
thread and analysis to the repository-local `artifacts/email_archive_streamlit.xlsx` workbook.
Ambiguous matches show candidate evidence and disable saving.

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

## Workbook repository

The workbook contains `Records`, `Action Items`, `Attachments`, `Source Emails`, and `Change History`. Updates retain the existing Record ID, replace the current child rows for that record, and append new change-history rows. Writes use a temporary file, reopen and validate it, then atomically replace the target workbook.
