import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from langchain_chroma import Chroma
from utils.llm_client import get_embeddings

load_dotenv()
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "vectorstore/chroma_db")
COLLECTION_NAME = "legal_documents"


_chroma_instance = None


def get_chroma_vectorstore() -> Chroma:
    """Returns a cached Chroma vector store singleton (mirrors get_embeddings())."""
    global _chroma_instance
    if _chroma_instance is None:
        embeddings = get_embeddings()
        os.makedirs(CHROMA_DB_PATH, exist_ok=True)
        _chroma_instance = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME,
        )
    return _chroma_instance


def add_document(document_id: str, version: int, clauses: List[Dict[str, Any]], upload_date: str) -> List[str]:
    """Adds a document's clauses to the vector database with metadata."""
    db = get_chroma_vectorstore()

    texts = []
    metadatas = []
    ids = []

    for idx, c in enumerate(clauses):
        texts.append(c["text_content"])
        meta = {
            "document_id": str(document_id),
            "version": int(c.get("version") or version),
            "clause_type": str(c.get("clause_type") or c.get("classification") or "Unclassified"),
            "risk_level": str(c.get("risk_level") or "None"),
            "upload_date": str(upload_date),
            "clause_id": int(c.get("id", idx)),
            "page_number": int(c.get("page_num") or c.get("page_number") or 0),
            "chunk_number": int(idx),
            "importance": int(c.get("importance_score") or 0),
            "language": str(c.get("language") or "unknown"),
            "document_type": str(c.get("document_type") or "General Contract"),
        }
        metadatas.append(meta)
        ids.append(f"{document_id}_v{version}_c{meta['clause_id']}")

    db.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    return ids


def delete_document(document_id: str) -> None:
    """Deletes all clause embeddings belonging to a document from ChromaDB."""
    db = get_chroma_vectorstore()
    try:
        collection = db._collection
        collection.delete(where={"document_id": str(document_id)})
    except Exception as e:
        print(f"Error deleting document_id {document_id} from vector store: {e}")
        raise e


def update_document(document_id: str, version: int, clauses: List[Dict[str, Any]], upload_date: str) -> List[str]:
    """Updates a document by deleting existing vectors and re-adding."""
    delete_document(document_id)
    return add_document(document_id, version, clauses, upload_date)


def search_document(query_text: str, document_id: Optional[str] = None,
                    filters: Optional[Dict[str, Any]] = None, k: int = 4) -> List[Any]:
    """Performs similarity search with optional document scope and metadata filtering."""
    db = get_chroma_vectorstore()

    where_filter = {}
    conditions = []

    if document_id is not None:
        conditions.append({"document_id": str(document_id)})
    if filters:
        for k_field, v_val in filters.items():
            conditions.append({k_field: v_val})

    if len(conditions) == 1:
        where_filter = conditions[0]
    elif len(conditions) > 1:
        where_filter = {"$and": conditions}

    results = db.similarity_search(
        query_text,
        k=k,
        filter=where_filter if where_filter else None,
    )
    return results


def add_clauses_to_vectorstore(clauses: List[Dict[str, Any]]) -> List[str]:
    """Compatibility wrapper mapping to add_document."""
    if not clauses:
        return []
    doc_id = str(clauses[0].get("doc_id", "unknown_doc"))
    from datetime import datetime
    upload_date = datetime.now().isoformat()

    mapped_clauses = []
    for c in clauses:
        mapped_clauses.append({
            "id": c.get("id"),
            "text_content": c.get("text_content"),
            "clause_type": c.get("clause_type") or c.get("classification"),
            "risk_level": c.get("risk_level"),
            "page_num": c.get("page_num"),
            "importance_score": c.get("importance_score"),
            "language": c.get("language"),
            "document_type": c.get("document_type"),
            "version": c.get("version", 1),
        })
    return add_document(document_id=doc_id, version=1, clauses=mapped_clauses, upload_date=upload_date)


def query_vectorstore(query: str, doc_id: Optional[Any] = None, k: int = 5) -> List[Any]:
    """Compatibility wrapper mapping to search_document."""
    return search_document(query_text=query, document_id=str(doc_id) if doc_id else None, k=k)
