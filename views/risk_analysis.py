import html
import json
import re

import streamlit as st

from database import crud
from utils.llm_client import invoke_llm_text
from utils.theme import render_header, render_metric_card, render_mini_card, render_badge
from agents.importance_agent import assess_clause_importance
from agents.rule_engine import detect_clause_type

render_header(
    "⚠️",
    "Risk Analysis & Mitigation Advisor",
    "Score document-wide risk and generate AI-backed mitigation strategies for flagged clauses.",
    badge="Agent 4"
)

RISK_COLORS = {"High": "#EF553B", "Medium": "#FECB52", "Low": "#636EFA", "None": "#00CC96", "Critical": "#EF553B"}

# Presentation-only keyword vocabulary for the "Risk Factors" chips — derived
# from the clause's existing category/explanation/text via simple keyword
# matching. No new agent calls, no persistence; purely a scannable summary
# of data the backend already produced.
RISK_FACTOR_VOCAB = [
    ("Vague Language", ["vague", "unclear", "undefined", "not clearly defined", "loosely defined"]),
    ("Missing Timeline", ["no timeline", "no deadline", "notice period", "no specified period",
                           "timeframe is not specified", "no cure period"]),
    ("Legal Ambiguity", ["ambiguous", "ambiguity", "open to interpretation", "subject to interpretation"]),
    ("Penalty Missing", ["no penalty", "lacks penalty", "without penalty", "no liquidated damages",
                          "penalty is not specified"]),
    ("Uncapped Liability", ["unlimited liability", "uncapped", "unlimited exposure", "no cap on"]),
    ("Unilateral Rights", ["sole discretion", "unilateral", "one-sided", "at its discretion", "without consent"]),
    ("Indemnity Gap", ["indemnification", "indemnify", "indemnity"]),
    ("Compliance Risk", ["compliance", "regulatory", "statutory", "non-compliant", "gdpr"]),
    ("Termination Risk", ["termination", "terminate"]),
    ("Assignment Risk", ["assignment", "assign its rights", "assign this agreement"]),
    ("Governing Law Gap", ["governing law", "jurisdiction is not specified", "no governing law"]),
]
CHIP_PALETTE = ["#EF553B", "#FECB52", "#636EFA", "#00CC96", "#AB63FA", "#FFA15A"]

HIGHLIGHT_WORDS = [
    "vague", "unclear", "ambiguous", "ambiguity", "undefined", "missing",
    "unlimited", "uncapped", "penalt", "indemnif", "liability",
    "sole discretion", "unilateral", "without notice", "non-compliant",
    "breach", "dispute", "terminate", "termination",
]
_HIGHLIGHT_RE = re.compile("(" + "|".join(re.escape(w) for w in HIGHLIGHT_WORDS) + ")", re.IGNORECASE)


def _fmt(value, default="—"):
    if value in (None, ""):
        return default
    return value


def _clause_risk_factors(category, explanation, text, limit=5):
    haystack = f"{explanation or ''} {text or ''}".lower()
    chips = []
    if category:
        chips.append(category)
    for label, keywords in RISK_FACTOR_VOCAB:
        if len(chips) >= limit:
            break
        if label not in chips and any(kw in haystack for kw in keywords):
            chips.append(label)
    return chips[:limit]


def _bulletize(explanation):
    """Splits a free-text explanation into short bullet points for
    scannability. Falls back gracefully if it can't be split cleanly."""
    if not explanation:
        return []
    text = explanation.strip()
    if text.startswith("-") or "\n-" in text:
        parts = [p.strip("- ").strip() for p in text.split("\n")]
    else:
        parts = re.split(r"(?<=[.;])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 3][:6]


def _highlight(text):
    """Escapes the text then bolds known risk-trigger keywords — safe to
    render with unsafe_allow_html since escaping happens first."""
    escaped = html.escape(text)
    return _HIGHLIGHT_RE.sub(
        lambda m: f'<strong style="color:var(--lq-danger);">{m.group(0)}</strong>', escaped
    )


def render_toggle(flag_key: str, button_key: str, label: str) -> bool:
    """Compact lazy-load toggle row (mirrors pages/clause_analysis.py) —
    a plain button + session_state flag instead of st.expander, so the
    body below only executes once opened."""
    if flag_key not in st.session_state:
        st.session_state[flag_key] = False
    arrow = "▼" if st.session_state[flag_key] else "▶"
    if st.button(f"{arrow}  {label}", key=button_key, width="stretch"):
        st.session_state[flag_key] = not st.session_state[flag_key]
        st.rerun()
    return st.session_state[flag_key]


@st.cache_data(show_spinner=False)
def _compute_display_intel(clauses_json: str) -> dict:
    """Rule-based importance category + identification confidence, purely
    for the header metadata chips — same agents already used on the Clause
    Analysis page (Agent 2/3), no LLM calls, so cheap to run eagerly."""
    clauses_list = json.loads(clauses_json)
    intel = {}
    for c in clauses_list:
        section_name = c.get("section_name") or "Clause"
        text = c.get("text_content") or ""
        try:
            importance = assess_clause_importance(section_name, text)
            importance_category = importance.importance_category
        except Exception:
            importance_category = None
        try:
            _clause_type, confidence = detect_clause_type(f"{section_name}\n{text}")
        except Exception:
            confidence = None
        intel[c["id"]] = {"importance_category": importance_category, "confidence": confidence}
    return intel


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

    active_doc = crud.get_document_by_id(doc_id)

    # ---------------------------------------------------------
    # OVERVIEW ROW — authenticity + document risk trigger side by side,
    # so both fit above the fold before the flagged-clause list.
    # ---------------------------------------------------------
    top_cols = st.columns(2)
    with top_cols[0]:
        with st.container(border=True):
            st.markdown("##### 🔍 Authenticity Report")
            if not active_doc or active_doc.get("authenticity_score") is None:
                st.caption("Not yet analyzed. Re-run analysis on this document to generate an authenticity report.")
            else:
                score = active_doc["authenticity_score"]
                level = active_doc.get("authenticity_level", "Unknown")
                level_color = "#00CC96" if level == "Authentic" else "#FECB52" if level == "Suspicious" else "#EF553B"
                st.markdown(
                    f"**{score}/100** &nbsp; "
                    f"<span style='color:{level_color}; font-weight:700;'>{level.upper()}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Whether the document looks like a genuine, complete legal instrument — "
                    "independent of how risky its clause content is."
                )

    with top_cols[1]:
        with st.container(border=True):
            st.markdown("##### 📊 Document Risk Score")
            btn_cols = st.columns(2)
            run_llm = btn_cols[0].button("🤖 Full AI Re-score", type="primary", width="stretch")
            run_quick = btn_cols[1].button("⚡ Quick Estimate", width="stretch")
            st.caption("Full AI Re-score calls Groq once per clause (Agent 4). Quick Estimate is instant, rule-based.")

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

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            method_caption = (
                "🤖 Scored via Groq LLM re-analysis of every clause — per-clause risk scores were updated too."
                if doc_risk_result["method"] == "llm"
                else "⚡ Scored via the fast rule-based phrase scan (no LLM call)."
            )

            gauge_col, detail_col = st.columns([1, 1.4])
            with gauge_col:
                gauge_fig = generate_risk_gauge_chart(risk_result.risk_score)
                st.plotly_chart(gauge_fig, use_container_width=True)
            with detail_col:
                level_badge = render_badge(
                    risk_result.risk_level.upper(), RISK_COLORS.get(risk_result.risk_level, "#888888")
                )
                st.markdown(f"**Risk Level:** {level_badge}", unsafe_allow_html=True)
                st.caption(method_caption)

                with st.expander("🧠 Agent Reasoning", expanded=False):
                    st.write(risk_result.reasoning)
                with st.expander("💡 Key Recommendations", expanded=False):
                    st.write(risk_result.recommendations)

                if risk_result.affected_clauses:
                    st.markdown("**Flagged Sections**")
                    chips_html = "".join(
                        f'<span class="lq-risk-chip" style="background:{CHIP_PALETTE[i % len(CHIP_PALETTE)]}22; '
                        f'color:{CHIP_PALETTE[i % len(CHIP_PALETTE)]}; border-color:{CHIP_PALETTE[i % len(CHIP_PALETTE)]}55;">'
                        f'{html.escape(ac)}</span>'
                        for i, ac in enumerate(risk_result.affected_clauses)
                    )
                    st.markdown(chips_html, unsafe_allow_html=True)

    st.divider()

    # ---------------------------------------------------------
    # FLAGGED CLAUSES
    # ---------------------------------------------------------
    # A clause that was just re-analyzed down to Low risk still needs to
    # stay visible so its Before/After comparison can render — otherwise
    # the risk-level filter below would make it disappear the instant it
    # improves, hiding the very result the user just asked for.
    reanalyzed_ids = {c["id"] for c in clauses if f"reanalysis_{c['id']}" in st.session_state}
    risky_clauses = [c for c in clauses if c["risk_level"] in ("High", "Medium") or c["id"] in reanalyzed_ids]

    if not risky_clauses:
        st.success("✅ Excellent! No High or Medium risk clauses were detected in this agreement.")
    else:
        high_count = sum(1 for c in risky_clauses if c["risk_level"] == "High")
        med_count = sum(1 for c in risky_clauses if c["risk_level"] == "Medium")

        kpi_cols = st.columns(3)
        with kpi_cols[0]:
            st.markdown(render_metric_card("Flagged Clauses", len(risky_clauses), "🚩", accent="var(--lq-danger)"), unsafe_allow_html=True)
        with kpi_cols[1]:
            st.markdown(render_metric_card("High Risk", high_count, "🔴", accent="var(--lq-danger)"), unsafe_allow_html=True)
        with kpi_cols[2]:
            st.markdown(render_metric_card("Medium Risk", med_count, "🟡", accent="var(--lq-warning)"), unsafe_allow_html=True)

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

        serializable = [
            {"id": c["id"], "section_name": c["section_name"], "text_content": c["text_content"]}
            for c in risky_clauses
        ]
        intel_by_clause = _compute_display_intel(json.dumps(serializable))

        PREVIEW_CHARS = 320
        for c in risky_clauses:
            cid = c["id"]
            risk_level = c["risk_level"]
            border_color = RISK_COLORS.get(risk_level, "#888888")
            full_text = c["text_content"] or ""
            is_long = len(full_text) > PREVIEW_CHARS

            intel = intel_by_clause.get(cid, {})
            importance_category = intel.get("importance_category") or "—"
            confidence = intel.get("confidence")
            confidence_display = f"{confidence:.2f} Confidence" if confidence is not None else "—"

            with st.container(border=True, key=f"riskcard_{cid}"):
                # Risk-colored accent strip along the top of the card.
                st.markdown(
                    f"<div style='height:4px; background:{border_color}; border-radius:6px; margin-bottom:12px;'></div>",
                    unsafe_allow_html=True,
                )

                header_col, badge_col = st.columns([5, 1.6])
                with header_col:
                    st.markdown(f"#### ⚠️ {c['section_name']}")
                with badge_col:
                    badge_html = render_badge(f"{risk_level.upper()} RISK", border_color)
                    st.markdown(f"<div style='text-align:right; padding-top:14px;'>{badge_html}</div>", unsafe_allow_html=True)

                mini_cols = st.columns(5)
                page_val = c.get("page_num")
                with mini_cols[0]:
                    st.markdown(render_mini_card("Category", _fmt(c.get("risk_category")), "🏷"), unsafe_allow_html=True)
                with mini_cols[1]:
                    st.markdown(render_mini_card("Page", f"Page {page_val}" if page_val else "N/A", "📄"), unsafe_allow_html=True)
                with mini_cols[2]:
                    st.markdown(render_mini_card("Importance", importance_category, "📈"), unsafe_allow_html=True)
                with mini_cols[3]:
                    st.markdown(render_mini_card("Confidence", confidence_display, "🎯"), unsafe_allow_html=True)
                with mini_cols[4]:
                    st.markdown(render_mini_card("Characters", f"{len(full_text):,}", "🔤"), unsafe_allow_html=True)

                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

                # ── Clause preview (fade-truncated ~5 lines) ────────────
                with st.container(key=f"clausepreview_{cid}"):
                    st.write(full_text or "No text extracted for this clause.")

                if is_long:
                    if render_toggle(f"clause_{cid}_full_expanded", f"btn_riskfull_{cid}", "View Full Clause"):
                        with st.container(border=True):
                            st.write(full_text)

                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

                # ── Why was this clause flagged? ─────────────────────────
                st.markdown("##### 🧠 Why was this clause flagged?")
                bullets = _bulletize(c.get("explanation"))
                if bullets:
                    bullets_html = "".join(f"<li>{_highlight(b)}</li>" for b in bullets)
                    st.markdown(f'<ul class="lq-explanation-list">{bullets_html}</ul>', unsafe_allow_html=True)
                else:
                    st.caption("No explanation recorded for this clause yet.")

                factors = _clause_risk_factors(c.get("risk_category"), c.get("explanation"), full_text)
                if factors:
                    st.markdown("**Risk Factors**")
                    chips_html = "".join(
                        f'<span class="lq-risk-chip" style="background:{CHIP_PALETTE[i % len(CHIP_PALETTE)]}22; '
                        f'color:{CHIP_PALETTE[i % len(CHIP_PALETTE)]}; border-color:{CHIP_PALETTE[i % len(CHIP_PALETTE)]}55;">'
                        f'{html.escape(str(f))}</span>'
                        for i, f in enumerate(factors)
                    )
                    st.markdown(chips_html, unsafe_allow_html=True)

                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

                # ── AI Mitigation Advisor ────────────────────────────────
                mitigation_key = f"mitigation_result_{cid}"
                improved_key = f"improved_clause_{cid}"
                if render_toggle(f"clause_{cid}_mitigation_expanded", f"btn_mitigate_toggle_{cid}", "AI Mitigation Strategy"):
                    with st.container(border=True):
                        if mitigation_key not in st.session_state:
                            st.caption(
                                "Generate a professional mitigation report: threat exposure, a revised clause "
                                "redraft, and negotiation strategy."
                            )
                            if st.button("💡 Generate Mitigation", key=f"mitigate_{cid}", type="primary"):
                                with st.spinner("💡 Generating AI Mitigation Strategy..."):
                                    try:
                                        system_prompt = "You are an expert contract lawyer providing risk mitigation advice."
                                        user_prompt = (
                                            f"The following clause was flagged as having a {risk_level} risk "
                                            f"in the category '{c['risk_category']}'.\n\n"
                                            f"Clause Text:\n{full_text}\n\n"
                                            f"Risk Explanation:\n{c.get('explanation')}\n\n"
                                            "Write a professional mitigation report using this exact Markdown structure:\n"
                                            "### Reason\n<one short paragraph on the specific threat/exposure to our organization>\n\n"
                                            "### Recommended Improvements\n<3-5 bullet points, each starting with '✔ ', "
                                            "covering the concrete revisions needed>\n\n"
                                            "### Improved Clause Wording\n<a revised, markup-ready version of the clause text>\n\n"
                                            "### Negotiation Strategy\n<1-2 short paragraphs of negotiation tactics for the opposing party>"
                                        )
                                        response = invoke_llm_text(system_prompt, user_prompt, temperature=0.2)
                                        st.session_state[mitigation_key] = response
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to generate mitigation: {e}")
                        else:
                            st.markdown("###### ✅ Recommended Mitigation Strategy")
                            st.markdown(st.session_state[mitigation_key])

                            action_cols = st.columns(2)
                            if action_cols[0].button("🔄 Regenerate", key=f"mitigate_regen_{cid}", width="stretch"):
                                del st.session_state[mitigation_key]
                                st.session_state.pop(improved_key, None)
                                st.rerun()
                            if action_cols[1].button("📝 Generate Improved Clause", key=f"improve_{cid}", width="stretch"):
                                with st.spinner("Drafting improved clause wording..."):
                                    try:
                                        improve_prompt = (
                                            f"Based on this mitigation report:\n\n{st.session_state[mitigation_key]}\n\n"
                                            "Rewrite the following clause so it fully addresses the risks and "
                                            "recommendations above. Return ONLY the revised clause text, no commentary.\n\n"
                                            f"Original Clause:\n{full_text}"
                                        )
                                        improved = invoke_llm_text(
                                            "You are an expert contract lawyer redrafting a legal clause.",
                                            improve_prompt, temperature=0.2,
                                        )
                                        st.session_state[improved_key] = improved
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to generate improved clause: {e}")

                            if st.session_state.get(improved_key):
                                st.markdown("###### 📝 Improved Clause")
                                st.info(st.session_state[improved_key])

                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

                # ── Re-analyze Risk with AI ──────────────────────────────
                reanalysis_key = f"reanalysis_{cid}"
                if render_toggle(f"clause_{cid}_reanalyze_expanded", f"btn_reanalyze_toggle_{cid}", "Re-analyze Risk"):
                    with st.container(border=True):
                        st.markdown("###### 🔄 Re-analyze Risk")
                        st.caption("Validate the clause after applying AI recommendations — re-scores it with a fresh LLM legal assessment.")

                        if st.button("Re-analyze with AI", key=f"llm_risk_{cid}", type="primary"):
                            with st.spinner("🔄 Requesting an LLM risk re-assessment for this clause..."):
                                try:
                                    from agents.analyzer_agent import analyze_clause_risk_with_llm
                                    before_level = risk_level
                                    before_score = c.get("risk_score") if c.get("risk_score") is not None else 0
                                    llm_result = analyze_clause_risk_with_llm(c["section_name"], full_text)
                                    crud.update_clause_risk(
                                        clause_id=cid,
                                        risk_level=llm_result.risk_level,
                                        risk_category=llm_result.risk_category,
                                        risk_score=llm_result.risk_score,
                                        explanation=llm_result.explanation,
                                    )
                                    st.session_state[reanalysis_key] = {
                                        "before_level": before_level,
                                        "before_score": before_score,
                                        "after_level": llm_result.risk_level,
                                        "after_score": llm_result.risk_score,
                                    }
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"LLM risk re-analysis failed: {e}")

                        if reanalysis_key in st.session_state:
                            r = st.session_state[reanalysis_key]
                            reduction = r["before_score"] - r["after_score"]
                            pct = round((reduction / r["before_score"]) * 100) if r["before_score"] else 0

                            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                            cmp_cols = st.columns([1, 0.3, 1])
                            with cmp_cols[0]:
                                st.markdown(
                                    f'<div class="lq-compare-box"><div class="lq-compare-label">BEFORE</div>'
                                    f'{render_badge(r["before_level"].upper(), RISK_COLORS.get(r["before_level"], "#888888"))}'
                                    f'<div class="lq-compare-score">{r["before_score"]}/100</div></div>',
                                    unsafe_allow_html=True,
                                )
                            with cmp_cols[1]:
                                st.markdown('<div class="lq-compare-arrow">→</div>', unsafe_allow_html=True)
                            with cmp_cols[2]:
                                st.markdown(
                                    f'<div class="lq-compare-box"><div class="lq-compare-label">AFTER</div>'
                                    f'{render_badge(r["after_level"].upper(), RISK_COLORS.get(r["after_level"], "#888888"))}'
                                    f'<div class="lq-compare-score">{r["after_score"]}/100</div></div>',
                                    unsafe_allow_html=True,
                                )

                            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
                            if reduction > 0:
                                st.success(f"✅ Risk reduced by {pct}% ({reduction} points)")
                            elif reduction < 0:
                                st.warning(f"⚠️ Risk increased by {abs(pct)}% ({abs(reduction)} points)")
                            else:
                                st.caption("No change in risk score.")

            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
