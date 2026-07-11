import os
import streamlit as st
from agents.orchestrator import run_orchestration
from database import crud
from utils.theme import render_header, render_metric_card

render_header(
    "📤",
    "Upload & Parse Legal Documents",
    "Upload a PDF or Word (.docx) contract to parse its clauses and perform risk analysis.",
    badge="Ingestion"
)

# The analysis summary is stashed in session_state (not shown inline, then
# immediately overwritten) because the "Force sidebar refresh" st.rerun()
# below would otherwise wipe any st.success/st.warning shown before it on
# the same run. Popped (read + cleared) so it only shows once, right after
# the triggering rerun, not on every subsequent page visit.
if "last_analysis_summary" in st.session_state:
    summary = st.session_state.pop("last_analysis_summary")
    st.success("🎉 Multi-agent analysis complete!")
    st.markdown("#### 📋 Analysis Summary")
    parsing_ok = not summary.get("parsing_quality_warning")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(render_metric_card(
            "Clause Count", summary.get("clause_count", 0), "📑"
        ), unsafe_allow_html=True)
    with m2:
        st.markdown(render_metric_card(
            "Legal Risk Score", f"{summary.get('document_risk_score', 0)}/100", "⚠️", "var(--lq-warning)"
        ), unsafe_allow_html=True)
    with m3:
        st.markdown(render_metric_card(
            "Authenticity Score", f"{summary.get('authenticity_score', 0)}/100", "🛡️",
            "var(--lq-success)" if parsing_ok else "var(--lq-danger)"
        ), unsafe_allow_html=True)
    with m4:
        st.markdown(render_metric_card(
            "Parsing Quality", "✅ Good" if parsing_ok else "⚠️ Check",
            "🔍", "var(--lq-success)" if parsing_ok else "var(--lq-danger)"
        ), unsafe_allow_html=True)

    if summary.get("parsing_quality_warning"):
        st.warning(f"⚠️ {summary['parsing_quality_warning']}")
    if summary.get("authenticity_warnings"):
        st.info("🛡️ Authenticity notes: " + "; ".join(summary["authenticity_warnings"]))
    if summary.get("document_risk_recommendations"):
        st.success(f"💡 Recommendations: {summary['document_risk_recommendations']}")

    st.info(f"Active workspace document set to **{summary.get('doc_name', '')}**. Head to the Dashboard or Clause Analysis pages to view results.")
    st.markdown("---")

uploaded_file = st.file_uploader("Choose a legal file", type=["pdf", "docx"])

if uploaded_file is not None:
    # Save the file locally, namespaced per-user so two users uploading a
    # same-named file don't overwrite each other on disk.
    uploads_dir = os.path.join(os.getenv("UPLOADS_DIR", "uploads"), str(st.session_state.user["id"]))
    os.makedirs(uploads_dir, exist_ok=True)

    file_path = os.path.join(uploads_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    st.success(f"File saved successfully to {file_path}")
    
    # Process file button
    if st.button("🚀 Analyze Document"):
        with st.spinner("Executing Multi-Agent LangGraph Orchestration... (Parsing & Risk Assessment)"):
            try:
                # Run the LangGraph orchestration flow
                result = run_orchestration(file_path, user_id=st.session_state.user["id"])
                
                if result.get("error") and "already analyzed" in result["error"].lower():
                    st.warning("⚠️ This document has already been analyzed and is available in the workspace.")
                    # Set as active anyway
                    st.session_state.active_doc_id = result["doc_id"]
                    st.session_state.active_doc_name = uploaded_file.name
                    st.rerun()
                elif result.get("error"):
                    st.error(f"❌ Analysis failed: {result['error']}")
                else:
                    st.session_state.active_doc_id = result["doc_id"]
                    st.session_state.active_doc_name = uploaded_file.name
                    st.session_state.last_analysis_summary = {
                        "doc_name": uploaded_file.name,
                        "clause_count": len(result.get("db_clauses", [])),
                        "document_risk_score": result.get("document_risk_score", 0),
                        "document_risk_recommendations": result.get("document_risk_recommendations", ""),
                        "authenticity_score": result.get("authenticity_score", 0),
                        "authenticity_warnings": result.get("authenticity_warnings", []),
                        "parsing_quality_warning": result.get("parsing_quality_warning"),
                    }
                    crud.add_audit_log(
                        "analysis_completed",
                        f"Completed multi-agent processing for '{uploaded_file.name}'"
                    )
                    # Force sidebar refresh (also displays last_analysis_summary, stashed above)
                    st.rerun()
            except Exception as e:
                st.error(f"❌ An error occurred during orchestrator execution: {e}")
                
st.markdown("---")

# List existing documents in system
st.subheader("signed agreements in Workspace")
docs = crud.get_all_documents(user_id=st.session_state.user["id"])
if docs:
    for doc in docs:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"📄 **{doc['name']}** — uploaded on {doc['upload_date']}")
        with col2:
            if st.button("Set Active", key=f"set_{doc['id']}"):
                st.session_state.active_doc_id = doc['id']
                st.session_state.active_doc_name = doc['name']
                st.rerun()
else:
    st.info("No documents analyzed yet. Please upload a file to begin.")
