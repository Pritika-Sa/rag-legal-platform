import streamlit as st
import pandas as pd
import json
from database import crud
from agents.clause_identifier_agent import identify_clauses
from agents.importance_agent import assess_clause_importance
from utils.theme import render_header

render_header(
    "🔍",
    "Clause Analysis & Classification",
    "Browse clause breakdowns, run hybrid identification, and audit clause importance and impact.",
    badge="Agents 2 · 3 · 6"
)

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

# Cached function for Agent 3 Importance Audit
@st.cache_data(show_spinner=True)
def run_importance_audit(clauses_json: str) -> list:
    """Invokes Agent 3 to evaluate legal significance and financial impact of each clause."""
    clauses_list = json.loads(clauses_json)
    audited_results = []
    
    for c in clauses_list:
        try:
            audit = assess_clause_importance(c['section_name'], c['text_content'])
            audited_results.append({
                "id": c['id'],
                "section_name": c['section_name'],
                "text_content": c['text_content'],
                "score": audit.importance_score,
                "category": audit.importance_category,
                "reasoning": audit.reasoning,
                "legal_analysis": audit.legal_significance_analysis,
                "financial_analysis": audit.financial_impact_analysis
            })
        except Exception as e:
            audited_results.append({
                "id": c['id'],
                "section_name": c['section_name'],
                "text_content": c['text_content'],
                "score": 20,
                "category": "Informational",
                "reasoning": f"Analysis failed: {str(e)}",
                "legal_analysis": "Error occurred",
                "financial_analysis": "Error occurred"
            })
            
    return audited_results

if not doc_id:
    st.warning("⚠️ Please select an active document in the sidebar or upload one to begin.")
else:
    st.info(f"Analyzing Document: **{doc_name}**")
    
    # Get all clauses
    clauses = crud.get_clauses_for_document(doc_id)
    
    if not clauses:
        st.info("No clauses parsed for this document.")
    else:
        PREVIEW_CHARS = 400

        def truncate_preview(text: str, max_chars: int = PREVIEW_CHARS):
            """Cuts long clause text at the nearest word boundary so cards
            across every tab stay scannable instead of showing a wall of
            text; returns (preview_text, was_truncated)."""
            if not text or len(text) <= max_chars:
                return text, False
            cut = text[:max_chars]
            last_space = cut.rfind(" ")
            if last_space > max_chars * 0.6:
                cut = cut[:last_space]
            return cut.rstrip() + " …", True

        # Create Streamlit tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            "Standard Clause Breakdown",
            "Hybrid Clause Identification Agent (Agent 2)",
            "Clause Importance Auditor (Agent 3)",
            "Clause Impact Analysis (Agent 6)"
        ])

        with tab1:
            # Get unique classifications for filtering
            classifications = list(set([c['classification'] for c in clauses if c['classification']]))
            classifications.insert(0, "All")
            
            # Filter selector
            selected_class = st.selectbox("Filter by Clause Classification:", classifications)
            
            # Filter clauses
            filtered_clauses = clauses
            if selected_class != "All":
                filtered_clauses = [c for c in clauses if c['classification'] == selected_class]
                
            st.markdown(f"Showing **{len(filtered_clauses)}** clauses:")
            
            for c in filtered_clauses:
                # Colors for risk levels
                risk_color = "#00CC96"  # None
                if c['risk_level'] == "High":
                    risk_color = "#EF553B"
                elif c['risk_level'] == "Medium":
                    risk_color = "#FECB52"
                elif c['risk_level'] == "Low":
                    risk_color = "#636EFA"

                clause_text = c['text_content'] or ""
                preview_text, was_truncated = truncate_preview(clause_text)
                length_badge = (
                    f'<span style="background: rgba(128,128,128,0.15); color: var(--text-color); '
                    f'padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; margin-left: 10px;">'
                    f'📏 {len(clause_text):,} chars</span>'
                    if was_truncated else ""
                )

                st.markdown(
                    f"""
                    <div style="
                        border: 1px solid rgba(128, 128, 128, 0.25);
                        border-radius: 8px;
                        padding: 15px;
                        margin-bottom: 15px;
                        background: var(--secondary-background-color);
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <h4 style="margin: 0; color: var(--text-color);">📌 {c['section_name']}</h4>
                            <span style="
                                background-color: {risk_color};
                                color: #121212;
                                font-weight: bold;
                                padding: 3px 10px;
                                border-radius: 4px;
                                font-size: 0.8rem;
                            ">{c['risk_level'].upper()} RISK</span>
                        </div>
                        <div style="margin-bottom: 10px;">
                            <span style="background: rgba(99, 110, 250, 0.2); color: #636EFA; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: 500;">
                                🏷️ Type: {c['classification']}
                            </span>
                            <span style="background: rgba(128, 128, 128, 0.18); color: var(--text-color); padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: 500; margin-left: 10px;">
                                📁 Risk Cat: {c['risk_category']}
                            </span>
                            {f'<span style="background: rgba(128,128,128,0.15); color: var(--text-color); padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; margin-left: 10px;">📄 Page {c["page_num"]}</span>' if c['page_num'] else ''}
                            {length_badge}
                        </div>
                        <p style="font-size: 0.95rem; line-height: 1.5; color: var(--text-color); opacity: 0.85; background: var(--background-color); padding: 12px; border-radius: 6px; border-left: 3px solid #636EFA;">
                            {preview_text}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if was_truncated:
                    with st.expander(f"📄 Show full clause text ({len(clause_text):,} characters)"):
                        st.write(clause_text)

                # Show explanations in expansion
                with st.expander("Show AI Explanation & Risk Analysis"):
                    st.write(c['explanation'] or "No explanation generated.")
                    if c['simplification']:
                        st.markdown("**Plain-English Redraft Suggestion:**")
                        st.write(c['simplification'])

                    st.markdown("---")
                    st.caption(
                        "The score above is from the fast rule-based scan run at upload time. "
                        "If it looks wrong for this clause, ask an LLM to re-read it with full "
                        "legal judgment (this is on-demand only — it never runs automatically)."
                    )
                    if st.button("🤖 Re-analyze Risk with AI", key=f"llm_risk_{c['id']}"):
                        with st.spinner("Requesting an LLM risk re-assessment for this clause..."):
                            try:
                                from agents.analyzer_agent import analyze_clause_risk_with_llm
                                llm_result = analyze_clause_risk_with_llm(c['section_name'], c['text_content'])
                                crud.update_clause_risk(
                                    clause_id=c['id'],
                                    risk_level=llm_result.risk_level,
                                    risk_category=llm_result.risk_category,
                                    risk_score=llm_result.risk_score,
                                    explanation=llm_result.explanation,
                                )
                                st.success(
                                    f"Updated: {llm_result.risk_level} risk ({llm_result.risk_score}/100). Refreshing..."
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"LLM risk re-analysis failed: {e}")
                        
        with tab2:
            st.subheader("🤖 Hybrid Clause Identification Agent")
            st.markdown(
                """
                This agent combines:
                1. **Rule-based regex patterns** (scanning for structures and numbering).
                2. **Keyword matching** (broad category vocabularies).
                3. **Deterministic confidence scoring** (regex hit + keyword density + heading match — no LLM call).

                It scans the document for: *Termination, Liability, Confidentiality, Arbitration, Payment, Indemnity, Compliance, Jurisdiction, and Force Majeure*.
                """
            )
            
            # Retrieve full text of document
            full_text = "\n\n".join([c['text_content'] for c in clauses])
            # Build page mapping for page resolution
            page_mapping = []
            for c in clauses:
                page_mapping.append({
                    "page_number": c["page_num"],
                    "text_content": c["text_content"]
                })
                
            if st.button("🚀 Trigger Hybrid Identification Agent"):
                with st.spinner("Analyzing text blocks using regex, keywords, and Groq LLM..."):
                    try:
                        detected_clauses = identify_clauses(full_text, page_mapping)
                        
                        if not detected_clauses:
                            st.info("No clauses matching the 9 target types were detected by the agent.")
                        else:
                            st.success(f"Successfully identified {len(detected_clauses)} contract clauses!")
                            
                            # Build pandas DataFrame for table display
                            table_data = []
                            for dc in detected_clauses:
                                table_data.append({
                                    "Clause Type": dc.clause_type,
                                    "Confidence Score": f"{dc.confidence_score:.2f}",
                                    "Page Number": dc.page_number or "N/A",
                                    "Start Offset": dc.start_position,
                                    "End Offset": dc.end_position,
                                    "Clause Text Snippet": dc.clause_text[:120] + "..." if len(dc.clause_text) > 120 else dc.clause_text
                                })
                                
                            df = pd.DataFrame(table_data)
                            st.dataframe(df, use_container_width=True)
                            
                            # Expanders for full text review
                            st.subheader("📖 Full Text of Identified Clauses")
                            for idx, dc in enumerate(detected_clauses):
                                with st.expander(f"Item {idx+1}: {dc.clause_type} (Confidence: {dc.confidence_score:.2f}, Page: {dc.page_number or 'N/A'})"):
                                    st.markdown(f"**Offsets**: `{dc.start_position}` to `{dc.end_position}`")
                                    st.write(dc.clause_text)
                                    
                            # Log audit action
                            crud.add_audit_log("hybrid_clause_identification", f"Executed Hybrid Clause Identification Agent on document '{doc_name}'")
                    except Exception as e:
                        st.error(f"Agent execution error: {e}")
                        
        with tab3:
            st.subheader("🛑 Important Clause Detection Agent")
            st.markdown(
                """
                This agent analyzes all contract sections and flags their **legal significance**, **semantic importance**, 
                and **financial impact**. It scores clauses (0-100) and classifies them into a color-coded schema:
                
                - 🔴 **Critical** (Score 75-100): Direct liabilities, indemnification terms, jurisdiction, or crucial termination clauses.
                - 🟠 **Important** (Score 40-74): Payment instructions, nda limitations, audit scopes, standard warranties.
                - 🟢 **Informational** (Score 0-39): Boilerplate details, addresses, notice instructions, contact lines, preambles.
                """
            )
            
            if st.button("🚀 Audit Clause Importance"):
                # Convert SQLite row list to JSON serializable list for caching purposes
                serializable_clauses = []
                for c in clauses:
                    serializable_clauses.append({
                        "id": c["id"],
                        "section_name": c["section_name"],
                        "text_content": c["text_content"]
                    })
                
                clauses_json = json.dumps(serializable_clauses)
                
                with st.spinner("Executing Significance Audit Agent (scoring legal, semantic, & financial impact)..."):
                    try:
                        audited_results = run_importance_audit(clauses_json)
                        
                        st.success(f"Audit complete! Classified significance for {len(audited_results)} clauses.")
                        
                        # Display summary
                        crit_count = sum(1 for a in audited_results if a["category"] == "Critical")
                        imp_count = sum(1 for a in audited_results if a["category"] == "Important")
                        info_count = sum(1 for a in audited_results if a["category"] == "Informational")
                        
                        col1, col2, col3 = st.columns(3)
                        col1.metric("🔴 Critical Significance", crit_count)
                        col2.metric("🟠 Important Significance", imp_count)
                        col3.metric("🟢 Informational Details", info_count)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        # Render each card styled appropriately
                        for idx, item in enumerate(audited_results):
                            border_color = "#00CC96" # Green
                            badge_color = "rgba(0, 204, 150, 0.15)"
                            text_color = "#00cc96"
                            
                            if item["category"] == "Critical":
                                border_color = "#EF553B" # Red
                                badge_color = "rgba(239, 85, 59, 0.15)"
                                text_color = "#EF553B"
                            elif item["category"] == "Important":
                                border_color = "#FECB52" # Orange
                                badge_color = "rgba(254, 203, 82, 0.15)"
                                text_color = "#FECB52"

                            item_text = item['text_content'] or ""
                            preview_text, was_truncated = truncate_preview(item_text)
                            length_badge = (
                                f'<span style="background: rgba(128,128,128,0.15); color: var(--text-color); '
                                f'padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 8px;">'
                                f'📏 {len(item_text):,} chars</span>'
                                if was_truncated else ""
                            )

                            st.markdown(
                                f"""
                                <div style="
                                    border: 1px solid {border_color};
                                    border-radius: 8px;
                                    padding: 18px;
                                    margin-bottom: 20px;
                                    background: var(--secondary-background-color);
                                ">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                        <h4 style="margin: 0; color: var(--text-color);">📌 {item['section_name']}{length_badge}</h4>
                                        <span style="
                                            background-color: {badge_color};
                                            color: {text_color};
                                            font-weight: bold;
                                            padding: 4px 12px;
                                            border-radius: 6px;
                                            font-size: 0.85rem;
                                            border: 1px solid {border_color};
                                        ">{item['category'].upper()} (Score: {item['score']})</span>
                                    </div>
                                    <p style="font-size: 0.95rem; line-height: 1.5; color: var(--text-color); opacity: 0.85; background: var(--background-color); padding: 12px; border-radius: 6px;">
                                        {preview_text}
                                    </p>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                            if was_truncated:
                                with st.expander(f"📄 Show full clause text ({len(item_text):,} characters)"):
                                    st.write(item_text)

                            # Expanders showing details
                            with st.expander(f"Inspect Significance Details for {item['section_name']}"):
                                st.markdown(f"**⚖️ Legal Significance Analysis:**")
                                st.write(item["legal_analysis"])
                                st.markdown(f"**💰 Financial Impact Analysis:**")
                                st.write(item["financial_analysis"])
                                st.markdown(f"**🔍 Significance Summary Reasoning:**")
                                st.write(item["reasoning"])
                                
                        crud.add_audit_log("clause_importance_audit", f"Audited clause importance categories for document '{doc_name}'")
                    except Exception as e:
                        st.error(f"Audit failure: {e}")

        with tab4:
            st.subheader("🎯 Clause Impact Analysis Agent")
            st.markdown(
                """
                This agent analyzes specific clauses across 4 key dimensions: **Legal**, **Financial**, **Business**, and **Compliance**.
                It generates a comprehensive impact matrix visualized via a radar chart.
                """
            )
            
            clause_options = {c['id']: c['section_name'] for c in clauses}
            selected_clause_id = st.selectbox(
                "Select a clause for Impact Analysis:",
                options=list(clause_options.keys()),
                format_func=lambda x: clause_options[x],
                key="impact_clause_select"
            )
            
            clause_to_analyze = next((c for c in clauses if c['id'] == selected_clause_id), None)
            
            if clause_to_analyze:
                st.info(clause_to_analyze['text_content'])
                
                if st.button("Generate Impact Matrix"):
                    with st.spinner("Agent 6 is assessing multi-dimensional impact..."):
                        try:
                            from agents.impact_agent import analyze_clause_impact
                            from utils.visualizer import generate_impact_radar_chart
                            
                            impact_result = analyze_clause_impact(clause_to_analyze['section_name'], clause_to_analyze['text_content'])
                            
                            col1, col2 = st.columns([1, 1])
                            with col1:
                                st.markdown("### 📊 Impact Radar Chart")
                                radar_fig = generate_impact_radar_chart(
                                    impact_result.legal_impact,
                                    impact_result.financial_impact,
                                    impact_result.business_impact,
                                    impact_result.compliance_impact
                                )
                                st.plotly_chart(radar_fig, use_container_width=True)
                                
                            with col2:
                                st.markdown("### 📋 Impact Scores")
                                st.metric("⚖️ Legal Impact", f"{impact_result.legal_impact}/100")
                                st.metric("💰 Financial Impact", f"{impact_result.financial_impact}/100")
                                st.metric("💼 Business Impact", f"{impact_result.business_impact}/100")
                                st.metric("📜 Compliance Impact", f"{impact_result.compliance_impact}/100")
                                
                        except Exception as e:
                            st.error(f"Impact Analysis failed: {e}")
