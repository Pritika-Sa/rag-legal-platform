"""Aggregate document-metric answering for the chatbot (Stage 0.5, no LLM,
no retrieval): detects when a chat question is asking for a number/label
that's already persisted on the document (clause count, risk/authenticity
scores, contradiction count, ...) and answers it straight from MongoDB via
the same crud functions the Dashboard/Risk Analysis/Clause Analysis pages
already use — instead of letting the LLM estimate it from a handful of
retrieved clause chunks (see agents/qa_agent.py, which calls this module
before falling back to the existing RAG pipeline).

Deliberately keyword/rule-based, not an LLM call: the whole point of this
module is to stop trusting an LLM to reproduce a number that already exists
verbatim in the database, so classifying "is this an aggregate question"
with a second LLM call would reintroduce a smaller version of the same
problem (and cost a round trip on every message). This mirrors the existing
codebase precedent for enumerable-category classification
(services/document_classifier.py, agents/rule_engine.py) — plain keyword
matching over a small, known set of question types.
"""

from typing import Any, Optional

from database import crud

# Checked in this order — first match wins. More specific phrasings (e.g.
# "risky clauses") must be listed before the generic metric they'd otherwise
# also satisfy as a substring (e.g. "risky clause count" contains "clause
# count"), so ordering here is load-bearing, not cosmetic.
_METRIC_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("risky_clause_count", (
        "risky clause", "risky clauses", "flagged clause", "flagged clauses",
        "high risk clause", "high-risk clause", "medium risk clause",
        "how many clauses are risky", "how many risky",
    )),
    ("authenticity_score", (
        "authenticity score", "authenticity level", "authenticity confidence",
        "how authentic", "is this document authentic", "document authenticity",
    )),
    ("document_risk_score", (
        "document risk score", "overall risk score", "risk score of the document",
        "risk score of this document", "what is the document's risk score",
    )),
    ("contradiction_count", (
        "how many contradictions", "contradiction count", "number of contradictions",
        "how many conflicts", "internal conflicts",
    )),
    ("entity_count", (
        "how many entities", "entity count", "number of entities", "named entities",
    )),
    ("relationship_count", (
        "how many relationships", "relationship count", "number of relationships",
    )),
    ("document_type", (
        "document type", "what type of document", "what kind of document",
        "type of contract is this", "what kind of contract",
    )),
    ("processing_status", (
        "processing status", "has this document been processed",
        "is this document processed", "document status",
    )),
    ("clause_count", (
        "how many clauses", "clause count", "number of clauses", "total clauses",
        "total number of clauses",
    )),
]


def classify_aggregate_metric(query: str) -> Optional[str]:
    """Returns the metric key (e.g. "clause_count") if `query` is asking for
    a persisted document-level aggregate, else None (meaning: treat it as a
    legal question and run the existing RAG pipeline unchanged)."""
    normalized = query.strip().lower()
    for metric, phrases in _METRIC_KEYWORDS:
        if any(phrase in normalized for phrase in phrases):
            return metric
    return None


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _format_answer(metric: str, document: dict, dashboard: dict,
                    entity_count: int, relationship_count: int) -> str:
    if metric == "clause_count":
        return f"This document has {_plural(dashboard['total_clauses'], 'clause', 'clauses')}."

    if metric == "risky_clause_count":
        dist = dashboard["risk_distribution"]
        high, medium = dist.get("High", 0), dist.get("Medium", 0)
        return (
            f"This document has {_plural(dashboard['risky_clauses'], 'risky clause', 'risky clauses')} "
            f"({high} High risk, {medium} Medium risk)."
        )

    if metric == "authenticity_score":
        score = document.get("authenticity_score")
        level = document.get("authenticity_level", "Unknown")
        if score is None:
            return "This document has not had an authenticity assessment yet."
        return f"The authenticity score is {score}/100 ({level})."

    if metric == "document_risk_score":
        score = document.get("document_risk_score")
        level = document.get("document_risk_level", "Unknown")
        if score is None:
            return "This document has not had a risk assessment yet."
        return f"The document risk score is {score}/100 ({level})."

    if metric == "contradiction_count":
        n = dashboard["total_contradictions"]
        return f"{_plural(n, 'contradiction', 'contradictions')} {'was' if n == 1 else 'were'} found in this document."

    if metric == "entity_count":
        return f"{_plural(entity_count, 'entity', 'entities')} {'was' if entity_count == 1 else 'were'} extracted from this document."

    if metric == "relationship_count":
        return (
            f"{_plural(relationship_count, 'relationship', 'relationships')} "
            f"{'was' if relationship_count == 1 else 'were'} extracted from this document."
        )

    if metric == "document_type":
        return f"This document is classified as: {document.get('document_type') or 'Unknown Document'}."

    if metric == "processing_status":
        return f"This document's processing status is: {document.get('status', 'unknown')}."

    raise ValueError(f"Unhandled aggregate metric: {metric}")  # pragma: no cover


def answer_aggregate_metric(metric: str, doc_id: Any, user_id: Any) -> Optional[str]:
    """Builds the answer text for `metric` straight from MongoDB. Returns
    None if there's no document to scope the answer to (no active document
    selected) or the document/user_id pair doesn't resolve to a real,
    owned document — in either case the caller falls back to the existing
    RAG pipeline's own out-of-scope handling rather than this module
    inventing a new error path.

    Ownership is not re-checked here: both call sites (api/routers/chat.py
    and app.py's Streamlit handler) already resolve `doc_id` from the
    current user's own document list before reaching this function, the
    same trust boundary the rest of agents/qa_agent.py relies on. The
    `user_id` passed to get_dashboard_metrics below is still honored as a
    defense-in-depth scope, exactly like every other document-scoped crud
    call in this codebase.
    """
    if doc_id is None:
        return None

    document = crud.get_document_by_id(int(doc_id))
    if not document:
        return None

    # Reuses the exact function the Dashboard/Risk Analysis pages call —
    # not a second implementation of "count risky clauses" or "count
    # clauses" (requirement: no duplicate database queries). Returns
    # zeroed counts (never None) if doc_id/user_id don't match a real,
    # owned document.
    dashboard = crud.get_dashboard_metrics(doc_id=int(doc_id), user_id=user_id)

    entity_count = crud.count_entities_for_document(int(doc_id))
    relationship_count = crud.count_relationships_for_document(int(doc_id))

    return _format_answer(metric, document, dashboard, entity_count, relationship_count)
