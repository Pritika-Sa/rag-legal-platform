from database.connection import get_db


def init_db():
    """Initializes MongoDB collections and creates indexes."""
    db = get_db()

    db.users.create_index("email", unique=True)
    db.users.create_index("reset_token_hash")
    # Looked up on every authenticated request now (api/deps.py::get_current_user
    # checks the account still exists, so a deleted account's JWT stops
    # working immediately instead of staying valid until it expires).
    db.users.create_index("id", unique=True)

    # Unique per-user, not globally - different users may each upload a file
    # named e.g. "contract.pdf" without colliding.
    db.documents.create_index([("user_id", 1), ("name", 1)], unique=True)
    db.documents.create_index("hash")
    db.documents.create_index("user_id")

    db.clauses.create_index("doc_id")
    db.clauses.create_index([("doc_id", 1), ("section_name", 1)])

    db.contradictions.create_index("doc_id")

    db.clause_versions.create_index("clause_id")

    db.audit_logs.create_index("timestamp")

    # Normalized collections: pages (Stage-1 raw page text), entities and
    # relationships (persisted knowledge-graph/dependency-graph output,
    # previously computed and thrown away every page load), and
    # retrieval_history (one row per QA query, for the hybrid retrieval
    # pipeline to log against).
    db.pages.create_index([("doc_id", 1), ("page_number", 1)])
    db.entities.create_index("doc_id")
    db.entities.create_index([("doc_id", 1), ("clause_id", 1)])
    db.relationships.create_index("doc_id")
    db.retrieval_history.create_index("timestamp")
    db.retrieval_history.create_index("doc_id_scope")

    for collection_name in (
        "users", "documents", "clauses", "contradictions", "clause_versions", "audit_logs",
        "pages", "entities", "relationships", "retrieval_history",
    ):
        db.counters.update_one(
            {"_id": collection_name}, {"$setOnInsert": {"seq": 0}}, upsert=True
        )

    print("MongoDB collections and indexes initialized successfully.")


def _get_next_id(collection_name: str) -> int:
    """Auto-increment helper — returns the next integer ID for a collection."""
    db = get_db()
    result = db.counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        return_document=True,
    )
    return result["seq"]


if __name__ == "__main__":
    init_db()
