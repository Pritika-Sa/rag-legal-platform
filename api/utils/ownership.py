from fastapi import HTTPException, status

from database import crud


def get_owned_document(doc_id: int, user_id: int) -> dict:
    """Authorization check (adapter responsibility, not business logic): a
    document-scoped endpoint reached directly by ID over HTTP is a new
    attack surface Streamlit's session-embedded doc_id never exposed — the
    UI only ever set active_doc_id from that same user's own document list.
    Shared across every router that touches a single document's data."""
    document = crud.get_document_by_id(doc_id)
    if not document or document.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document
