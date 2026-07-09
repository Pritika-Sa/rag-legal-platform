import streamlit as st
import pandas as pd
from database import crud
from utils import visualizer
from agents.risk_evolution_agent import analyze_risk_evolution
from utils.theme import render_header

render_header(
    "📈",
    "Contract Risk Profile Evolution",
    "Track the progress of risk mitigation across different iterations and versions of the agreement.",
    badge="Agent 13"
)

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

if not doc_id:
    st.warning("⚠️ Please select an active document in the sidebar to view risk evolution.")
else:
    st.info(f"Tracking Evolution for: **{doc_name}**")
    
    clauses = crud.get_clauses_for_document(doc_id)
    
    if not clauses:
        st.info("No clause data available.")
    else:
        if st.button("Generate AI Risk Evolution (Agent 13)"):
            with st.spinner("Agent 13 is analyzing multi-version risk trajectories..."):
                try:
                    # Calculate average risk score: High = 9, Medium = 5, Low = 2, None = 0
                    def get_risk_score(level):
                        if level == 'High': return 9
                        if level == 'Medium': return 5
                        if level == 'Low': return 2
                        return 0
                        
                    total_clauses = len(clauses)
                    max_v = max(c['version'] for c in clauses)
                    versions_data = []
                    
                    # Pre-calculate data for Agent 13
                    for v in range(1, max_v + 1):
                        v_high_count = 0
                        v_sum_score = 0
                        
                        for c in clauses:
                            if c['version'] > v:
                                original_lvl = c['risk_level'] if c['risk_level'] in ['High', 'Medium'] else 'High' # Assume unmitigated was high
                                v_high_count += 1 if original_lvl == 'High' else 0
                                v_sum_score += get_risk_score(original_lvl)
                            else:
                                v_high_count += 1 if c['risk_level'] == 'High' else 0
                                v_sum_score += get_risk_score(c['risk_level'])
                                
                        avg_score = round(v_sum_score / total_clauses, 2) if total_clauses > 0 else 0
                        versions_data.append({
                            "version": f"V{v}",
                            "avg_risk": avg_score,
                            "high_count": v_high_count,
                            "changes_summary": "Initial parse" if v == 1 else "Various user edits to clauses"
                        })
                        
                    result = analyze_risk_evolution(versions_data)
                    
                    st.subheader("📊 Risk Trend Line Chart")
                    
                    # Convert timeline back to format needed for visualizer
                    chart_data = [{"version": pt.version, "avg_risk": pt.avg_risk_score, "high_count": pt.high_count} for pt in result.risk_timeline]
                    fig = visualizer.generate_risk_evolution_chart(chart_data)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.markdown("### 🧠 AI Trend Analysis")
                    st.info(result.risk_trend)
                    
                    col_red, col_inc = st.columns(2)
                    with col_red:
                        st.markdown("#### 📉 Risk Reduction Drivers")
                        for r in result.risk_reduction_factors:
                            st.markdown(f"- {r}")
                    with col_inc:
                        st.markdown("#### 📈 Risk Increase Factors")
                        for i in result.risk_increase_factors:
                            st.markdown(f"- {i}")
                            
                    # Downloadable report (CSV)
                    df = pd.DataFrame([pt.model_dump() for pt in result.risk_timeline])
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Risk Timeline Data (CSV)",
                        data=csv,
                        file_name=f"risk_evolution_{doc_name.replace(' ', '_')}.csv",
                        mime='text/csv'
                    )
                    
                    crud.add_audit_log("risk_evolution", f"Agent 13 generated risk evolution for '{doc_name}'")
                except Exception as e:
                    st.error(f"Failed to generate evolution analysis: {e}")
