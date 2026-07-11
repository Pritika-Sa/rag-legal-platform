import streamlit as st
from database import crud
from utils import visualizer
from utils.theme import render_header, render_metric_card


def render():
    render_header(
        "📊",
        "Platform Dashboard",
        "Next-generation AI legal intelligence platform",
        badge="Overview"
    )

    # Get active document from session state
    doc_id = st.session_state.active_doc_id
    doc_name = st.session_state.active_doc_name

    if doc_id:
        st.info(f"Viewing metrics for Active Document: **{doc_name}**")
        metrics = crud.get_dashboard_metrics(doc_id=doc_id)
        clauses = crud.get_clauses_for_document(doc_id=doc_id)
        document = crud.get_document_by_id(doc_id)
        doc_type_display = (document.get("document_type") if document else None) or "Unknown Document"
    else:
        st.warning("No active document selected. Showing aggregate workspace metrics.")
        user_id = st.session_state.user["id"]
        metrics = crud.get_dashboard_metrics(user_id=user_id)
        # For aggregate workspace, fetch clauses from all of this user's documents
        clauses = []
        documents = crud.get_all_documents(user_id=user_id)
        for doc in documents:
            clauses.extend(crud.get_clauses_for_document(doc['id']))
        doc_type_display = "Not Selected"

    # Visual Metrics Grid
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(render_metric_card("Total Clauses", metrics["total_clauses"], "📑", "var(--lq-accent)"), unsafe_allow_html=True)
    with col2:
        st.markdown(render_metric_card("Risky Clauses (High/Med)", metrics["risky_clauses"], "⚠️", "var(--lq-warning)"), unsafe_allow_html=True)
    with col3:
        st.markdown(render_metric_card("Contradictions", metrics["total_contradictions"], "⚡", "var(--lq-danger)"), unsafe_allow_html=True)
    with col4:
        st.markdown(render_metric_card("Document Type", doc_type_display, "📄", "var(--lq-success)"), unsafe_allow_html=True)

    st.markdown("---")

    # Visual Charts
    if clauses:
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            pie_fig = visualizer.generate_risk_pie_chart(metrics["risk_distribution"])
            st.plotly_chart(pie_fig, use_container_width=True)
        with chart_col2:
            bar_fig = visualizer.generate_category_bar_chart(clauses)
            st.plotly_chart(bar_fig, use_container_width=True)
    else:
        st.info("Upload and parse a document to view risk distributions.")
