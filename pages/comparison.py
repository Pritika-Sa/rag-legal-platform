import streamlit as st
import plotly.graph_objects as go
from database import crud
from agents.comparison_agent import compare_documents
from utils.theme import is_light_theme, render_header

render_header(
    "🔀",
    "Agreement Comparison",
    "Select two agreements to analyze structural differences, clause variations, and potential vulnerabilities between them.",
    badge="Agent 10"
)

documents = crud.get_all_documents()

if len(documents) < 2:
    st.info("⚠️ You need at least two documents in the workspace to perform comparison. Please upload another file.")
else:
    doc_options = {doc['id']: doc['name'] for doc in documents}
    
    col1, col2 = st.columns(2)
    with col1:
        doc_a_id = st.selectbox("Select Agreement A (Baseline):", options=list(doc_options.keys()), index=0)
    with col2:
        default_idx = 1 if len(doc_options) > 1 else 0
        doc_b_id = st.selectbox("Select Agreement B (Compare to):", options=list(doc_options.keys()), index=default_idx)
        
    if doc_a_id == doc_b_id:
        st.warning("⚠️ Please select two different agreements to compare.")
    else:
        if st.button("⚖️ Compare Agreements (Agent 10)"):
            with st.spinner("Agent 10 is analyzing document variations and risk changes..."):
                try:
                    clauses_a = crud.get_clauses_for_document(doc_a_id)
                    clauses_b = crud.get_clauses_for_document(doc_b_id)
                    doc_a_name = doc_options[doc_a_id]
                    doc_b_name = doc_options[doc_b_id]
                    
                    result = compare_documents(clauses_a, clauses_b, doc_a_name, doc_b_name)
                    
                    # Display Similarity Score Gauge
                    chart_text_color = "#31333F" if is_light_theme() else "#FFFFFF"
                    chart_grid_color = "#D5D5D5" if is_light_theme() else "#333333"
                    fig = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = result.similarity_score,
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        title = {'text': "Similarity Score", 'font': {'size': 24, 'color': chart_text_color}},
                        gauge = {
                            'axis': {'range': [0, 100], 'tickcolor': chart_grid_color},
                            'bar': {'color': "#636EFA"},
                            'bgcolor': "rgba(0,0,0,0)",
                            'borderwidth': 2,
                            'bordercolor': chart_grid_color,
                        }
                    ))
                    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font={'color': chart_text_color}, height=300)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.markdown("### 📋 Change Summary")
                    st.info(result.change_summary)
                    
                    col_add, col_rem, col_mod = st.columns(3)
                    with col_add:
                        st.markdown("#### 🟢 Added Clauses")
                        for ac in result.added_clauses:
                            st.markdown(f"- {ac}")
                    with col_rem:
                        st.markdown("#### 🔴 Removed Clauses")
                        for rc in result.removed_clauses:
                            st.markdown(f"- {rc}")
                    with col_mod:
                        st.markdown("#### 🟡 Modified Clauses")
                        for mc in result.modified_clauses:
                            st.markdown(f"- {mc}")
                            
                    st.markdown("### ⚠️ Risk Changes")
                    st.warning(result.risk_changes)
                    
                    st.markdown("### 📑 Detailed Difference Report")
                    st.write(result.difference_report)
                    
                    st.divider()
                    
                    # Create dictionary classifications for side-by-side view
                    dict_a = {c['classification']: c['text_content'] for c in clauses_a if c['classification']}
                    dict_b = {c['classification']: c['text_content'] for c in clauses_b if c['classification']}
                    all_classes = sorted(list(set(list(dict_a.keys()) + list(dict_b.keys()))))
                    
                    st.subheader("📖 Side-by-Side Reference")
                    for c_type in all_classes:
                        text_a = dict_a.get(c_type, "*(Clause not present in Agreement A)*")
                        text_b = dict_b.get(c_type, "*(Clause not present in Agreement B)*")
                        
                        with st.expander(f"Type: {c_type}"):
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.markdown(f"**Agreement A ({doc_a_name}):**")
                                st.info(text_a)
                            with col_b:
                                st.markdown(f"**Agreement B ({doc_b_name}):**")
                                st.info(text_b)
                                
                    crud.add_audit_log("compare_documents", f"Compared {doc_a_name} and {doc_b_name} with Agent 10")
                except Exception as e:
                    st.error(f"Failed to compile comparison: {e}")
