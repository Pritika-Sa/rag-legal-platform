import os
import hashlib
import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

from agents.parser_agent import parse_document, parse_document_pages, enforce_chunk_bounds
from agents.clause_identifier_agent import identify_clauses
from agents.importance_agent import assess_clause_importance
from agents.analyzer_agent import assess_clauses_batch
from agents.risk_scoring_agent import assess_document_risk
from agents.contradiction_agent import find_contradictions
from agents.impact_agent import analyze_clause_impact
from agents.knowledge_graph_agent import extract_knowledge_graph
from agents.dependency_agent import extract_clause_dependencies
from agents.authenticity_agent import assess_and_persist_document_authenticity
from agents.audit_agent import perform_macro_audit
from agents import graph_store
from services.document_classifier import classify_document_type
from utils.doc_classifier import detect_language

from database import crud
from vectorstore import chroma_client


class AgentState(TypedDict):
    file_path: str
    user_id: int
    doc_name: str
    doc_hash: str
    doc_id: int
    raw_sections: List[Dict[str, Any]]
    identified_clauses: List[Dict[str, Any]]
    db_clauses: List[Dict[str, Any]]
    contradictions: List[Dict[str, Any]]
    audit_score: int
    error: str
    # Additive fields from the config-driven-rules / hybrid-retrieval / graph
    # / authenticity refactor. None of these hold full document text.
    parsing_quality_warning: Optional[str]
    document_type: str
    language: str
    document_risk_score: int
    document_risk_level: str
    document_risk_recommendations: str
    authenticity_score: int
    authenticity_level: str
    authenticity_warnings: List[str]


def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()


def parse_document_node(state: AgentState) -> Dict[str, Any]:
    """Stage 1 (no LLM): parse the file, enforce the 800-1000 char chunk
    bound on every section, and persist raw per-page text (PDF only)."""
    file_path = state["file_path"]
    doc_name = os.path.basename(file_path)
    try:
        doc_hash = get_file_hash(file_path)
        existing_doc = crud.get_document_by_hash(doc_hash, user_id=state.get("user_id"))
        if existing_doc:
            return {"doc_name": doc_name, "doc_hash": doc_hash, "doc_id": existing_doc['id'],
                    "error": "Document already analyzed."}

        raw_sections = enforce_chunk_bounds(parse_document(file_path))
        doc_id = crud.add_document(doc_name, file_path, doc_hash, user_id=state.get("user_id"))

        pages = parse_document_pages(file_path)
        if pages:
            crud.add_pages_bulk(doc_id, pages)

        return {"doc_name": doc_name, "doc_hash": doc_hash, "doc_id": doc_id,
                "raw_sections": raw_sections, "error": ""}
    except Exception as e:
        return {"error": f"Parsing failed: {str(e)}"}


def clause_processing_node(state: AgentState) -> Dict[str, Any]:
    """Stage 2 (no LLM): identification, importance scoring, and risk
    classification in a single batch pass, followed by bulk persistence and
    document-level risk aggregation. Also computes document-level language/
    type (threaded onto every clause's Chroma metadata) and the clause-count
    parsing-quality check."""
    if state.get("error"):
        return {}

    raw_sections = state["raw_sections"]
    blocks = [f"{s['section_name']}\n{s['text_content']}" for s in raw_sections]
    full_text = "\n\n".join(blocks)
    page_mapping = [
        {"page_number": s.get("page_num"), "text_content": block}
        for s, block in zip(raw_sections, blocks)
    ]

    doc_language = detect_language(full_text)
    doc_type = classify_document_type(full_text)

    try:
        identified_objects = identify_clauses(full_text, page_mapping)
        identified = [
            {
                # Display title: the document's own heading when present,
                # else a descriptive generated one — never the bare
                # clause_type, so e.g. six Confidentiality clauses in one
                # NDA don't all render as identical "Confidentiality" cards.
                "section_name": obj.clause_title,
                "text_content": obj.clause_text,
                # Category: used for grouping/filtering/analytics only.
                "classification": obj.clause_type,
                "confidence_score": obj.confidence_score,
                "page_num": obj.page_number,
            }
            for obj in identified_objects
        ]
        if not identified:
            identified = [
                {"section_name": sec["section_name"], "text_content": sec["text_content"], "classification": "General"}
                for sec in raw_sections
            ]
    except Exception as e:
        logger.exception(f"Clause identification failed (doc_id={state.get('doc_id')}): {e}")
        identified = [
            {"section_name": sec["section_name"], "text_content": sec["text_content"], "classification": "General"}
            for sec in raw_sections
        ]

    parsing_quality_warning = None
    if len(identified) < 3:
        parsing_quality_warning = "Possible parsing issue or poor clause extraction."
        logger.warning(f"{parsing_quality_warning} doc_id={state.get('doc_id')} identified={len(identified)}")
        crud.add_audit_log(
            "parsing_quality_warning",
            f"Doc {state['doc_id']} ('{state['doc_name']}') produced only {len(identified)} identified clauses.",
        )

    for c in identified:
        try:
            importance = assess_clause_importance(c.get("section_name", "Clause"), c["text_content"])
            c["importance_score"] = importance.importance_score
            c["importance_category"] = importance.importance_category
        except Exception:
            c["importance_score"] = 0
            c["importance_category"] = "Informational"

    # Risk scoring runs as one batch call across every clause in the
    # document, not per-clause inside the loop above: the Hybrid
    # Explainable Risk Engine's entropy-weighted dimension fusion (see
    # risk_engine/fusion.py) is a document-level statistic — scoring one
    # clause in isolation can't produce it. This replaces the old
    # per-clause analyze_clause()/score_risk_points() keyword scorer.
    try:
        risk_results, _document_risk_assessment = assess_clauses_batch(identified)
        for c, result in zip(identified, risk_results):
            c["risk_level"] = result.risk_level
            c["risk_category"] = result.risk_category
            c["risk_score"] = result.risk_score
            c["confidence"] = result.confidence
            c["dimension_breakdown"] = [d.model_dump() for d in result.dimension_breakdown]
            c["explanation"] = result.explanation
    except Exception as e:
        logger.exception(f"Batch risk assessment failed (doc_id={state.get('doc_id')}): {e}")
        for c in identified:
            c["risk_level"] = "None"
            c["risk_category"] = "Unknown"
            c["risk_score"] = None
            c["confidence"] = None
            c["dimension_breakdown"] = []
            c["explanation"] = "Error analyzing risk"

    clause_ids = crud.add_clauses_bulk(state["doc_id"], identified)
    db_clauses = []
    for clause_id, sec in zip(clause_ids, identified):
        sec["id"] = clause_id
        # Bug fix: this was never set, so every clause's Chroma
        # "document_id" metadata silently fell back to "unknown_doc",
        # breaking per-document filtering (see chroma_client.add_clauses_to_vectorstore).
        sec["doc_id"] = state["doc_id"]
        sec["language"] = doc_language
        sec["document_type"] = doc_type
        db_clauses.append(sec)

    document_risk_score, document_risk_level, document_risk_recommendations = 0, "Low", ""
    try:
        doc_risk = assess_document_risk(state["doc_name"], db_clauses)
        crud.add_audit_log("document_risk",
                           f"Doc {state['doc_id']} scored {doc_risk.risk_score}/100 ({doc_risk.risk_level})")
        document_risk_score = doc_risk.risk_score
        document_risk_level = doc_risk.risk_level
        document_risk_recommendations = doc_risk.recommendations
    except Exception:
        pass

    chroma_client.add_clauses_to_vectorstore(db_clauses)

    crud.update_document_analysis(
        state["doc_id"],
        document_type=doc_type,
        language=doc_language,
        parsing_quality_warning=parsing_quality_warning,
        document_risk_score=document_risk_score,
        document_risk_level=document_risk_level,
    )

    return {
        "identified_clauses": identified,
        "db_clauses": db_clauses,
        "parsing_quality_warning": parsing_quality_warning,
        "document_type": doc_type,
        "language": doc_language,
        "document_risk_score": document_risk_score,
        "document_risk_level": document_risk_level,
        "document_risk_recommendations": document_risk_recommendations,
    }


def authenticity_check_node(state: AgentState) -> Dict[str, Any]:
    """Deterministic authenticity check (Stage 2, no LLM) — the 7-factor,
    entropy-fused Document Authenticity Index (see authenticity/),
    deliberately separate from legal risk scoring. Runs after
    clause_processing because it needs db_clauses (mandatory-clause and
    semantic-consistency factors); reads the original file_path and
    per-page text directly, since the digital-verification and
    metadata-validation factors need the raw file, not just extracted
    text, and the entity-verification factor needs page boundaries."""
    if state.get("error"):
        return {}

    full_text = "\n\n".join(f"{s['section_name']}\n{s['text_content']}" for s in state["raw_sections"])
    try:
        pages = crud.get_pages_for_document(state["doc_id"])
        result = assess_and_persist_document_authenticity(
            state["doc_id"], state["doc_name"], state["db_clauses"], full_text,
            file_path=state.get("file_path"), pages=pages,
        )
        return {
            "authenticity_score": result.authenticity_score,
            "authenticity_level": result.authenticity_level,
            "authenticity_warnings": result.evidence,
        }
    except Exception as e:
        logger.exception(f"Authenticity check failed (doc_id={state.get('doc_id')}): {e}")
        return {"authenticity_score": 0, "authenticity_level": "Unknown", "authenticity_warnings": []}


def contradiction_detection_node(state: AgentState) -> Dict[str, Any]:
    """Rule-based only (use_llm=False) — fast, no Groq quota cost, runs on
    every upload so the dashboard's contradiction count is accurate the
    moment processing finishes. The deeper AI-verification pass is
    deliberately deferred to the first time a user opens the Contradiction
    Detection page (see views/contradiction.py), which then upgrades this
    same persisted set via crud.replace_contradictions_for_document — so
    every upload isn't paying for an AI pass the user may never look at."""
    if state.get("error"):
        return {}
    try:
        contradictions = find_contradictions(state["db_clauses"], use_llm=False)
        contradiction_ids = crud.replace_contradictions_for_document(state["doc_id"], contradictions)
        saved_contradictions = [
            {"id": c_id, "severity": item.severity}
            for c_id, item in zip(contradiction_ids, contradictions)
        ]
        return {"contradictions": saved_contradictions}
    except Exception as e:
        print(f"Error in contradiction detection: {e}")
        return {"contradictions": []}


def graph_and_impact_node(state: AgentState) -> Dict[str, Any]:
    """Merges the old impact_analysis, knowledge_graph, and dependency_graph
    nodes; no longer gated behind a conditional edge since none of these
    steps calls an LLM. Also unifies both graph agents' output into one
    NetworkX graph (agents/graph_store.py) and persists it as entities/
    relationships rows — knowledge_graph_agent.py and dependency_agent.py
    themselves are untouched, so pages/knowledge_graph.py and
    pages/dependency_graph.py keep working exactly as before."""
    if state.get("error"):
        return {}

    high_risk_clauses = [c for c in state["db_clauses"] if c.get("risk_level") == "High"]
    for c in high_risk_clauses[:2]:
        try:
            analyze_clause_impact(c.get("section_name", "Clause"), c["text_content"])
        except Exception:
            pass

    full_text = "\n".join([c['text_content'] for c in state["db_clauses"]][:5])
    kg_data = {"nodes": [], "edges": []}
    try:
        kg_data = extract_knowledge_graph(state["doc_name"], full_text)
    except Exception:
        pass

    dependency_edges = []
    try:
        dependency_edges = extract_clause_dependencies(state["db_clauses"])
    except Exception:
        pass

    try:
        graph_store.build_document_graph(state["doc_id"], state["db_clauses"], kg_data, dependency_edges)
        entities = graph_store.flatten_entities(state["doc_id"], kg_data)
        relationships = graph_store.flatten_relationships(kg_data, dependency_edges)
        crud.add_entities_bulk(state["doc_id"], entities)
        crud.add_relationships_bulk(state["doc_id"], relationships)
    except Exception:
        logger.exception(f"Graph persistence failed (doc_id={state.get('doc_id')})")

    return {}


def audit_agent_node(state: AgentState) -> Dict[str, Any]:
    try:
        res = perform_macro_audit(state["doc_name"], state["db_clauses"], state["contradictions"])
        crud.add_audit_log("pipeline_audit", f"Orchestrator finished. Audit Score: {res.audit_score}")
        return {"audit_score": res.audit_score}
    except Exception:
        return {"audit_score": 0}


def build_orchestrator():
    workflow = StateGraph(AgentState)

    workflow.add_node("parse_document", parse_document_node)
    workflow.add_node("clause_processing", clause_processing_node)
    workflow.add_node("authenticity_check", authenticity_check_node)
    workflow.add_node("contradiction_detection", contradiction_detection_node)
    workflow.add_node("graph_and_impact", graph_and_impact_node)
    workflow.add_node("audit_agent", audit_agent_node)

    workflow.set_entry_point("parse_document")
    workflow.add_edge("parse_document", "clause_processing")
    workflow.add_edge("clause_processing", "authenticity_check")
    workflow.add_edge("authenticity_check", "contradiction_detection")
    workflow.add_edge("contradiction_detection", "graph_and_impact")
    workflow.add_edge("graph_and_impact", "audit_agent")
    workflow.add_edge("audit_agent", END)

    return workflow.compile()


def run_orchestration(file_path: str, user_id: int = None) -> Dict[str, Any]:
    app = build_orchestrator()
    initial_state = {
        "file_path": file_path,
        "user_id": user_id,
        "doc_name": "", "doc_hash": "", "doc_id": -1,
        "raw_sections": [], "identified_clauses": [],
        "db_clauses": [], "contradictions": [],
        "audit_score": 0, "error": "",
        "parsing_quality_warning": None,
        "document_type": "General Contract", "language": "unknown",
        "document_risk_score": 0, "document_risk_level": "Low", "document_risk_recommendations": "",
        "authenticity_score": 0, "authenticity_level": "Unknown", "authenticity_warnings": [],
    }
    return app.invoke(initial_state)
