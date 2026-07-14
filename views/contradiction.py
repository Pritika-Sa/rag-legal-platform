import streamlit as st
from database import crud
from agents.contradiction_agent import find_contradictions
from utils.theme import render_header


def _run_and_persist_ai_pass(doc_id, clauses):
    """Full hybrid pipeline (rules + embeddings + LLM verification), written
    over whatever's currently persisted for this document (see
    crud.replace_contradictions_for_document) and flagged so it only ever
    runs once automatically per document."""
    contradictions = find_contradictions(clauses, use_llm=True)
    crud.replace_contradictions_for_document(doc_id, contradictions)
    crud.update_document_analysis(doc_id, contradiction_ai_analyzed=True)


def render():
    doc_id = st.session_state.active_doc_id
    doc_name = st.session_state.active_doc_name

    render_header(
        "⚖️",
        "Contradiction & Inconsistency Finder",
        "Identifies conflicting statements, inconsistent obligations, and contradictory terms within the document.",
        badge="Agent 5",
        doc_name=doc_name,
    )

    if not doc_id:
        st.warning("⚠️ Please select an active document in the sidebar to review contradictions.")
        return

    document = crud.get_document_by_id(doc_id)
    clauses = crud.get_clauses_for_document(doc_id)

    # One-time upgrade for documents ingested before clause_title generation
    # existed: their section_name is still the bare category (e.g. every
    # Confidentiality clause literally titled "Confidentiality"), which used
    # to make _detect_duplicates flag every same-category clause pair as a
    # false "duplicate." Same flag/pattern as views/clause_analysis.py and
    # views/risk_analysis.py, so it only runs once per document.
    titles_just_backfilled = False
    if clauses and document and not document.get("clause_titles_backfilled"):
        from agents.clause_identifier_agent import backfill_clause_titles_for_document
        if backfill_clause_titles_for_document(doc_id):
            clauses = crud.get_clauses_for_document(doc_id)
            titles_just_backfilled = True
        crud.update_document_analysis(doc_id, clause_titles_backfilled=True)
        document = crud.get_document_by_id(doc_id)

    # A fast rule-based pass already ran automatically at upload (see
    # agents/orchestrator.py) so a contradiction count is already sitting in
    # the dashboard the moment processing finishes. The first time anyone
    # actually opens this page for the document, upgrade that same stored
    # set with the deeper AI-verification pass — once — so results are ready
    # immediately on every visit after this one, with no button required.
    # If titles were just backfilled, any previously-stored results were
    # computed against the old bare-category titles (the false-duplicate
    # flood) and must be redone regardless of the ai_analyzed flag.
    ai_analyzed = bool(document.get("contradiction_ai_analyzed")) if document else False
    if not ai_analyzed or titles_just_backfilled:
        with st.spinner(
            "Agent 5 is running a one-time deeper AI check for this document — grouping clauses, "
            "checking numeric/date/entity mismatches, and verifying semantically similar pairs with AI. "
            "Future visits to this page will load instantly."
        ):
            _run_and_persist_ai_pass(doc_id, clauses)

    contradictions = crud.get_contradictions_for_document(doc_id)

    header_col, button_col = st.columns([5, 2])
    with header_col:
        if contradictions:
            st.markdown(f"### Found **{len(contradictions)}** internal conflicts:")
        else:
            st.success("✅ No conflicting clauses or internal contradictions were detected in this agreement!")
    with button_col:
        if st.button("🔄 Re-analyze with AI", use_container_width=True,
                     help="Re-runs the full check from scratch — useful after editing or re-scoring clauses."):
            with st.spinner("Agent 5 is re-analyzing this document..."):
                _run_and_persist_ai_pass(doc_id, clauses)
            st.rerun()

    for c in contradictions:
        severity = (c.get("severity") or "Medium").capitalize()
        sev_color = "#FECB52"  # Medium
        if severity == "High":
            sev_color = "#EF553B"
        elif severity == "Low":
            sev_color = "#636EFA"
        contradiction_type = c.get("contradiction_type") or "Contradiction"
        affected = c.get("affected_clauses") or []
        clause_count_label = f" ({len(affected)} clauses)" if len(affected) > 2 else ""

        with st.expander(f"⚠️ {contradiction_type}{clause_count_label} - {severity.upper()} Severity", expanded=True):
            st.markdown(
                f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <span style="
                        background-color: {sev_color};
                        color: #121212;
                        font-weight: bold;
                        padding: 3px 10px;
                        border-radius: 4px;
                        font-size: 0.8rem;
                    ">{severity.upper()} SEVERITY</span>
                    <strong style="color: var(--text-color); opacity: 0.65;">{contradiction_type}</strong>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown("#### 🔍 Affected Clauses")
            for clause in affected:
                if not clause.get("section_name"):
                    continue
                if clause.get("value"):
                    st.markdown(f"- **{clause['section_name']}** → `{clause['value']}`")
                else:
                    st.markdown(f"- {clause['section_name']}")

            st.markdown(
                f"""
                <div style="background: rgba(128, 128, 128, 0.15); padding: 12px; border-radius: 6px; border-left: 3px solid {sev_color}; margin-top: 10px; margin-bottom: 15px;">
                    <strong style="color: var(--text-color);">Explanation of Conflict:</strong><br>
                    <span style="font-size: 0.95rem; color: var(--text-color); opacity: 0.85;">{c.get('explanation', '')}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown("#### 💡 Suggested Resolution")
            st.success(c.get("resolution") or "No specific resolution suggested.")
