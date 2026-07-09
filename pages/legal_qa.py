import streamlit as st
from database import crud
from agents.qa_agent import answer_legal_question
from utils.theme import render_header

render_header(
    "💬",
    "Semantic Q&A & Search",
    "Ask questions about the contract repository or the active document. LQ-RAG uses hybrid retrieval and strict audit validation to answer.",
    badge="Agent 9"
)

# Query configuration
search_scope = st.radio("Search Scope:", ["Active Document Only", "All Documents in Workspace"])

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

target_doc_id = None
if search_scope == "Active Document Only":
    if not doc_id:
        st.warning("⚠️ Please select an active document first, or search across the entire workspace.")
        st.stop()
    else:
        st.info(f"Searching within active document: **{doc_name}**")
        target_doc_id = doc_id
else:
    st.info("Searching across all uploaded agreements.")

# Chat history initialization
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # Render structured payload if it's an assistant response
        if msg["role"] == "assistant" and "result_payload" in msg:
            res = msg["result_payload"]
            
            score_color = "#00CC96" if res.confidence_score > 85 else "#FECB52" if res.confidence_score > 60 else "#EF553B"
            st.markdown(
                f"""
                <div style="margin-top: 10px; margin-bottom: 10px;">
                    <span style="background-color: rgba(128,128,128,0.15); border: 1px solid {score_color}; color: {score_color}; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: bold;">
                        Agent Confidence: {res.confidence_score}/100
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            with st.expander("🔍 View Supporting Clauses & Citations"):
                if res.supporting_clauses:
                    st.markdown("**Supporting Clauses:**")
                    for sc in res.supporting_clauses:
                        st.markdown(f"- {sc}")
                
                if res.citation_references:
                    st.markdown("**Citations:**")
                    for cit in res.citation_references:
                        # Resolve Document ID if it's a numeric ID
                        doc_title = f"Doc ID {cit.document_id}"
                        try:
                            if cit.document_id.isdigit():
                                db_doc = crud.get_document_by_id(int(cit.document_id))
                                if db_doc:
                                    doc_title = db_doc['name']
                            else:
                                # Sometimes document_id in Chroma is a string, let's try our best to parse it
                                doc_id_str = cit.document_id.split('_')[0]
                                if doc_id_str.isdigit():
                                    db_doc = crud.get_document_by_id(int(doc_id_str))
                                    if db_doc:
                                        doc_title = db_doc['name']
                        except:
                            pass
                            
                        st.markdown(f"- **{doc_title}**: {cit.section_name}\n  > {cit.text_snippet[:150]}...")

# Chat Input
if prompt := st.chat_input("Ask a legal question... (e.g., 'What is the liability cap?')"):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Process assistant response
    with st.chat_message("assistant"):
        with st.spinner("Agent 9 is retrieving and validating answers..."):
            try:
                # Stringify target doc if present
                doc_id_str = str(target_doc_id) if target_doc_id else None
                result = answer_legal_question(prompt, doc_id_str)
                
                st.markdown(result.answer)
                
                score_color = "#00CC96" if result.confidence_score > 85 else "#FECB52" if result.confidence_score > 60 else "#EF553B"
                st.markdown(
                    f"""
                    <div style="margin-top: 10px; margin-bottom: 10px;">
                        <span style="background-color: rgba(128,128,128,0.15); border: 1px solid {score_color}; color: {score_color}; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: bold;">
                            Agent Confidence: {result.confidence_score}/100
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                with st.expander("🔍 View Supporting Clauses & Citations"):
                    if result.supporting_clauses:
                        st.markdown("**Supporting Clauses:**")
                        for sc in result.supporting_clauses:
                            st.markdown(f"- {sc}")
                    
                    if result.citation_references:
                        st.markdown("**Citations:**")
                        for cit in result.citation_references:
                            doc_title = f"Doc ID {cit.document_id}"
                            try:
                                if cit.document_id.isdigit():
                                    db_doc = crud.get_document_by_id(int(cit.document_id))
                                    if db_doc:
                                        doc_title = db_doc['name']
                                else:
                                    doc_id_str = cit.document_id.split('_')[0]
                                    if doc_id_str.isdigit():
                                        db_doc = crud.get_document_by_id(int(doc_id_str))
                                        if db_doc:
                                            doc_title = db_doc['name']
                            except:
                                pass
                                
                            st.markdown(f"- **{doc_title}**: {cit.section_name}\n  > {cit.text_snippet[:150]}...")
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": result.answer,
                    "result_payload": result
                })
                
                # Display LQ-RAG loop metadata
                if result.iteration_count > 1 or result.refinement_history:
                    with st.expander(f"🔄 LQ-RAG Recursive Loop ({result.iteration_count} iterations)"):
                        st.markdown(f"**Iterations until convergence:** {result.iteration_count}")
                        if result.refinement_history:
                            for rh in result.refinement_history:
                                st.markdown(f"- {rh}")
                        else:
                            st.markdown("Converged on first attempt — no refinement needed.")

                # Evaluate Hallucination with Agent 14
                with st.spinner("Agent 14 is evaluating output for hallucinations and faithfulness..."):
                    from agents.hallucination_agent import evaluate_hallucination
                    eval_result = evaluate_hallucination(result.context_used, result.answer)

                    st.markdown("---")
                    st.markdown("### 🛡️ Agent 14: Audit Verification")
                    
                    # Layout scores
                    col_ts, col_hs = st.columns(2)
                    with col_ts:
                        ts_color = "#00CC96" if eval_result.trust_score >= 80 else "#FECB52" if eval_result.trust_score >= 50 else "#EF553B"
                        st.markdown(
                            f"""
                            <div style="background-color: rgba(128,128,128,0.12); border-left: 4px solid {ts_color}; padding: 10px; border-radius: 4px;">
                                <strong>Trust Score:</strong> {eval_result.trust_score}/100
                            </div>
                            """, unsafe_allow_html=True
                        )
                    with col_hs:
                        hs_color = "#00CC96" if eval_result.hallucination_score < 20 else "#FECB52" if eval_result.hallucination_score < 50 else "#EF553B"
                        st.markdown(
                            f"""
                            <div style="background-color: rgba(128,128,128,0.12); border-left: 4px solid {hs_color}; padding: 10px; border-radius: 4px;">
                                <strong>Hallucination Score:</strong> {eval_result.hallucination_score}/100
                            </div>
                            """, unsafe_allow_html=True
                        )
                        
                    if eval_result.unsupported_statements and eval_result.unsupported_statements[0] != "None":
                        st.warning("⚠️ **Unsupported Statements Detected:**")
                        for stmt in eval_result.unsupported_statements:
                            st.write(f"- {stmt}")
                            
                crud.add_audit_log("agent9_qa", f"LQ-RAG Query: '{prompt}' (Scope: {search_scope}, Confidence: {result.confidence_score}, Trust: {eval_result.trust_score})")
            except Exception as e:
                st.error(f"Failed to answer question: {e}")
