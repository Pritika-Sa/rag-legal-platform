"""Prompt Builder (Stage 3/4, no LLM): the only place LLM-facing prompt
strings get assembled from clause text, retrieved chunks, or document-level
summaries. Centralizing this keeps every prompt provably bounded — no call
site builds its own ad hoc string that could accidentally grow to full-
document size.
"""

from typing import Any, Dict, List, Tuple


def build_clause_prompt(section_name: str, clause_text: str, instructions: str = "") -> str:
    """Single-clause prompt body: 'Section Heading / Clause Content', optionally
    followed by extra instructions/context. Used for any on-demand, per-clause
    LLM call (risk re-analysis, simplification, mitigation drafting)."""
    prompt = f"Section Heading: {section_name}\nClause Content:\n{clause_text}"
    if instructions:
        prompt += f"\n\n{instructions}"
    return prompt


def build_context_block(blocks: List[Tuple[Dict[str, Any], str]]) -> str:
    """Formats retrieved-and-compressed chunks into the citation-friendly
    '--- Context Block N (Doc ID: ..., Section: ...) ---' layout consumed by
    the QA agent's prompt. `blocks` is a list of (chroma_metadata, compressed_text)
    pairs, in the order they should appear."""
    context_str = ""
    for idx, (meta, compressed_text) in enumerate(blocks):
        context_str += (
            f"--- Context Block {idx+1} "
            f"(Doc ID: {meta.get('document_id', meta.get('doc_id'))}, "
            f"Section: {meta.get('clause_type', 'Unknown')}) ---\n"
            f"{compressed_text}\n\n"
        )
    return context_str


def build_summary_prompt(doc_name: str, stats: Dict[str, Any], sample_lines: List[str]) -> str:
    """Small, bounded document-level summary prompt body: a handful of
    aggregate stats plus a short list of pre-truncated sample lines — never
    the document's full clause text. Used for macro-level audits/insights
    where per-clause detail isn't needed, only the shape of the document."""
    context = f"Document: {doc_name}\n"
    for label, value in stats.items():
        context += f"{label}: {value}\n"
    if sample_lines:
        context += "\nSamples:\n"
        for line in sample_lines:
            context += f"- {line}\n"
    return context
