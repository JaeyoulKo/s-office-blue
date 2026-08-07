from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from .analyzer import ArchiveAnalyzer
from .models import (
    ActionItem,
    ArchiveRecord,
    ArchiveResult,
    EmailThread,
    FieldChange,
    RecordUpdate,
    SourceEmail,
    StorageResult,
    ThreadAnalysis,
    UNKNOWN,
)
from .record_matcher import RecordMatcher
from .storage import ExcelRecordRepository


class ArchiveService:
    def __init__(
        self,
        analyzer: ArchiveAnalyzer,
        repository: ExcelRecordRepository,
        matcher: RecordMatcher | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.repository = repository
        self.matcher = matcher or RecordMatcher()

    def process(self, thread: EmailThread, write: bool = False) -> ArchiveResult:
        analysis = self.analyzer.analyze(thread)
        proposed = self._build_record(thread, analysis)
        existing_records = self.repository.list_records()
        match = self.matcher.match(thread, proposed, existing_records)
        storage = StorageResult(
            requested=write,
            user_approved=write,
            destination=str(self.repository.workbook_path),
        )

        if match.decision == "ambiguous":
            return ArchiveResult(
                result_status="additional_confirmation_required",
                archive_decision=self._archive_decision(write),
                input_inventory=self._input_inventory(thread),
                thread_analysis=analysis,
                record_match=match,
                archive_record=proposed,
                conflicts=analysis.conflicts,
                limitations=analysis.limitations,
                storage=storage,
            )

        if match.decision == "new_record":
            proposed.record_id = proposed.record_id_candidate
            result = ArchiveResult(
                result_status="new_record_ready",
                archive_decision=self._archive_decision(write),
                input_inventory=self._input_inventory(thread),
                thread_analysis=analysis,
                record_match=match,
                archive_record=proposed,
                conflicts=analysis.conflicts,
                limitations=analysis.limitations,
                storage=storage,
            )
            if write:
                self._persist(result, proposed, [], "create")
            return result

        existing = next(
            record for record in existing_records if record.record_id == match.selected_record_id
        )
        updated, changes, update = self._merge(existing, proposed, thread)
        result = ArchiveResult(
            result_status="record_update_ready",
            archive_decision=self._archive_decision(write),
            input_inventory=self._input_inventory(thread),
            thread_analysis=analysis,
            record_match=match,
            archive_record=updated,
            record_update=update,
            conflicts=analysis.conflicts,
            limitations=analysis.limitations,
            storage=storage,
        )
        if write:
            self._persist(result, updated, changes, "update")
        return result

    def _persist(
        self,
        result: ArchiveResult,
        record: ArchiveRecord,
        changes: list[FieldChange],
        operation: str,
    ) -> None:
        try:
            self.repository.save(record, changes, operation)
        except Exception as error:
            result.storage.operation = operation
            result.storage.error = str(error)
            raise
        result.result_status = "saved"
        result.storage.executed = True
        result.storage.operation = operation
        result.storage.saved_record_id = record.record_id
        result.storage.completed_at = _now()

    def _build_record(self, thread: EmailThread, analysis: ThreadAnalysis) -> ArchiveRecord:
        attachments = analysis.attachments or [
            attachment.model_copy(deep=True)
            for message in thread.messages
            for attachment in message.attachments
        ]
        source_type = {
            "gmail_mcp": "mcp_tool_result",
            "test_fixture": "test_fixture",
            "normalized_input": "user_provided",
        }[thread.source_type]
        sources = [
            SourceEmail(
                message_id=message.message_id,
                thread_id=message.thread_id,
                subject=message.subject,
                sent_at=message.sent_at.isoformat(),
                source_type=source_type,
            )
            for message in thread.messages
        ]
        reference_ids = _unique(
            reference for message in thread.messages for reference in message.reference_ids
        )
        due_dates = _unique(
            item.due_date for item in analysis.action_items if item.due_date != UNKNOWN
        )
        stable_key = thread.thread_id + "|" + thread.messages[0].message_id
        record_id = "ARC-" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16].upper()
        return ArchiveRecord(
            record_id_candidate=record_id,
            title=_known(analysis.subject, thread.messages[-1].subject),
            thread_summary=analysis.thread_summary,
            requester=analysis.requester,
            participants=analysis.participants,
            start_date=_known(analysis.start_date, thread.messages[0].sent_at.isoformat()),
            latest_update_date=_known(
                analysis.latest_update_date, thread.messages[-1].sent_at.isoformat()
            ),
            key_points=analysis.key_points,
            decisions=analysis.decisions,
            action_items=analysis.action_items,
            due_dates=due_dates,
            important_numbers=analysis.important_numbers,
            attachments=attachments,
            open_items=analysis.open_items,
            current_status=analysis.current_status,
            source_emails=sources,
            reference_ids=reference_ids,
            last_updated=_now(),
        )

    def _merge(
        self,
        existing: ArchiveRecord,
        proposed: ArchiveRecord,
        thread: EmailThread,
    ) -> tuple[ArchiveRecord, list[FieldChange], RecordUpdate]:
        updated = existing.model_copy(deep=True)
        changes: list[FieldChange] = []
        evidence_message = thread.messages[-1].message_id
        changed_at = thread.messages[-1].sent_at.isoformat()
        unchanged: list[str] = []

        scalar_fields = [
            "title",
            "thread_summary",
            "requester",
            "latest_update_date",
            "current_status",
        ]
        for field in scalar_fields:
            old = getattr(existing, field)
            new = getattr(proposed, field)
            if new == UNKNOWN or new == old:
                unchanged.append(field)
                continue
            setattr(updated, field, new)
            changes.append(
                _change(field, old, new, changed_at, evidence_message, "latest thread analysis")
            )

        for field in ["participants", "key_points", "decisions", "open_items", "reference_ids"]:
            old_values = getattr(existing, field)
            merged_values = _unique([*old_values, *getattr(proposed, field)])
            setattr(updated, field, merged_values)
            if merged_values != old_values:
                changes.append(
                    _change(field, old_values, merged_values, changed_at, evidence_message, "new thread information")
                )
            else:
                unchanged.append(field)

        updated.action_items, action_changes, new_actions, completed_actions = _merge_actions(
            existing.action_items,
            proposed.action_items,
            changed_at,
            evidence_message,
        )
        changes.extend(action_changes)
        updated.due_dates = _unique(
            item.due_date for item in updated.action_items if item.due_date != UNKNOWN
        )
        updated.important_numbers = _merge_models(existing.important_numbers, proposed.important_numbers)
        updated.attachments = _merge_models(existing.attachments, proposed.attachments)
        updated.source_emails = _merge_models(existing.source_emails, proposed.source_emails)
        updated.start_date = min(_date_values(existing.start_date, proposed.start_date))
        updated.record_id = existing.record_id
        updated.record_id_candidate = existing.record_id
        updated.last_updated = _now()

        new_decisions = [item for item in proposed.decisions if item not in existing.decisions]
        update = RecordUpdate(
            target_record_id=existing.record_id,
            retained_summary=existing.thread_summary,
            proposed_current_record=updated,
            field_changes=changes,
            unchanged_fields=unchanged,
            new_decisions=new_decisions,
            new_action_items=new_actions,
            completed_action_items=completed_actions,
            unresolved_items=updated.open_items,
        )
        return updated, changes, update

    @staticmethod
    def _archive_decision(write: bool) -> dict[str, Any]:
        return {
            "recommendation": "archive_recommended",
            "user_selection": "selected",
            "rationale": [{"evidence": "archive processing requested", "source": "user", "evidence_status": "confirmed"}],
            "policy_basis": "email-archive-agent",
            "storage_approved": write,
        }

    @staticmethod
    def _input_inventory(thread: EmailThread) -> dict[str, Any]:
        return {
            "source_type": thread.source_type,
            "thread_id": thread.thread_id,
            "message_count": len(thread.messages),
            "attachment_count": sum(len(message.attachments) for message in thread.messages),
        }


def _merge_actions(
    old_items: list[ActionItem],
    new_items: list[ActionItem],
    changed_at: str,
    fallback_message_id: str,
) -> tuple[list[ActionItem], list[FieldChange], list[ActionItem], list[ActionItem]]:
    merged = [item.model_copy(deep=True) for item in old_items]
    index = {_action_key(item): position for position, item in enumerate(merged)}
    changes: list[FieldChange] = []
    added: list[ActionItem] = []
    completed: list[ActionItem] = []
    for incoming in new_items:
        key = _action_key(incoming)
        if key not in index:
            merged.append(incoming.model_copy(deep=True))
            added.append(incoming)
            changes.append(
                _change(
                    f"action_items[{key}]",
                    UNKNOWN,
                    incoming.model_dump(mode="json"),
                    changed_at,
                    incoming.source_message_id or fallback_message_id,
                    "new action item",
                    "added",
                )
            )
            continue
        current = merged[index[key]]
        for field in ["owner", "due_date", "status"]:
            old = getattr(current, field)
            new = getattr(incoming, field)
            if new == UNKNOWN or new == old:
                continue
            setattr(current, field, new)
            change_type = "completed" if field == "status" and new == "completed" else "changed"
            changes.append(
                _change(
                    f"action_items[{key}].{field}",
                    old,
                    new,
                    changed_at,
                    incoming.source_message_id or fallback_message_id,
                    f"action item {field} changed in thread",
                    change_type,
                )
            )
            if change_type == "completed" and current not in completed:
                completed.append(current)
        if incoming.source_message_id != UNKNOWN:
            current.source_message_id = incoming.source_message_id
    return merged, changes, added, completed


def _action_key(item: ActionItem) -> str:
    if item.action_id_candidate != UNKNOWN:
        return item.action_id_candidate
    return re.sub(r"\s+", " ", item.description).strip().casefold()


def _change(
    field: str,
    old: Any,
    new: Any,
    changed_at: str,
    source_message_id: str,
    reason: str,
    change_type: str = "changed",
) -> FieldChange:
    return FieldChange(
        field_path=field,
        change_type=change_type,
        previous_value=old,
        new_value=new,
        changed_at=changed_at,
        source_message_id=source_message_id,
        reason=reason,
    )


def _merge_models(old_items: list[Any], new_items: list[Any]) -> list[Any]:
    merged = [item.model_copy(deep=True) for item in old_items]
    seen = {item.model_dump_json() for item in merged}
    for item in new_items:
        serialized = item.model_dump_json()
        if serialized not in seen:
            merged.append(item.model_copy(deep=True))
            seen.add(serialized)
    return merged


def _known(preferred: str, fallback: str) -> str:
    return fallback if preferred == UNKNOWN else preferred


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _date_values(*values: str) -> list[str]:
    known = [value for value in values if value != UNKNOWN]
    return known or [UNKNOWN]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
