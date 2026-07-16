import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from database import crud
from services.retrieval_service import build_prompt_context, perform_vector_search
from utils.llm_client import invoke_llm_structured

logger = logging.getLogger(__name__)


class Citation(BaseModel):
    document_id: str
    section_name: str
    text_snippet: str


class QAResult(BaseModel):
    answer: str = Field(description="The comprehensive answer based strictly on the context provided.")
    supporting_clauses: List[str] = Field(description="List of specific clause strings that directly support the answer.")
    citation_references: List[Citation] = Field(description="List of exact citations pointing to source documents.")
    confidence_score: int = Field(description="Confidence score from 0 to 100.")
    context_used: str = Field(default="", description="The raw context string used to generate this answer.")


def answer_legal_question(query: str, doc_id: Optional[str] = None) -> QAResult:
    """Legal Question Answering Agent.

    Query -> Embedding -> Vector Search (Top 5) -> optional Cross-Encoder
    Reranker -> Prompt Builder -> single LLM call -> Answer + citations.
    """
    retrieved_docs = perform_vector_search(query, doc_id, k=5)

    retrieved_chunk_ids = [d.metadata.get("clause_id") for d in retrieved_docs if d.metadata.get("clause_id") is not None]
    try:
        crud.log_retrieval(query_text=query, doc_id_scope=doc_id, retrieved_chunk_ids=retrieved_chunk_ids)
    except Exception:
        logger.exception("Failed to log retrieval history (non-fatal)")

    if not retrieved_docs:
        return QAResult(
            answer="I could not find any relevant information in the documents to answer your question.",
            supporting_clauses=[], citation_references=[], confidence_score=0,
        )

    context_str = build_prompt_context(retrieved_docs)

    system_instruction = (
        "You are an expert corporate legal counsel. "
        "Answer the user's question using strictly the provided context blocks. "
        "Do not hallucinate or use outside knowledge. If the answer is not in the context, say so clearly. "
        "Provide a comprehensive 'answer', 'supporting_clauses' texts, 'citation_references' with document IDs and section names, "
        "and a 'confidence_score' (0-100)."
    )
    prompt = f"Retrieved Context:\n{context_str}\n\nUser Question:\n{query}"

    try:
        result = invoke_llm_structured(system_instruction, prompt, QAResult)
        result.context_used = context_str
        return result
    except Exception as e:
        logger.error(f"QA generation failed: {e}")
        return QAResult(
            answer=f"An error occurred while generating the answer: {e}",
            supporting_clauses=[], citation_references=[], confidence_score=0,
        )
