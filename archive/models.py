from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UNKNOWN = "unknown"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Attachment(StrictModel):
    attachment_id: str = UNKNOWN
    file_name: str
    file_type: Literal["pdf", "spreadsheet", "document", "image", "other", "unknown"] = "unknown"
    mime_type: str = UNKNOWN
    access_status: Literal["analyzed", "unverified", "failed"] = "unverified"
    summary: str = UNKNOWN
    extracted_text: str = UNKNOWN
    source_message_id: str = UNKNOWN


class EmailMessage(StrictModel):
    message_id: str
    thread_id: str
    subject: str = UNKNOWN
    sender: str = UNKNOWN
    recipients: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    sent_at: datetime
    body_text: str = UNKNOWN
    attachments: list[Attachment] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)


class EmailThread(StrictModel):
    thread_id: str
    messages: list[EmailMessage]
    source_type: Literal["gmail_mcp", "normalized_input", "test_fixture"] = "normalized_input"

    @field_validator("messages")
    @classmethod
    def require_messages(cls, value: list[EmailMessage]) -> list[EmailMessage]:
        if not value:
            raise ValueError("an email thread must contain at least one message")
        return sorted(value, key=lambda message: message.sent_at)

    @model_validator(mode="after")
    def validate_thread_ids(self) -> "EmailThread":
        if any(message.thread_id != self.thread_id for message in self.messages):
            raise ValueError("every message must belong to the thread")
        return self


class ChronologicalEvent(StrictModel):
    event_date: str = UNKNOWN
    event_type: Literal["request", "discussion", "change", "decision", "action", "completion"]
    summary: str
    source_message_id: str = UNKNOWN


class ActionItem(StrictModel):
    action_id_candidate: str = UNKNOWN
    description: str
    owner: str = UNKNOWN
    due_date: str = UNKNOWN
    status: Literal["open", "in_progress", "completed", "blocked", "unknown"] = "unknown"
    source_message_id: str = UNKNOWN


class ImportantNumber(StrictModel):
    label: str
    value: str = UNKNOWN
    unit_or_currency: str = UNKNOWN
    period: str = UNKNOWN
    source_message_id: str = UNKNOWN


class ThreadAnalysis(StrictModel):
    subject: str = UNKNOWN
    senders: list[str] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    email_dates: list[str] = Field(default_factory=list)
    requester: str = UNKNOWN
    participants: list[str] = Field(default_factory=list)
    start_date: str = UNKNOWN
    latest_update_date: str = UNKNOWN
    initial_request: str = UNKNOWN
    chronological_events: list[ChronologicalEvent] = Field(default_factory=list)
    key_discussions: list[str] = Field(default_factory=list)
    thread_summary: str = UNKNOWN
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    important_numbers: list[ImportantNumber] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    changes_in_thread: list[str] = Field(default_factory=list)
    current_status: str = UNKNOWN
    conflicts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SourceEmail(StrictModel):
    message_id: str
    thread_id: str
    subject: str = UNKNOWN
    sent_at: str
    source_type: Literal["user_provided", "mcp_tool_result", "test_fixture"]


class ArchiveRecord(StrictModel):
    record_id: str = UNKNOWN
    record_id_candidate: str = UNKNOWN
    title: str = UNKNOWN
    thread_summary: str = UNKNOWN
    requester: str = UNKNOWN
    participants: list[str] = Field(default_factory=list)
    start_date: str = UNKNOWN
    latest_update_date: str = UNKNOWN
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    due_dates: list[str] = Field(default_factory=list)
    important_numbers: list[ImportantNumber] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list)
    current_status: str = UNKNOWN
    source_emails: list[SourceEmail] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    last_updated: str = UNKNOWN


class MatchEvidence(StrictModel):
    field: str
    current_value: Any
    existing_value: Any
    source: str


class RecordCandidate(StrictModel):
    record_id: str
    matching_evidence: list[MatchEvidence] = Field(default_factory=list)
    conflicting_evidence: list[MatchEvidence] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"


class RecordMatch(StrictModel):
    search_status: Literal["completed", "search_unavailable", "partial"] = "completed"
    decision: Literal["same_record", "new_record", "ambiguous"]
    selected_record_id: str = UNKNOWN
    candidates: list[RecordCandidate] = Field(default_factory=list)
    user_confirmation_required: bool = False


class FieldChange(StrictModel):
    field_path: str
    change_type: Literal["added", "changed", "completed", "reopened", "removed"]
    previous_value: Any = UNKNOWN
    new_value: Any = UNKNOWN
    changed_at: str = UNKNOWN
    source_message_id: str = UNKNOWN
    reason: str


class RecordUpdate(StrictModel):
    target_record_id: str
    retained_summary: str = UNKNOWN
    proposed_current_record: ArchiveRecord
    field_changes: list[FieldChange] = Field(default_factory=list)
    unchanged_fields: list[str] = Field(default_factory=list)
    new_decisions: list[str] = Field(default_factory=list)
    new_action_items: list[ActionItem] = Field(default_factory=list)
    completed_action_items: list[ActionItem] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)


class StorageResult(StrictModel):
    requested: bool = False
    user_approved: bool = False
    tool_available: bool = True
    executed: bool = False
    destination: str = UNKNOWN
    operation: Literal["create", "update", "none"] = "none"
    saved_record_id: str = UNKNOWN
    tool_result_source: str = "local_excel"
    completed_at: str = UNKNOWN
    error: str = UNKNOWN


class ArchiveResult(StrictModel):
    result_status: Literal[
        "new_record_ready",
        "record_update_ready",
        "additional_confirmation_required",
        "archive_not_needed",
        "storage_tool_unavailable",
        "saved",
    ]
    archive_decision: dict[str, Any] = Field(default_factory=dict)
    input_inventory: dict[str, Any] = Field(default_factory=dict)
    thread_analysis: ThreadAnalysis
    record_match: RecordMatch
    archive_record: ArchiveRecord | None = None
    record_update: RecordUpdate | None = None
    excel_output: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    storage: StorageResult = Field(default_factory=StorageResult)
