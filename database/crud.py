from datetime import datetime, timezone
from database.connection import get_db
from database.models import _get_next_id


def _now():
    return datetime.now(timezone.utc)


# ── Documents ──────────────────────────────────────────────────────────────

def add_document(name, path, file_hash, user_id=None):
    """Inserts a new document and returns its integer ID. Dedup (by name) is
    scoped per-user - two different users may each own a same-named file."""
    db = get_db()
    existing = db.documents.find_one({"name": name, "user_id": user_id})
    if existing:
        return existing["id"]

    doc_id = _get_next_id("documents")
    db.documents.insert_one({
        "id": doc_id,
        "name": name,
        "path": path,
        "hash": file_hash,
        "user_id": user_id,
        "upload_date": _now(),
        "status": "processing",
    })
    add_audit_log("document_upload", f"Uploaded document '{name}' (ID: {doc_id})")
    return doc_id


def get_document_by_hash(file_hash, user_id=None):
    """Retrieves document by its hash, scoped to `user_id` when given so two
    different users uploading identical file content each get their own
    document instead of the second user being pointed at the first user's
    (otherwise-invisible-to-them) document."""
    db = get_db()
    query = {"hash": file_hash}
    if user_id is not None:
        query["user_id"] = user_id
    return db.documents.find_one(query)


def get_all_documents(user_id=None):
    """Retrieves documents, newest first. Scoped to `user_id` when given -
    every page reaches a doc_id through this listing (or through a
    session_state value seeded by it), so filtering here is what keeps each
    user's workspace private."""
    db = get_db()
    query = {"user_id": user_id} if user_id is not None else {}
    return list(db.documents.find(query).sort("upload_date", -1))


def get_document_by_id(doc_id):
    """Retrieves a document by ID."""
    db = get_db()
    return db.documents.find_one({"id": doc_id})


def update_document_analysis(doc_id, **fields):
    """Sets document-level analysis fields (document_type, language,
    authenticity_score, authenticity_level, parsing_quality_warning,
    document_risk_score, document_risk_level, document_risk_recommendations)
    onto the documents collection. Only non-None values are written, so
    partial updates (e.g. from a node that only computed authenticity) never
    clobber fields set by another node. MongoDB is schemaless, so documents
    analyzed before this field existed simply lack it — every reader must
    use .get(...) with a default, never direct indexing."""
    updates = {k: v for k, v in fields.items() if v is not None}
    if not updates:
        return
    db = get_db()
    db.documents.update_one({"id": doc_id}, {"$set": updates})


def delete_document(doc_id):
    """Deletes a document and all related data."""
    db = get_db()
    doc = db.documents.find_one({"id": doc_id})
    doc_name = doc["name"] if doc else f"ID {doc_id}"

    db.contradictions.delete_many({"doc_id": doc_id})
    clause_ids = [c["id"] for c in db.clauses.find({"doc_id": doc_id}, {"id": 1})]
    if clause_ids:
        db.clause_versions.delete_many({"clause_id": {"$in": clause_ids}})
    db.clauses.delete_many({"doc_id": doc_id})
    db.documents.delete_one({"id": doc_id})

    add_audit_log("document_delete", f"Deleted document '{doc_name}' (ID: {doc_id})")


# ── Clauses ────────────────────────────────────────────────────────────────

def add_clause(doc_id, section_name, text_content, page_num=None,
               classification=None, risk_category=None, risk_level="None",
               explanation=None, simplification=None, risk_score=None):
    """Inserts a clause and returns its integer ID."""
    db = get_db()
    clause_id = _get_next_id("clauses")
    db.clauses.insert_one({
        "id": clause_id,
        "doc_id": doc_id,
        "section_name": section_name,
        "text_content": text_content,
        "page_num": page_num,
        "version": 1,
        "classification": classification,
        "risk_category": risk_category,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "explanation": explanation,
        "simplification": simplification,
    })
    return clause_id


def add_clauses_bulk(doc_id, clauses):
    """Bulk-inserts clauses for a document, incrementing the ID counter once
    (via a single $inc) instead of once per clause. `clauses` items are
    dicts using the same keys as add_clause's parameters. Returns the
    assigned integer IDs in the same order as `clauses`."""
    if not clauses:
        return []

    db = get_db()
    n = len(clauses)
    result = db.counters.find_one_and_update(
        {"_id": "clauses"},
        {"$inc": {"seq": n}},
        return_document=True,
    )
    end_id = result["seq"]
    ids = list(range(end_id - n + 1, end_id + 1))

    docs = [
        {
            "id": clause_id,
            "doc_id": doc_id,
            "section_name": c.get("section_name", "Clause"),
            "text_content": c.get("text_content", ""),
            "page_num": c.get("page_num"),
            "version": 1,
            "classification": c.get("classification"),
            "risk_category": c.get("risk_category"),
            "risk_level": c.get("risk_level", "None"),
            "risk_score": c.get("risk_score"),
            "explanation": c.get("explanation"),
            "simplification": c.get("simplification"),
        }
        for clause_id, c in zip(ids, clauses)
    ]
    db.clauses.insert_many(docs)
    return ids


def get_clauses_for_document(doc_id):
    """Retrieves all clauses for a document, ordered by ID."""
    db = get_db()
    return list(db.clauses.find({"doc_id": doc_id}).sort("id", 1))


def update_clause_risk(clause_id, risk_level, risk_category, risk_score, explanation, source="LLM"):
    """Overwrites a clause's risk fields (e.g. after an on-demand LLM
    re-analysis) without touching text_content/version — this isn't an edit
    to the clause itself, just a re-scoring."""
    db = get_db()
    clause = db.clauses.find_one({"id": clause_id})
    if not clause:
        raise ValueError(f"Clause with ID {clause_id} not found.")

    db.clauses.update_one(
        {"id": clause_id},
        {"$set": {
            "risk_level": risk_level,
            "risk_category": risk_category,
            "risk_score": risk_score,
            "explanation": explanation,
        }},
    )
    add_audit_log(
        "clause_risk_reanalysis",
        f"Re-scored clause ID {clause_id} ('{clause['section_name']}') via {source}: {risk_level} ({risk_score}/100)",
    )


# ── Contradictions ─────────────────────────────────────────────────────────

def add_contradiction(doc_id, clause_id_1, clause_id_2, explanation, severity="Medium"):
    """Inserts a detected contradiction."""
    db = get_db()
    c_id = _get_next_id("contradictions")
    db.contradictions.insert_one({
        "id": c_id,
        "doc_id": doc_id,
        "clause_id_1": clause_id_1,
        "clause_id_2": clause_id_2,
        "explanation": explanation,
        "severity": severity,
    })
    return c_id


def get_contradictions_for_document(doc_id):
    """Gets all contradictions in a document with clause details joined."""
    db = get_db()
    contradictions = list(db.contradictions.find({"doc_id": doc_id}))

    for c in contradictions:
        cl1 = db.clauses.find_one({"id": c["clause_id_1"]})
        cl2 = db.clauses.find_one({"id": c["clause_id_2"]})
        c["section_1"] = cl1["section_name"] if cl1 else ""
        c["text_1"] = cl1["text_content"] if cl1 else ""
        c["section_2"] = cl2["section_name"] if cl2 else ""
        c["text_2"] = cl2["text_content"] if cl2 else ""

    return contradictions


# ── Pages (Stage-1 raw per-page text, PDF only) ─────────────────────────────

def add_pages_bulk(doc_id, pages):
    """Bulk-inserts page records. `pages` items are dicts with
    `page_number`/`raw_text` (see parser_agent.parse_document_pages). Empty
    for DOCX/TXT sources, which have no fixed pagination."""
    if not pages:
        return []

    db = get_db()
    n = len(pages)
    result = db.counters.find_one_and_update(
        {"_id": "pages"}, {"$inc": {"seq": n}}, return_document=True,
    )
    end_id = result["seq"]
    ids = list(range(end_id - n + 1, end_id + 1))

    docs = [
        {
            "id": page_id,
            "doc_id": doc_id,
            "page_number": p.get("page_number"),
            "raw_text": p.get("raw_text", ""),
        }
        for page_id, p in zip(ids, pages)
    ]
    db.pages.insert_many(docs)
    return ids


def get_pages_for_document(doc_id):
    """Retrieves all page records for a document, ordered by page number.
    Returns [] for documents with no page-level data (DOCX/TXT, or
    documents analyzed before this collection existed)."""
    db = get_db()
    return list(db.pages.find({"doc_id": doc_id}).sort("page_number", 1))


# ── Entities (persisted knowledge-graph nodes) ──────────────────────────────

def add_entities_bulk(doc_id, entities):
    """Bulk-inserts entity records. `entities` items are dicts with
    `clause_id` (None for document-level entities like jurisdiction),
    `entity_text`, `entity_type` (party/date/money/jurisdiction/penalty/
    obligation — matches graph_store's node_type vocabulary)."""
    if not entities:
        return []

    db = get_db()
    n = len(entities)
    result = db.counters.find_one_and_update(
        {"_id": "entities"}, {"$inc": {"seq": n}}, return_document=True,
    )
    end_id = result["seq"]
    ids = list(range(end_id - n + 1, end_id + 1))

    docs = [
        {
            "id": entity_id,
            "doc_id": doc_id,
            "clause_id": e.get("clause_id"),
            "entity_text": e.get("entity_text", ""),
            "entity_type": e.get("entity_type", "unknown"),
        }
        for entity_id, e in zip(ids, entities)
    ]
    db.entities.insert_many(docs)
    return ids


# ── Relationships (persisted knowledge-graph + dependency-graph edges) ──────

def add_relationships_bulk(doc_id, relationships):
    """Bulk-inserts relationship records unifying knowledge_graph_agent's
    entity-edges and dependency_agent's clause-edges into one collection.
    `relationships` items are dicts with `source_type`/`target_type`
    ('clause' or 'entity'), `source_id`/`target_id` (as strings), `relation`,
    `explanation`."""
    if not relationships:
        return []

    db = get_db()
    n = len(relationships)
    result = db.counters.find_one_and_update(
        {"_id": "relationships"}, {"$inc": {"seq": n}}, return_document=True,
    )
    end_id = result["seq"]
    ids = list(range(end_id - n + 1, end_id + 1))

    docs = [
        {
            "id": rel_id,
            "doc_id": doc_id,
            "source_type": r.get("source_type"),
            "source_id": str(r.get("source_id")),
            "target_type": r.get("target_type"),
            "target_id": str(r.get("target_id")),
            "relation": r.get("relation"),
            "explanation": r.get("explanation"),
        }
        for rel_id, r in zip(ids, relationships)
    ]
    db.relationships.insert_many(docs)
    return ids


# ── Retrieval History (one row per QA query) ────────────────────────────────

def log_retrieval(query_text, doc_id_scope=None, detected_intent_filter=None,
                   retrieved_chunk_ids=None, confidence_score=None, trust_score=None):
    """Logs one QA query for later analysis. Called from qa_agent.py after
    each answer_legal_question call."""
    db = get_db()
    log_id = _get_next_id("retrieval_history")
    db.retrieval_history.insert_one({
        "id": log_id,
        "query_text": query_text,
        "doc_id_scope": doc_id_scope,
        "detected_intent_filter": detected_intent_filter,
        "retrieved_chunk_ids": retrieved_chunk_ids or [],
        "confidence_score": confidence_score,
        "trust_score": trust_score,
        "timestamp": _now(),
    })
    return log_id


# ── Audit Logs ─────────────────────────────────────────────────────────────

def add_audit_log(action, details=None):
    """Inserts an event into the audit logs."""
    db = get_db()
    log_id = _get_next_id("audit_logs")
    db.audit_logs.insert_one({
        "id": log_id,
        "action": action,
        "details": details,
        "timestamp": _now(),
    })
    return log_id


def get_audit_logs(limit=50):
    """Gets recent logs."""
    db = get_db()
    return list(db.audit_logs.find().sort("timestamp", -1).limit(limit))


# ── Dashboard Metrics ──────────────────────────────────────────────────────

def get_dashboard_metrics(doc_id=None, user_id=None):
    """Aggregates metrics for the dashboard page. When `doc_id` is omitted,
    `user_id` scopes the aggregate workspace metrics to that user's own
    documents."""
    db = get_db()

    if doc_id:
        total_clauses = db.clauses.count_documents({"doc_id": doc_id})
        total_contradictions = db.contradictions.count_documents({"doc_id": doc_id})
        risky_clauses = db.clauses.count_documents({
            "doc_id": doc_id,
            "risk_level": {"$in": ["High", "Medium"]},
        })

        pipeline = [
            {"$match": {"doc_id": doc_id}},
            {"$group": {"_id": "$risk_level", "count": {"$sum": 1}}},
        ]
        risk_dist = {r["_id"]: r["count"] for r in db.clauses.aggregate(pipeline)}
        total_documents = 1
    else:
        doc_query = {"user_id": user_id} if user_id is not None else {}
        doc_ids = [d["id"] for d in db.documents.find(doc_query, {"id": 1})]
        clause_query = {"doc_id": {"$in": doc_ids}}

        total_documents = len(doc_ids)
        total_clauses = db.clauses.count_documents(clause_query)
        total_contradictions = db.contradictions.count_documents({"doc_id": {"$in": doc_ids}})
        risky_clauses = db.clauses.count_documents({
            **clause_query,
            "risk_level": {"$in": ["High", "Medium"]},
        })

        pipeline = [
            {"$match": clause_query},
            {"$group": {"_id": "$risk_level", "count": {"$sum": 1}}},
        ]
        risk_dist = {r["_id"]: r["count"] for r in db.clauses.aggregate(pipeline)}

    return {
        "total_documents": total_documents,
        "total_clauses": total_clauses,
        "total_contradictions": total_contradictions,
        "risky_clauses": risky_clauses,
        "risk_distribution": risk_dist,
    }
