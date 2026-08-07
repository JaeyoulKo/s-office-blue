from __future__ import annotations

import re

from .models import ArchiveRecord, EmailThread, MatchEvidence, RecordCandidate, RecordMatch


class RecordMatcher:
    """Conservative deterministic matching based on the Skill rules."""

    def match(
        self,
        thread: EmailThread,
        proposed: ArchiveRecord,
        existing_records: list[ArchiveRecord],
    ) -> RecordMatch:
        candidates: list[RecordCandidate] = []
        strong_candidates: list[RecordCandidate] = []

        thread_references = set(proposed.reference_ids)
        for record in existing_records:
            evidence: list[MatchEvidence] = []
            conflicts: list[MatchEvidence] = []
            strong = False

            source_thread_ids = {source.thread_id for source in record.source_emails}
            if thread.thread_id in source_thread_ids:
                strong = True
                evidence.append(
                    MatchEvidence(
                        field="thread_id",
                        current_value=thread.thread_id,
                        existing_value=thread.thread_id,
                        source="source_emails",
                    )
                )

            record_references = set(record.reference_ids)
            shared_references = sorted(thread_references & record_references)
            if shared_references:
                strong = True
                evidence.append(
                    MatchEvidence(
                        field="reference_ids",
                        current_value=shared_references,
                        existing_value=shared_references,
                        source="thread/reference_ids",
                    )
                )
            elif thread_references and record_references:
                conflicts.append(
                    MatchEvidence(
                        field="reference_ids",
                        current_value=sorted(thread_references),
                        existing_value=sorted(record_references),
                        source="thread/reference_ids",
                    )
                )

            if _normalized_title(proposed.title) == _normalized_title(record.title):
                evidence.append(
                    MatchEvidence(
                        field="title",
                        current_value=proposed.title,
                        existing_value=record.title,
                        source="normalized title",
                    )
                )
            if proposed.requester != "unknown" and proposed.requester == record.requester:
                evidence.append(
                    MatchEvidence(
                        field="requester",
                        current_value=proposed.requester,
                        existing_value=record.requester,
                        source="thread analysis",
                    )
                )
            shared_participants = sorted(set(proposed.participants) & set(record.participants))
            if shared_participants:
                evidence.append(
                    MatchEvidence(
                        field="participants",
                        current_value=shared_participants,
                        existing_value=shared_participants,
                        source="thread analysis",
                    )
                )

            if evidence:
                candidate = RecordCandidate(
                    record_id=record.record_id,
                    matching_evidence=evidence,
                    conflicting_evidence=conflicts,
                    confidence="high" if strong and not conflicts else "medium" if evidence else "low",
                )
                candidates.append(candidate)
                if strong and not conflicts:
                    strong_candidates.append(candidate)

        if len(strong_candidates) == 1:
            selected = strong_candidates[0]
            return RecordMatch(
                search_status="completed",
                decision="same_record",
                selected_record_id=selected.record_id,
                candidates=candidates,
            )
        if len(strong_candidates) > 1 or candidates:
            return RecordMatch(
                search_status="completed",
                decision="ambiguous",
                candidates=candidates,
                user_confirmation_required=True,
            )
        return RecordMatch(search_status="completed", decision="new_record")


def _normalized_title(value: str) -> str:
    value = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip().casefold()
