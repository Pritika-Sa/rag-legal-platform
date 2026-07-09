import streamlit as st
from database import crud
from utils.theme import render_header

render_header(
    "🕒",
    "Version History & Audit Trail",
    "Track modifications, view text histories, and restore previous versions of edited contract clauses.",
    badge="Governance"
)

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

if not doc_id:
    st.warning("⚠️ Please select an active document in the sidebar to view version history.")
else:
    st.info(f"Version Logs for: **{doc_name}**")
    
    clauses = crud.get_clauses_for_document(doc_id)
    
    if not clauses:
        st.info("No clause data available.")
    else:
        # Find clauses that have versions > 1
        modified_clauses = [c for c in clauses if c['version'] > 1]
        
        if not modified_clauses:
            st.success("✅ No clauses have been modified yet. All clauses are at baseline Version 1.")
        else:
            st.markdown(f"Found **{len(modified_clauses)}** modified clauses:")
            
            clause_options = {c['id']: f"{c['section_name']} (Current: V{c['version']})" for c in modified_clauses}
            
            selected_clause_id = st.selectbox(
                "Select clause to inspect history:",
                options=list(clause_options.keys()),
                format_func=lambda x: clause_options[x]
            )
            
            # Fetch version history
            versions = crud.get_clause_versions(selected_clause_id)
            
            if not versions:
                st.info("No detailed version records found.")
            else:
                for idx, v in enumerate(versions):
                    version_num = len(versions) - idx
                    
                    st.markdown(
                        f"""
                        <div style="background-color: var(--secondary-background-color); border: 1px solid rgba(128,128,128,0.2); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                            <div style="display:flex; justify-content:space-between; margin-bottom: 10px;">
                                <strong style="color: #636EFA; font-size: 1.1rem;">Version {version_num + 1} &rarr; Version {version_num}</strong>
                                <span style="font-size: 0.85rem; color: var(--text-color); opacity: 0.65;">🕒 {v['timestamp']}</span>
                            </div>
                            <div style="margin-bottom: 10px;">
                                <strong>Description:</strong> <em>{v['change_description']}</em>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Previous Text:**")
                        st.info(v['previous_text'])
                    with col2:
                        st.markdown("**New Text:**")
                        st.success(v['new_text'])
                        
                    # Agent 15 Analysis
                    with st.expander("🧠 Agent 15: Version Intelligence Analysis"):
                        with st.spinner("Agent 15 is evaluating the impact of this edit..."):
                            from agents.version_intelligence_agent import analyze_version_diff
                            ai_diff = analyze_version_diff(v['previous_text'], v['new_text'])
                            
                            st.markdown(f"**📝 Clause Changes:** {ai_diff.clause_changes}")
                            st.markdown(f"**⚠️ Risk Changes:** {ai_diff.risk_changes}")
                            st.markdown(f"**⚖️ Compliance Changes:** {ai_diff.compliance_changes}")
                            st.markdown(f"**🌍 Jurisdiction Changes:** {ai_diff.jurisdiction_changes}")
                            st.markdown(f"**📋 Obligation Changes:** {ai_diff.obligation_changes}")
                        
                    # Restore Button
                    if st.button("Restore this version", key=f"restore_{v['id']}"):
                        with st.spinner("Restoring clause text..."):
                            try:
                                # Restore old text
                                new_v = crud.update_clause_text(
                                    clause_id=selected_clause_id,
                                    new_text=v['previous_text'],
                                    change_description=f"Restored to state from {v['timestamp']}"
                                )
                                st.success(f"Restored clause successfully! Now at version {new_v}.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to restore: {e}")
                                
                    st.markdown("---")
