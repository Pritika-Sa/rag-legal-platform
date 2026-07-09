import streamlit as st
from database import crud
from utils.theme import render_header

render_header(
    "🌐",
    "Legal Clause Translation",
    "Translate contract terms into multiple languages while preserving precise legal definitions and context.",
    badge="Agent 8"
)

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

if not doc_id:
    st.warning("⚠️ Please select an active document in the sidebar to translate clauses.")
else:
    st.info(f"Translating Terms from: **{doc_name}**")
    
    clauses = crud.get_clauses_for_document(doc_id)
    
    if not clauses:
        st.info("No clauses parsed for this document.")
    else:
        clause_options = {c['id']: c['section_name'] for c in clauses}
        
        selected_clause_id = st.selectbox(
            "Select clause to translate:",
            options=list(clause_options.keys()),
            format_func=lambda x: clause_options[x]
        )
        
        clause = next(c for c in clauses if c['id'] == selected_clause_id)
        
        languages = ["Tamil", "Hindi"]
        target_lang = st.selectbox("Select Target Language:", languages)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Original Text:**")
            st.info(clause['text_content'])
            
        with col2:
            st.markdown(f"**Translated Text ({target_lang}):**")
            
            # Button to trigger translation
            if st.button(f"Translate to {target_lang} (Agent 8)"):
                with st.spinner(f"Agent 8 is translating to {target_lang}..."):
                    try:
                        from agents.translation_agent import translate_clause
                        
                        result = translate_clause(clause['text_content'], target_lang)
                        
                        st.success("Translation complete!")
                        
                        # Confidence Score styling
                        score_color = "#00CC96" if result.confidence_score > 85 else "#FECB52" if result.confidence_score > 60 else "#EF553B"
                        st.markdown(
                            f"""
                            <div style="margin-bottom: 10px;">
                                <span style="background-color: rgba(128,128,128,0.15); border: 1px solid {score_color}; color: {score_color}; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: bold;">
                                    Confidence Score: {result.confidence_score}/100
                                </span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                        st.markdown(
                            f"""
                            <div style="background-color: var(--secondary-background-color); padding: 15px; border-radius: 8px; border-left: 3px solid #636EFA;">
                                <p style="font-size: 0.95rem; line-height: 1.5; color: var(--text-color);">{result.translated_clause}</p>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        
                        # Log translation audit
                        crud.add_audit_log("clause_translation", f"Translated clause ID {clause['id']} ('{clause['section_name']}') to {target_lang} (Conf: {result.confidence_score})")
                    except Exception as e:
                        st.error(f"Translation failed: {e}")
