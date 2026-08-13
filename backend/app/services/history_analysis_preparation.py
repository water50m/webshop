"""Prepare redacted local history snapshots for review before any AI analysis.

This module only reads ``history_*`` tables and writes local draft records.  It
has no network dependency and deliberately does not know about an AI provider.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import HistoryAnalysisBatch, HistoryAnalysisPreparation, HistoryMessage


_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("url", re.compile(r"https?://[^\s]+", re.IGNORECASE), "[URL]"),
    (
        "coordinates",
        re.compile(r"(?<!\d)\d{1,2}\.\d{4,}\s*,\s*\d{1,3}\.\d{4,}(?!\d)"),
        "[COORDINATES]",
    ),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE), "[EMAIL]"),
    (
        "name",
        re.compile(r"(?im)(?:(?:ชื่อ|name)\s*(?:คือ)?\s*[:：-]\s*)\S+"),
        "[NAME]",
    ),
    (
        "phone",
        re.compile(r"(?<!\d)(?:\+?66[-\s]?)?(?:0?\d(?:[-\s]?\d){7,9})(?!\d)"),
        "[PHONE]",
    ),
    (
        "address",
        re.compile(r"(?im)(?:(?:ที่อยู่|address)\s*(?:คือ)?\s*[:：-]?\s*)[^\n]+"),
        "[ADDRESS]",
    ),
    (
        "address",
        re.compile(r"(?i)(?:บ้านเลขที่|เลขที่|เลข|no\.?)\s*\d+(?:[/\-]\d+)?"),
        "[ADDRESS_NUMBER]",
    ),
    (
        "address",
        re.compile(r"(?<!\d)\d{1,4}/\d{1,4}(?!\d)"),
        "[ADDRESS_NUMBER]",
    ),
    (
        "unit_number",
        re.compile(r"(?i)(?:(?:หน้า)?ห้อง|room|ชั้น|floor)\s*#?\s*\d+[a-zA-Z]?"),
        "[UNIT]",
    ),
    ("address", re.compile(r"หมู่\s*\d+"), "[VILLAGE]"),
    ("postal_code", re.compile(r"(?<!\d)\d{5}(?!\d)"), "[POSTAL_CODE]"),
)


def redact_text(text: str) -> tuple[str, Counter[str]]:
    """Remove common direct identifiers while preserving order-related wording."""
    counts: Counter[str] = Counter()
    redacted = text.strip()
    for name, pattern, replacement in _REDACTION_PATTERNS:
        redacted, replaced = pattern.subn(replacement, redacted)
        if replaced:
            counts[name] += replaced
    return redacted, counts


def _new_chunk(conversation_number: int, part: int) -> dict:
    return {
        "conversation": f"C{conversation_number:04d}" + (f"-P{part}" if part > 1 else ""),
        "messages": [],
    }


def create_preparation(
    db: Session,
    *,
    max_conversations_per_batch: int = 20,
    max_characters_per_batch: int = 9000,
) -> HistoryAnalysisPreparation:
    """Create a durable, redacted snapshot split into reasonably sized contexts."""
    rows = (
        db.query(HistoryMessage)
        .order_by(HistoryMessage.history_conversation_id, HistoryMessage.sent_at, HistoryMessage.id)
        .all()
    )
    preparation = HistoryAnalysisPreparation(status="draft")
    db.add(preparation)
    db.flush()

    batches: list[dict] = []
    batch_chunks: list[dict] = []
    batch_characters = 0
    redaction_counts: Counter[str] = Counter()
    conversation_number = 0
    message_count = 0
    current_conversation_id: int | None = None
    current_chunk: dict | None = None
    current_part = 0

    def flush_batch() -> None:
        nonlocal batch_chunks, batch_characters
        if batch_chunks:
            batches.append({"conversations": batch_chunks})
        batch_chunks = []
        batch_characters = 0

    for message in rows:
        if message.history_conversation_id != current_conversation_id:
            current_conversation_id = message.history_conversation_id
            conversation_number += 1
            current_part = 1
            current_chunk = _new_chunk(conversation_number, current_part)
            if len(batch_chunks) >= max_conversations_per_batch:
                flush_batch()
            batch_chunks.append(current_chunk)

        redacted_text, counts = redact_text(message.text)
        redaction_counts.update(counts)
        entry = {"speaker": "customer" if message.direction == "in" else "shop", "text": redacted_text}
        entry_size = len(redacted_text) + 24

        if batch_characters and batch_characters + entry_size > max_characters_per_batch:
            # Preserve the conversation boundary whenever possible. For an
            # unusually long conversation, label a continuation part instead.
            if current_chunk and current_chunk["messages"]:
                flush_batch()
                current_part += 1
                current_chunk = _new_chunk(conversation_number, current_part)
                batch_chunks.append(current_chunk)
        current_chunk["messages"].append(entry)
        batch_characters += entry_size
        message_count += 1

    flush_batch()
    for number, content in enumerate(batches, start=1):
        conversation_count = len(content["conversations"])
        batch_message_count = sum(len(chunk["messages"]) for chunk in content["conversations"])
        db.add(
            HistoryAnalysisBatch(
                preparation_id=preparation.id,
                batch_number=number,
                conversation_count=conversation_count,
                message_count=batch_message_count,
                content=content,
            )
        )

    preparation.conversation_count = conversation_number
    preparation.message_count = message_count
    preparation.batch_count = len(batches)
    preparation.redaction_counts = dict(redaction_counts)
    db.commit()
    db.refresh(preparation)
    return preparation


def approve_batch(batch: HistoryAnalysisBatch, user_id: int) -> HistoryAnalysisBatch:
    """Mark a batch as explicitly reviewed; no data is transmitted here."""
    batch.status = "approved"
    batch.approved_by_user_id = user_id
    batch.approved_at = datetime.utcnow()
    return batch
