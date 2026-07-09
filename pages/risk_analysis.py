import streamlit as st
from database import crud
from utils.llm_client import invoke_llm_text
from utils.theme import render_header

render_header(
    "⚠️",
    "Risk Analysis & Mitigation Advisor",
    "Score document-wide risk and generate AI-backed mitigation strategies for flagged clauses.",
    badge="Agent 4"
)

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

if not doc_id:
    st.warning("⚠️ Please select an active document in the sidebar to review risks.")
else:
    st.info(f"Auditing Risks for: **{doc_name}**")

    clauses = crud.get_clauses_for_document(doc_id)

    # Popped (read + cleared) so it only renders once, right after the
    # rerun triggered below — the LLM path updates per-clause risk in
    # Mongo, so a rerun is needed for the risky-clauses list further down
    # (already fetched into `clauses` above) to reflect the new scores.
    doc_risk_result = st.session_state.pop("document_risk_result", None)

    # ---------------------------------------------------------
    # AUTHENTICITY AGENT (deliberately separate from legal risk —
    # a bland but fabricated document can be "low risk" and still fake)
    # ---------------------------------------------------------
    active_doc = crud.get_document_by_id(doc_id)
    with st.expander("🔍 Authenticity Report", expanded=False):
        if not active_doc or active_doc.get("authenticity_score") is None:
            st.info("Not yet analyzed. Re-run analysis on this document to generate an authenticity report.")
        else:
            score = active_doc["authenticity_score"]
            level = active_doc.get("authenticity_level", "Unknown")
            level_color = "#00CC96" if level == "Authentic" else "#FECB52" if level == "Suspicious" else "#EF553B"
            st.markdown(
                f"**Authenticity Score:** {score}/100 &nbsp; "
                f"<span style='color:{level_color}; font-weight:bold;'>{level.upper()}</span>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Measures whether the document looks like a genuine, complete legal instrument "
                "(signatures, dates, structure) — independent of how risky its clause content is."
            )

    st.divider()

    # ---------------------------------------------------------
    # AGENT 4: EXPLAINABLE RISK SCORING AGENT
    # ---------------------------------------------------------
    st.markdown("### 📊 Overall Document Risk Profile")

    col_llm, col_quick = st.columns([2, 1])
    with col_llm:
        run_llm = st.button("🤖 Generate Document Risk Score with Groq (Agent 4)", type="primary")
    with col_quick:
        run_quick = st.button("⚡ Quick rule-based estimate (no LLM)")

    if run_llm or run_quick:
        spinner_msg = (
            "Agent 4 is asking Groq to re-assess every clause and recomputing the document score "
            "(this calls the LLM once per clause, so larger documents take longer)..."
            if run_llm else
            "Agent 4 is computing a fast rule-based estimate..."
        )
        with st.spinner(spinner_msg):
            try:
                from agents.risk_scoring_agent import assess_document_risk, assess_document_risk_with_llm

                if run_llm:
                    risk_result = assess_document_risk_with_llm(doc_name, clauses)
                    # The LLM path just overwrote per-clause risk fields in Mongo —
                    # stash the result and rerun so the risky-clauses list below
                    # (already fetched into `clauses` before this ran) picks up
                    # the new scores instead of showing stale badges.
                    st.session_state.document_risk_result = {"result": risk_result, "method": "llm"}
                    st.rerun()
                else:
                    risk_result = assess_document_risk(doc_name, clauses)
                    doc_risk_result = {"result": risk_result, "method": "rule"}

            except Exception as e:
                st.error(f"Failed to generate document risk score: {e}")
                doc_risk_result = None

    if doc_risk_result:
        risk_result = doc_risk_result["result"]
        from utils.visualizer import generate_risk_gauge_chart

        if doc_risk_result["method"] == "llm":
            st.caption("🤖 Scored via Groq LLM re-analysis of every clause. Per-clause risk scores were updated too.")
        else:
            st.caption("⚡ Scored via the fast rule-based phrase scan (no LLM call).")

        # Display Gauge Chart
        gauge_fig = generate_risk_gauge_chart(risk_result.risk_score)
        st.plotly_chart(gauge_fig, use_container_width=True)

        # Display Risk Details
        st.markdown(f"**Risk Level:** `{risk_result.risk_level}`")

        st.markdown("#### 🧠 Agent Reasoning")
        st.info(risk_result.reasoning)

        st.markdown("#### 💡 Key Recommendations")
        st.success(risk_result.recommendations)

        if risk_result.affected_clauses:
            st.markdown("#### 🔍 Affected Clauses")
            for ac in risk_result.affected_clauses:
                st.markdown(f"- {ac}")

    st.divider()
    
    # Filter clauses with High/Medium risk
    risky_clauses = [c for c in clauses if c['risk_level'] in ('High', 'Medium')]
    
    if not risky_clauses:
        st.success("✅ Excellent! No High or Medium risk clauses were detected in this agreement.")
    else:
        st.markdown(f"Detected **{len(risky_clauses)}** risky clauses requiring review:")
        
        # Display each risky clause
        for c in risky_clauses:
            border_color = "#EF553B" if c['risk_level'] == "High" else "#FECB52"
            
            st.markdown(
                f"""
                <div style="
                    border: 1px solid {border_color};
                    border-radius: 8px;
                    padding: 15px;
                    margin-bottom: 20px;
                    background: var(--secondary-background-color);
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <h4 style="margin: 0; color: var(--text-color);">⚠️ {c['section_name']}</h4>
                        <span style="
                            background-color: {border_color};
                            color: #121212;
                            font-weight: bold;
                            padding: 3px 10px;
                            border-radius: 4px;
                            font-size: 0.8rem;
                        ">{c['risk_level'].upper()} RISK</span>
                    </div>
                    <div style="margin-bottom: 10px; font-size: 0.85rem;">
                        <strong style="color: var(--text-color); opacity: 0.65;">Category:</strong> {c['risk_category']} |
                        <strong style="color: var(--text-color); opacity: 0.65;">Type:</strong> {c['classification']}
                    </div>
                    <p style="font-size: 0.95rem; line-height: 1.5; color: var(--text-color); opacity: 0.85; background: var(--background-color); padding: 12px; border-radius: 6px;">
                        {c['text_content']}
                    </p>
                    <div style="background: rgba(128, 128, 128, 0.15); padding: 12px; border-radius: 6px; border-left: 3px solid {border_color}; margin-top: 10px;">
                        <strong style="color: var(--text-color);">Risk Explanation:</strong><br>
                        <span style="font-size: 0.9rem; color: var(--text-color); opacity: 0.9;">{c['explanation']}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            # Interactive LLM Mitigation Advisor
            with st.expander(f"💡 Request AI Mitigation Strategy for {c['section_name']}"):
                if st.button("Generate Mitigation", key=f"mitigate_{c['id']}"):
                    with st.spinner("Analyzing legal mitigations..."):
                        try:
                            system_prompt = "You are an expert contract lawyer providing risk mitigation advice."
                            user_prompt = (
                                f"The following clause was flagged as having a {c['risk_level']} risk "
                                f"in the category '{c['risk_category']}'.\n\n"
                                f"Clause Text:\n{c['text_content']}\n\n"
                                f"Risk Explanation:\n{c['explanation']}\n\n"
                                f"Please write a professional advice report:\n"
                                f"1. Explain the specific threat/exposure to our organization.\n"
                                f"2. Suggest a revised or marked-up version of the clause text to mitigate this risk.\n"
                                f"3. Detail negotiation strategies to present to the opposing party."
                            )
                            response = invoke_llm_text(system_prompt, user_prompt, temperature=0.2)
                            st.markdown("### 💡 Recommended Mitigation Strategy")
                            st.write(response)
                        except Exception as e:
                            st.error(f"Failed to generate mitigation: {e}")

            # On-demand LLM risk re-analysis — the rule-based score above is
            # the fast default set at upload time; this re-scores just this
            # one clause with full LLM legal judgment, only when requested.
            with st.expander(f"🤖 Re-analyze Risk with AI for {c['section_name']}"):
                if st.button("Re-analyze Risk with AI", key=f"llm_risk_{c['id']}"):
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
                            st.success(f"Updated: {llm_result.risk_level} risk ({llm_result.risk_score}/100). Refreshing...")
                            st.rerun()
                        except Exception as e:
                            st.error(f"LLM risk re-analysis failed: {e}")
