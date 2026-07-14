import json
import statistics

import streamlit as st

from database import crud
from agents.importance_agent import assess_clause_importance
from agents.impact_agent import analyze_clause_impact
from agents.rule_engine import detect_clause_type
from utils.theme import render_header, render_metric_card, render_mini_card, render_badge
from utils.visualizer import generate_clause_impact_radar_chart

RISK_COLORS = {"High": "#EF553B", "Medium": "#FECB52", "Low": "#636EFA", "None": "#00CC96"}
IMPORTANCE_COLORS = {"Critical": "#EF553B", "Important": "#FECB52", "Informational": "#00CC96"}
COMPLIANCE_COLORS = {"Needs Review": "#EF553B", "Monitor": "#FECB52", "Compliant": "#00CC96"}
IMPACT_LEVEL_COLORS = {"High": "#EF553B", "Medium": "#FECB52", "Low": "#00CC96"}


def _fmt(value, default="—"):
    if value is None or value == "":
        return default
    return value


def _compliance_status(compliance_impact):
    if compliance_impact is None:
        return "Unknown"
    if compliance_impact >= 70:
        return "Needs Review"
    if compliance_impact >= 40:
        return "Monitor"
    return "Compliant"


def _impact_level_score(legal, financial, business, compliance):
    scores = [v for v in (legal, financial, business, compliance) if v is not None]
    if not scores:
        return None
    return round(statistics.mean(scores))


def _impact_level_label(score):
    if score is None:
        return None
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _confidence_tier(confidence):
    if confidence is None:
        return "Unscored"
    if confidence >= 0.7:
        return "High-Confidence Match"
    if confidence >= 0.4:
        return "Moderate-Confidence Match"
    return "Low-Confidence Match"


# Cached consolidated compute for Agent 2 (identification confidence), Agent 3
# (importance), and Agent 6 (impact) — all rule-based/no-LLM, so it's cheap to
# run eagerly for every clause instead of gating each behind its own button.
@st.cache_data(show_spinner="Running clause intelligence (identification, importance, impact)...")
def compute_clause_intelligence(clauses_json: str) -> dict:
    clauses_list = json.loads(clauses_json)
    intel = {}
    for c in clauses_list:
        section_name = c.get("section_name") or "Clause"
        text = c.get("text_content") or ""

        try:
            importance = assess_clause_importance(section_name, text)
        except Exception:
            importance = None

        try:
            impact = analyze_clause_impact(section_name, text)
        except Exception:
            impact = None

        try:
            _clause_type, confidence = detect_clause_type(f"{section_name}\n{text}")
        except Exception:
            confidence = None

        intel[c["id"]] = {
            "importance_score": importance.importance_score if importance else None,
            "importance_category": importance.importance_category if importance else "Informational",
            "legal_impact": impact.legal_impact if impact else None,
            "financial_impact": impact.financial_impact if impact else None,
            "business_impact": impact.business_impact if impact else None,
            "compliance_impact": impact.compliance_impact if impact else None,
            "confidence_score": confidence,
        }
    return intel


def render_toggle(flag_key: str, button_key: str, label: str) -> bool:
    """Compact lazy-load toggle row, styled via CSS (see app.py, scoped to
    the button's key) to match the compact bordered look of native expander
    rows elsewhere in the app. Deliberately a plain st.button + session_state
    flag, not st.expander — Streamlit still executes and ships an expander's
    body to the client even while collapsed, which would (a) defeat
    lazy-loading for very large clause text, and (b) call Agent 7 on every
    single rerun for every clause instead of only when the user opens that
    clause's Simplified Version.

    Uses two distinct keys because Streamlit forbids writing to
    st.session_state under a key that's also bound to a widget."""
    if flag_key not in st.session_state:
        st.session_state[flag_key] = False
    arrow = "▼" if st.session_state[flag_key] else "▶"
    if st.button(f"{arrow}  {label}", key=button_key, width="stretch"):
        st.session_state[flag_key] = not st.session_state[flag_key]
        st.rerun()
    return st.session_state[flag_key]


def render():
    doc_id = st.session_state.active_doc_id
    doc_name = st.session_state.active_doc_name

    render_header(
        "🔍",
        "Clause Analysis",
        "Detailed clause-level analysis of the active document",
        badge="Agents 2 · 3 · 6 · 7",
        doc_name=doc_name,
    )

    if not doc_id:
        st.warning("⚠️ Please select an active document in the sidebar or upload one to begin.")
        return

    clauses = crud.get_clauses_for_document(doc_id)

    if not clauses:
        st.info("No clauses parsed for this document.")
        return

    # One-time upgrade for documents ingested before clause_title generation
    # existed: their section_name is still the bare category (e.g. every
    # Payment clause literally titled "Payment"). Cheap and rule-based, so it
    # runs silently the first time this document is viewed after the fix.
    document = crud.get_document_by_id(doc_id)
    if document and not document.get("clause_titles_backfilled"):
        from agents.clause_identifier_agent import backfill_clause_titles_for_document
        if backfill_clause_titles_for_document(doc_id):
            clauses = crud.get_clauses_for_document(doc_id)
        crud.update_document_analysis(doc_id, clause_titles_backfilled=True)

    serializable_clauses = [
        {
            "id": c["id"],
            "section_name": c["section_name"],
            "text_content": c["text_content"],
            "classification": c.get("classification"),
        }
        for c in clauses
    ]
    clauses_json = json.dumps(serializable_clauses)

    intel_by_clause = compute_clause_intelligence(clauses_json)

    # ── KPI summary row ─────────────────────────────────────────────
    high_risk_count = sum(1 for c in clauses if c.get("risk_level") == "High")
    importance_scores = [
        intel_by_clause[c["id"]]["importance_score"]
        for c in clauses if intel_by_clause.get(c["id"], {}).get("importance_score") is not None
    ]
    avg_importance = round(statistics.mean(importance_scores)) if importance_scores else 0

    kpi_cols = st.columns(3)
    with kpi_cols[0]:
        st.markdown(render_metric_card("Total Clauses", len(clauses), "📑"), unsafe_allow_html=True)
    with kpi_cols[1]:
        st.markdown(render_metric_card("High Risk Clauses", high_risk_count, "🔴", accent="var(--lq-danger)"), unsafe_allow_html=True)
    with kpi_cols[2]:
        st.markdown(render_metric_card("Avg Importance", f"{avg_importance}/100", "🎯"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Filters ──────────────────────────────────────────────────────
    filter_cols = st.columns(4)
    classifications = ["All"] + sorted({c["classification"] for c in clauses if c.get("classification")})
    risk_levels = ["All", "High", "Medium", "Low", "None"]
    importance_levels = ["All", "Critical", "Important", "Informational"]

    selected_class = filter_cols[0].selectbox("Clause Type:", classifications)
    selected_risk = filter_cols[1].selectbox("Risk Level:", risk_levels)
    selected_importance = filter_cols[2].selectbox("Importance Level:", importance_levels)
    search_text = filter_cols[3].text_input("Search title or text:", placeholder="e.g. termination, liability…")

    filtered_clauses = clauses
    if selected_class != "All":
        filtered_clauses = [c for c in filtered_clauses if c.get("classification") == selected_class]
    if selected_risk != "All":
        filtered_clauses = [c for c in filtered_clauses if (c.get("risk_level") or "None") == selected_risk]
    if selected_importance != "All":
        filtered_clauses = [
            c for c in filtered_clauses
            if intel_by_clause.get(c["id"], {}).get("importance_category") == selected_importance
        ]
    if search_text:
        needle = search_text.lower()
        filtered_clauses = [
            c for c in filtered_clauses
            if needle in (c.get("section_name") or "").lower() or needle in (c.get("text_content") or "").lower()
        ]

    st.markdown(f"Showing **{len(filtered_clauses)}** of **{len(clauses)}** clauses:")
    st.markdown("<br>", unsafe_allow_html=True)

    # ── One compact card per clause (plain bordered container, not an
    # expander — real st.expander can't nest inside another, and Impact
    # Analysis below needs to be a genuine expander to match the app's
    # native compact-row style) ───────────────────────────────────────
    for c in filtered_clauses:
        cid = c["id"]
        intel = intel_by_clause.get(cid, {})
        risk_level = c.get("risk_level") or "None"
        importance_category = intel.get("importance_category", "Informational")
        compliance_status = _compliance_status(intel.get("compliance_impact"))
        text_content = c.get("text_content") or ""
        confidence_score = intel.get("confidence_score")

        with st.container(border=True):
            # ── Summary cards (Title / Page / Category / Type / Characters) ──
            card_cols = st.columns([1.6, 0.8, 1, 1, 1])
            with card_cols[0]:
                st.markdown(render_mini_card("Clause Title", c["section_name"], "📌"), unsafe_allow_html=True)
            with card_cols[1]:
                st.markdown(render_mini_card("Page", _fmt(c.get("page_num"), "N/A"), "📄"), unsafe_allow_html=True)
            with card_cols[2]:
                st.markdown(render_mini_card("Category", _fmt(c.get("risk_category")), "🏷"), unsafe_allow_html=True)
            with card_cols[3]:
                st.markdown(render_mini_card("Type", _fmt(c.get("classification"), "Unclassified"), "📑"), unsafe_allow_html=True)
            with card_cols[4]:
                st.markdown(render_mini_card("Characters", f"{len(text_content):,}", "🔤"), unsafe_allow_html=True)

            # ── Clause Details Table ─────────────────────────────────
            risk_badge = render_badge(f"{risk_level.upper()} RISK", RISK_COLORS.get(risk_level, "#888888"))
            importance_badge = render_badge(importance_category.upper(), IMPORTANCE_COLORS.get(importance_category, "#888888"))
            compliance_badge = render_badge(compliance_status.upper(), COMPLIANCE_COLORS.get(compliance_status, "#888888"))

            rows = [
                ("Clause Classification", _confidence_tier(confidence_score)),
                ("Importance Level", importance_badge),
                ("Risk Level", risk_badge),
                ("Compliance Status", compliance_badge),
            ]
            table_rows_html = "".join(
                f'<tr><td class="lq-field">{field}</td><td>{value}</td></tr>' for field, value in rows
            )
            st.markdown(f'<table class="lq-clause-table">{table_rows_html}</table>', unsafe_allow_html=True)

            # ── View Original Clause Text (lazy — body never executes
            # while collapsed, see render_toggle docstring) ──────────
            if render_toggle(f"clause_{cid}_text_expanded", f"btn_clause_{cid}_text", "View Original Clause Text"):
                with st.container(border=True):
                    st.write(text_content or "No text extracted for this clause.")

            # ── Simplify Clause (Agent 7) — runs the moment this section is
            # opened, no separate "Simplify" button needed. Cached per
            # clause per session so re-opening/collapsing it doesn't
            # re-call the LLM. Shows the full plain-English breakdown:
            # explanation, easy summary, rights, obligations, hidden
            # risks, and an AI recommendation. ────────────────────────
            if render_toggle(f"clause_{cid}_simplify_expanded", f"btn_clause_{cid}_simplify", "Simplify Clause"):
                with st.container(border=True):
                    result_key = f"simplify_result_{cid}"
                    error_key = f"simplify_error_{cid}"

                    if result_key not in st.session_state:
                        with st.spinner("Agent 7 is translating legalese to plain English..."):
                            try:
                                from agents.simplification_agent import simplify_clause
                                st.session_state[result_key] = simplify_clause(text_content)
                                st.session_state[error_key] = None
                            except Exception as e:
                                st.session_state[result_key] = None
                                st.session_state[error_key] = str(e)

                    generated = st.session_state.get(result_key)
                    if generated:
                        st.markdown("**💬 Plain English Explanation**")
                        st.write(generated.simplified_clause)
                        st.markdown("**📝 Easy Summary**")
                        st.write(generated.easy_summary)
                        rights_col, obligations_col = st.columns(2)
                        with rights_col:
                            st.markdown("**✅ Rights**")
                            st.write(generated.rights)
                        with obligations_col:
                            st.markdown("**📌 Obligations**")
                            st.write(generated.obligations)
                        st.markdown("**⚠️ Hidden Risks**")
                        st.warning(generated.hidden_risks)
                        st.markdown("**💡 AI Recommendation**")
                        st.success(generated.ai_recommendation)
                    elif c.get("simplification"):
                        st.caption("AI generation failed — showing the previously saved plain-English redraft instead.")
                        st.write(c["simplification"])
                    else:
                        st.error(f"Simplification failed: {st.session_state.get(error_key, 'unknown error')}")

                    if st.button("🔄 Regenerate with AI (Agent 7)", key=f"simplify_regen_{cid}"):
                        with st.spinner("Agent 7 is translating legalese to plain English..."):
                            try:
                                from agents.simplification_agent import simplify_clause
                                st.session_state[result_key] = simplify_clause(text_content)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Simplification failed: {e}")

            # ── Impact Analysis (radar chart + side details) ────────
            with st.expander("📊 Impact Analysis", expanded=False):
                impact_score = _impact_level_score(
                    intel.get("legal_impact"), intel.get("financial_impact"),
                    intel.get("business_impact"), intel.get("compliance_impact"),
                )
                if impact_score is None or intel.get("legal_impact") is None:
                    st.caption("Impact scoring unavailable for this clause.")
                else:
                    impact_label = _impact_level_label(impact_score)
                    chart_col, detail_col = st.columns([1.1, 1])
                    with chart_col:
                        radar_fig = generate_clause_impact_radar_chart(
                            impact_score, intel["business_impact"], intel["legal_impact"],
                        )
                        st.plotly_chart(radar_fig, width="stretch", key=f"radar_{cid}")
                    with detail_col:
                        st.markdown(
                            f"**Impact Level:** {render_badge(impact_label.upper(), IMPACT_LEVEL_COLORS.get(impact_label, '#888888'))}",
                            unsafe_allow_html=True,
                        )
                        st.caption("Overall severity of this clause's impact across legal, financial, business, and compliance dimensions.")
                        st.markdown(f"**Business Impact:** {intel['business_impact']}/100")
                        st.caption("How significantly this clause could affect business operations, SLAs, or deliverables.")
                        st.markdown(f"**Legal Impact:** {intel['legal_impact']}/100")
                        st.caption("How significantly this clause could affect legal exposure or enforceability.")

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
