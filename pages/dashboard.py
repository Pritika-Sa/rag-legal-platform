import streamlit as st
from database import crud
from utils import visualizer
from utils.theme import render_header, render_metric_card

render_header(
    "📊",
    "Platform Dashboard",
    "Next-generation AI legal intelligence platform powered by LangGraph, Groq & MongoDB.",
    badge="Overview"
)

# Get active document from session state
doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

if doc_id:
    st.info(f"Viewing metrics for Active Document: **{doc_name}**")
    metrics = crud.get_dashboard_metrics(doc_id=doc_id)
    clauses = crud.get_clauses_for_document(doc_id=doc_id)
    active_doc = crud.get_document_by_id(doc_id)
    authenticity_display = f"{active_doc.get('authenticity_score')}/100" if active_doc and active_doc.get("authenticity_score") is not None else "Not yet analyzed"
else:
    st.warning("No active document selected. Showing aggregate workspace metrics.")
    metrics = crud.get_dashboard_metrics()
    # For aggregate workspace, fetch clauses from all documents
    clauses = []
    documents = crud.get_all_documents()
    for doc in documents:
        clauses.extend(crud.get_clauses_for_document(doc['id']))
    scored_docs = [d for d in documents if d.get("authenticity_score") is not None]
    authenticity_display = (
        f"{round(sum(d['authenticity_score'] for d in scored_docs) / len(scored_docs))}/100 (avg)"
        if scored_docs else "Not yet analyzed"
    )

# Visual Metrics Grid
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown(render_metric_card("Documents", metrics["total_documents"], "📁", "var(--lq-accent)"), unsafe_allow_html=True)
with col2:
    st.markdown(render_metric_card("Total Clauses", metrics["total_clauses"], "📑", "var(--lq-accent)"), unsafe_allow_html=True)
with col3:
    st.markdown(render_metric_card("Risky Clauses (High/Med)", metrics["risky_clauses"], "⚠️", "var(--lq-warning)"), unsafe_allow_html=True)
with col4:
    st.markdown(render_metric_card("Contradictions", metrics["total_contradictions"], "⚡", "var(--lq-danger)"), unsafe_allow_html=True)
with col5:
    st.markdown(render_metric_card("Authenticity Score", authenticity_display, "🛡️", "var(--lq-success)"), unsafe_allow_html=True)

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

st.markdown("---")

# Recent Audit Logs
st.subheader("📜 Recent System & Audit Activity")
logs = crud.get_audit_logs(limit=10)
if logs:
    for log in logs:
        # Style logs depending on severity/type of action
        icon = "⚙️"
        if "upload" in log['action']:
            icon = "📤"
        elif "risk" in log['action'] or "contradiction" in log['action']:
            icon = "⚠️"
        elif "update" in log['action']:
            icon = "✏️"
            
        st.markdown(f"**{icon} {log['action'].upper()}** — *{log['timestamp']}*")
        st.write(log['details'])
        st.markdown("---")
else:
    st.text("No audit logs available.")
