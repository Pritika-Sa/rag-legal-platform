import streamlit as st
from database import crud
from agents.simplification_agent import simplify_clause
from utils.theme import render_header

render_header(
    "✍️",
    "Clause Simplification & Redrafting",
    "Convert dense legalese into plain English, edit the redrafts, and save changes.",
    badge="Agent 7"
)

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

if not doc_id:
    st.warning("⚠️ Please select an active document in the sidebar to redraft clauses.")
else:
    st.info(f"Editing Document: **{doc_name}**")
    
    clauses = crud.get_clauses_for_document(doc_id)
    
    if not clauses:
        st.info("No clauses parsed for this document.")
    else:
        clause_options = {c['id']: f"{c['section_name']} (V{c['version']})" for c in clauses}
        
        selected_clause_id = st.selectbox(
            "Select a clause to simplify/redraft:",
            options=list(clause_options.keys()),
            format_func=lambda x: clause_options[x]
        )
        
        # Fetch chosen clause details
        clause = next(c for c in clauses if c['id'] == selected_clause_id)
        
        if 'simplification_result' not in st.session_state:
            st.session_state.simplification_result = None
            st.session_state.simplified_clause_id = None
            
        # Reset state if clause selection changes
        if st.session_state.simplified_clause_id != selected_clause_id:
            st.session_state.simplification_result = None
            st.session_state.simplified_clause_id = selected_clause_id
        
        if st.button("Simplify with AI (Agent 7)"):
            with st.spinner("Agent 7 is translating legalese to plain English..."):
                try:
                    result = simplify_clause(clause['text_content'])
                    st.session_state.simplification_result = result
                except Exception as e:
                    st.error(f"Failed to simplify: {e}")
                    
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Original Legalese Text")
            st.markdown(
                f"""
                <div style="background-color: var(--secondary-background-color); padding: 15px; border-radius: 8px; border-left: 3px solid #636EFA; height: 350px; overflow-y: auto;">
                    <p style="font-family: monospace; font-size: 0.95rem; line-height: 1.6; color: var(--text-color); opacity: 0.85;">{clause['text_content']}</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            
        with col2:
            st.subheader("Plain-English Simplification")
            
            if st.session_state.simplification_result:
                default_text = st.session_state.simplification_result.simplified_clause
            else:
                default_text = clause['simplification'] or clause['text_content']
                
            edited_text = st.text_area(
                "Customize/Edit the simplified text here:",
                value=default_text,
                height=350,
                key=f"edit_area_{selected_clause_id}_{'ai' if st.session_state.simplification_result else 'db'}"
            )
            
        if st.session_state.simplification_result:
            st.markdown("---")
            st.markdown("### 🧠 AI Analysis")
            col_exp, col_rw = st.columns(2)
            with col_exp:
                st.info("**Explanation**")
                st.write(st.session_state.simplification_result.explanation)
            with col_rw:
                st.success("**Real-World Example**")
                st.write(st.session_state.simplification_result.real_world_example)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        change_desc = st.text_input(
            "Describe the reason for modification (optional):",
            value="Simplified legalese for better clarity"
        )
        
        if st.button("Save & Commit New Clause Version"):
            if not edited_text.strip():
                st.error("Text cannot be empty!")
            else:
                with st.spinner("Saving new version to database..."):
                    try:
                        new_version = crud.update_clause_text(
                            clause_id=selected_clause_id,
                            new_text=edited_text.strip(),
                            change_description=change_desc
                        )
                        st.success(f"🎉 Clause updated successfully! Saved as Version {new_version}.")
                        
                        # Clear state to reset
                        st.session_state.simplification_result = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update clause: {e}")
