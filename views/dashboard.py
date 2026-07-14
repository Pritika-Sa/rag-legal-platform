import streamlit as st
from database import crud
from utils import visualizer
from utils.theme import render_header, render_metric_card


def _clickable_metric_card(nav_key: str, target_page: str, label: str, value, icon: str) -> None:
    """Renders a metric card as a real st.button (not render_metric_card's
    HTML) so the whole card is natively, reliably clickable — an earlier
    version tried overlaying an invisible button on top of the separate
    markdown card via CSS, but Streamlit's own Emotion-generated button
    styles kept winning the width/height cascade even against !important.
    Streamlit button labels do support "\\n\\n" line breaks and **bold**
    markdown (verified empirically), so the icon/value/label 3-line layout
    is preserved; app.py's "dash_nav_" CSS block restyles the button and
    its bolded value to match render_metric_card's visual weight."""
    with st.container(key=nav_key):
        label_text = f"{icon}\n\n**{value}**\n\n{label}"
        if st.button(label_text, key=f"navgo_{target_page}", use_container_width=True, help=f"View {label}"):
            st.session_state.current_page = target_page
            st.rerun()


def render():
    # Get active document from session state
    doc_id = st.session_state.active_doc_id
    doc_name = st.session_state.active_doc_name

    render_header(
        "📊",
        "Platform Dashboard",
        "Next-generation AI legal intelligence platform",
        badge="Overview",
        doc_name=doc_name,
    )

    if not doc_id:
        st.warning("⚠️ Please select an active document in the sidebar to view its dashboard metrics.")
        return

    user_id = st.session_state.user["id"]
    metrics = crud.get_dashboard_metrics(doc_id=doc_id, user_id=user_id)
    clauses = crud.get_clauses_for_document(doc_id=doc_id)
    document = crud.get_document_by_id(doc_id)
    doc_type_display = (document.get("document_type") if document else None) or "Unknown Document"

    # Visual Metrics Grid — Total Clauses / Risky Clauses / Contradictions
    # link through to the page that explains that number.
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _clickable_metric_card(
            "dash_nav_total_clauses", "clause_analysis",
            "Total Clauses", metrics["total_clauses"], "📑",
        )
    with col2:
        _clickable_metric_card(
            "dash_nav_risky_clauses", "risk_analysis",
            "Risky Clauses (High/Med)", metrics["risky_clauses"], "⚠️",
        )
    with col3:
        _clickable_metric_card(
            "dash_nav_contradictions", "contradiction",
            "Contradictions", metrics["total_contradictions"], "⚡",
        )
    with col4:
        st.markdown(render_metric_card("Document Type", doc_type_display, "📄", "var(--lq-success)"), unsafe_allow_html=True)

    st.markdown("---")

    # Visual Charts
    if clauses:
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            radar_fig = visualizer.generate_risk_radar_chart(metrics["risk_distribution"])
            st.plotly_chart(radar_fig, use_container_width=True)

            risk_dist = metrics["risk_distribution"]
            total_clauses = sum(risk_dist.get(level, 0) for level in ["High", "Medium", "Low", "None"])
            bullet_lines = []
            for level in ["High", "Medium", "Low", "None"]:
                count = risk_dist.get(level, 0)
                pct = round(100 * count / total_clauses) if total_clauses else 0
                bullet_lines.append(f"- **{level} Risk:** {count} clause{'s' if count != 1 else ''} ({pct}%)")
            st.markdown("\n".join(bullet_lines))
        with chart_col2:
            bar_fig = visualizer.generate_category_bar_chart(clauses)
            st.plotly_chart(bar_fig, use_container_width=True)
    else:
        st.info("Upload and parse a document to view risk distributions.")
