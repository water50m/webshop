"""Aggregate-only Parser v2 evaluation over an approved, redacted history snapshot."""

from collections import Counter

from sqlalchemy.orm import Session

from app.models import HistoryAnalysisBatch, HistoryAnalysisPreparation
from app.services.rule_based_parser_v2 import _catalog, parse_message


def summarize_latest_approved_history(db: Session) -> dict:
    """Run Parser v2 on customer messages without exposing or persisting their text.

    The source is restricted to the most recent snapshot whose batches were
    approved.  The response contains aggregate counts only, so it is useful as
    the real-history regression corpus without creating a second copy of chat
    content or triggering live orders/handoffs.
    """
    preparation = (
        db.query(HistoryAnalysisPreparation)
        .filter(HistoryAnalysisPreparation.status == "approved")
        .order_by(HistoryAnalysisPreparation.id.desc())
        .first()
    )
    if preparation is None:
        raise ValueError("ไม่พบชุดข้อมูลปกปิดที่อนุมัติแล้ว")

    batches = (
        db.query(HistoryAnalysisBatch)
        .filter(
            HistoryAnalysisBatch.preparation_id == preparation.id,
            HistoryAnalysisBatch.status == "approved",
        )
        .order_by(HistoryAnalysisBatch.batch_number)
        .all()
    )
    entries = _catalog(db)
    intent_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    handoff_counts: Counter[str] = Counter()
    product_counts: Counter[str] = Counter()
    match_source_counts: Counter[str] = Counter()
    customer_message_count = 0

    for batch in batches:
        for conversation in batch.content.get("conversations", []):
            for message in conversation.get("messages", []):
                if message.get("speaker") != "customer" or not message.get("text"):
                    continue
                customer_message_count += 1
                result = parse_message(db, message["text"], entries=entries)
                intent_counts[result.intent] += 1
                state_counts[result.next_state] += 1
                if result.handoff_reason:
                    handoff_counts[result.handoff_reason] += 1
                for item in result.items:
                    product_counts[item.product_name] += item.quantity
                    match_source_counts[item.match_source] += 1

    return {
        "preparation_id": preparation.id,
        "approved_batch_count": len(batches),
        "customer_message_count": customer_message_count,
        "intent_counts": dict(intent_counts.most_common()),
        "next_state_counts": dict(state_counts.most_common()),
        "handoff_reason_counts": dict(handoff_counts.most_common()),
        "matched_product_quantity": dict(product_counts.most_common()),
        "match_source_counts": dict(match_source_counts.most_common()),
    }
