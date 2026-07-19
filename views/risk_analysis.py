import html
import json
import re

import streamlit as st

from database import crud
from utils.theme import render_header, render_metric_card, render_mini_card, render_badge
from agents.importance_agent import assess_clause_importance
from agents.rule_engine import detect_clause_type

RISK_COLORS = {"High": "#EF553B", "Medium": "#FECB52", "Low": "#636EFA", "None": "#00CC96", "Critical": "#EF553B"}

HIGHLIGHT_WORDS = [
    "vague", "unclear", "ambiguous", "ambiguity", "undefined", "missing",
    "unlimited", "uncapped", "penalt", "indemnif", "liability",
    "sole discretion", "unilateral", "without notice", "non-compliant",
    "breach", "dispute", "terminate", "termination",
    "one-sided", "no upper limit", "no limit", "not clearly stated", "lack of clarity",
]
_HIGHLIGHT_RE = re.compile("(" + "|".join(re.escape(w) for w in HIGHLIGHT_WORDS) + ")", re.IGNORECASE)

# Rule-based jargon → plain-English swaps applied to clause explanations
# before display, so "Why is this risky" reads in simple English without an
# extra LLM call. Longest keys first so multi-word phrases match before
# their single-word substrings (e.g. "sole discretion" before "discretion").
SIMPLIFY_MAP = {
    "indemnification": "compensation for losses",
    "indemnify": "compensate for losses",
    "indemnity": "compensation for losses",
    "unilaterally": "one-sided",
    "unilateral": "one-sided",
    "sole discretion": "its own judgment, without asking you",
    "ambiguous": "unclear",
    "ambiguity": "lack of clarity",
    "undefined": "not clearly stated",
    "liquidated damages": "a pre-agreed penalty amount",
    "governing law": "which state's or country's laws apply",
    "jurisdiction": "which court has authority",
    "force majeure": "unforeseeable events beyond anyone's control",
    "cure period": "time allowed to fix the problem",
    "statutory": "required by law",
    "non-compliant": "not following the rules",
    "unlimited liability": "no limit on what you could owe",
    "uncapped": "with no upper limit",
    "notwithstanding": "despite",
    "herein": "in this document",
    "thereof": "of it",
}
_SIMPLIFY_RE = re.compile(
    "(" + "|".join(re.escape(k) for k in sorted(SIMPLIFY_MAP, key=len, reverse=True)) + ")",
    re.IGNORECASE,
)

# The rule-based analyzer (agents/analyzer_agent.py) writes explanations as
# "Classified as 'X' (Y risk category). Risk score 72/100: 'without notice'
# +15; base tier 'Medium' = 55." — a scoring readout, not a risk narrative.
# This pulls out the risk category and the flagged phrases and drops the
# arithmetic (and any mitigating, negative-point phrases) entirely.
_SCORE_EXPLANATION_RE = re.compile(
    r"^Classified as '(?P<clause_type>[^']*)'\s*\((?P<risk_category>[^)]*) risk category\)\.\s*"
    r"Risk score \d+/100:\s*(?P<contributions>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_CONTRIBUTION_RE = re.compile(r"^'([^']+)'\s*([+-]\d+)$")

# One-line grounding for *why* a risk category matters, shown before the
# specific flagged phrases so a single phrase match still reads as a full
# explanation rather than an isolated word.
CATEGORY_CONTEXT = {
    "Financial": "This clause carries financial risk — it can directly affect what you pay, owe, or recover if something goes wrong.",
    "Legal": "This clause carries legal risk — it can affect your legal standing, obligations, or ability to enforce your rights.",
    "Compliance": "This clause carries compliance risk — failing to meet its requirements could expose you to regulatory or contractual consequences.",
    "Operational": "This clause carries operational risk — it can disrupt how the agreement is carried out in practice.",
    "Ambiguity": "This clause carries ambiguity risk — vague or hedged language makes its obligations harder to predict or enforce.",
}

# Plain-English reason each risk-increasing phrase actually matters — not
# just that it was "found", but what it does to your exposure. Covers every
# escalating (positive-point) phrase in rules/risk_rules.json and
# rules/escalation_rules.json.
PHRASE_EXPLANATIONS = {
    "without notice": "it lets the other party act (e.g. terminate or change terms) without warning you first, leaving you no time to prepare or respond",
    "sole discretion": "the decision is left entirely to the other party's own judgment, with no requirement to consult you or explain it",
    "immediate termination": "the agreement can end right away, with no transition period to wind down obligations or find an alternative",
    "immediately": "an obligation or consequence takes effect right away, with no buffer time to comply or react",
    "no cure period": "there's no window to fix a mistake or missed obligation before consequences like termination kick in",
    "at any time": "the other party can exercise this right whenever it wants, with no defined trigger or advance planning for you",
    "for convenience": "the agreement can be ended for no stated reason at all, not just for a breach — no cause is required",
    "irrevocable": "once given, it cannot be taken back or changed later, even if circumstances change",
    "unlimited liability": "there is no cap on how much you could be required to pay if something goes wrong",
    "unlimited": "there is no cap on the exposure this clause creates",
    "uncapped": "no maximum limit is set on the financial exposure this clause creates",
    "no limitation": "the clause explicitly rules out any cap on liability or obligation",
    "without limitation": "this signals the surrounding obligation has no cap or boundary",
    "consequential damages": "you could be liable for indirect losses (like lost profits) on top of direct damages, which can be large and hard to predict",
    "punitive damages": "you could be liable for damages meant to punish, not just compensate — these can far exceed actual losses",
    "joint and several": "each party can be held responsible for the entire obligation, not just its own share, if another party can't pay",
    "non-refundable": "money already paid will not be returned, even if circumstances change or the agreement ends early",
    "penalty": "a monetary penalty applies, adding cost on top of the underlying obligation",
    "liquidated damages": "a pre-agreed penalty amount applies automatically if there's a breach, regardless of your actual loss",
    "late fee": "falling behind on a deadline (usually payment) triggers an extra charge",
    "interest": "outstanding amounts accrue interest, which increases what you owe the longer it stays unpaid",
    "immediate payment": "payment is due right away, leaving no time to arrange funds",
    "acceleration": "missing one payment or obligation can trigger the entire remaining balance to become due at once",
    "no offset": "you can't reduce what you owe by amounts the other party separately owes you",
    "forfeit": "you could lose money, property, or rights already paid for or earned, without compensation",
    "hold harmless": "you may be required to cover the other party's losses, even for issues you didn't directly cause",
    "unlimited indemnification": "there is no cap on how much you could owe to cover the other party's losses or claims",
    "defend": "you may be required to pay for and manage the legal defense of claims brought against the other party",
    "third-party claims": "you could be responsible for claims brought by people or companies outside this agreement",
    "sole negligence": "you may owe compensation even for harm caused solely by the other party's own carelessness",
}


def _fmt(value, default="—"):
    if value in (None, ""):
        return default
    return value


def _simplify(text):
    """Rule-based plain-English pass over explanatory text — swaps common
    legal/technical jargon for everyday phrasing. No LLM call."""
    if not text:
        return text
    return _SIMPLIFY_RE.sub(lambda m: SIMPLIFY_MAP[m.group(0).lower()], text)


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


def _dimension_breakdown_bullets(dimension_breakdown):
    """Preferred path: builds bullets directly from the Hybrid Explainable
    Risk Engine's per-dimension breakdown (risk_engine/explain.py) — no
    regex parsing needed, since the structured data already says exactly
    why each dimension contributed. One bullet per dimension that actually
    contributed positively, in the same largest-first order the engine
    already sorted them in."""
    bullets = []
    for dim in dimension_breakdown:
        if not isinstance(dim, dict) or dim.get("contribution", 0) <= 0:
            continue
        dimension = dim.get("dimension", "")
        context = CATEGORY_CONTEXT.get(dimension, f"This clause carries {dimension.lower()} risk." if dimension else "")
        if not context:
            continue

        evidence_bits = []
        feature_evidence = dim.get("feature_evidence") or []
        if feature_evidence:
            evidence_bits.append(feature_evidence[0])
        semantic_evidence = dim.get("semantic_evidence") or {}
        if semantic_evidence.get("prototype"):
            evidence_bits.append(f'reads similarly to "{semantic_evidence["prototype"]}"')

        detail = f" ({'; '.join(evidence_bits)})" if evidence_bits else ""
        bullets.append(f"{context}{detail}")
    return bullets[:6]


def _risk_explanation_bullets(explanation, dimension_breakdown=None):
    """Plain-English bullets describing *why* a clause is risky. Prefers the
    Hybrid Explainable Risk Engine's structured dimension_breakdown when
    present (every clause scored since that engine went live); falls back
    to parsing the older keyword-scorer's explanation string format for
    documents processed before it existed, or to simple sentence-splitting
    if neither shape matches."""
    if dimension_breakdown:
        bullets = _dimension_breakdown_bullets(dimension_breakdown)
        if bullets:
            return bullets

    if not explanation:
        return []
    text = explanation.strip()
    match = _SCORE_EXPLANATION_RE.match(text)
    if not match:
        return [_simplify(b) for b in _bulletize(text)]

    risk_category = match.group("risk_category").strip()
    bullets = [CATEGORY_CONTEXT.get(
        risk_category, "This clause was flagged for elevated risk based on its specific wording."
    )]

    for part in match.group("contributions").split(";"):
        part = part.strip().rstrip(".")
        if not part or part.lower().startswith("base tier"):
            continue
        contribution_match = _CONTRIBUTION_RE.match(part)
        if not contribution_match:
            continue
        phrase, points = contribution_match.group(1), int(contribution_match.group(2))
        if points <= 0:
            continue  # mitigating language — not a reason this clause is risky
        reason = PHRASE_EXPLANATIONS.get(phrase.lower())
        if reason:
            bullets.append(f'Uses the phrase "{phrase}" — {reason}.')
        else:
            bullets.append(f'Uses the phrase "{phrase}", which raises risk.')
    return bullets[:6]


def _highlight(text):
    """Escapes the text then bolds known risk-trigger keywords — safe to
    render with unsafe_allow_html since escaping happens first."""
    escaped = html.escape(text)
    return _HIGHLIGHT_RE.sub(
        lambda m: f'<strong style="color:var(--lq-danger);">{m.group(0)}</strong>', escaped
    )


def render_toggle(flag_key: str, button_key: str, label: str) -> bool:
    """Plain text-link toggle (not a boxed CTA button) — swaps its own label
    between "<label>" and "Hide <label>" instead of using an arrow icon, so
    it reads as an inline link. Body below only executes once opened."""
    if flag_key not in st.session_state:
        st.session_state[flag_key] = False
    shown_label = f"Hide {label}" if st.session_state[flag_key] else label
    if st.button(shown_label, key=button_key):
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


def render():
    doc_id = st.session_state.active_doc_id
    doc_name = st.session_state.active_doc_name

    render_header(
        "⚠️",
        "Risk Analysis & Mitigation Advisor",
        "A plain-English breakdown of document-wide risk and authenticity, plus every flagged clause explained.",
        badge="Agent 4",
        doc_name=doc_name,
    )

    if not doc_id:
        st.warning("⚠️ Please select an active document in the sidebar to review risks.")
        return

    clauses = crud.get_clauses_for_document(doc_id)
    active_doc = crud.get_document_by_id(doc_id) or {}

    # One-time upgrade for documents ingested before clause_title generation
    # existed: their section_name is still the bare category (e.g. every
    # Payment clause literally titled "Payment"). Cheap and rule-based, so it
    # runs silently the first time this document is viewed after the fix —
    # shared with views/clause_analysis.py via the same document-level flag.
    if clauses and not active_doc.get("clause_titles_backfilled"):
        from agents.clause_identifier_agent import backfill_clause_titles_for_document
        if backfill_clause_titles_for_document(doc_id):
            clauses = crud.get_clauses_for_document(doc_id)
        crud.update_document_analysis(doc_id, clause_titles_backfilled=True)

    # ---------------------------------------------------------
    # OVERVIEW — a Quick Estimate trigger. The gauge + recommendations only appear once
    # the button is clicked (persisted per-document in session_state so
    # picking a filter below doesn't make it vanish again).
    # ---------------------------------------------------------
    with st.container(key="risk_overview_card"):
        st.markdown('<div class="lq-overview-title">📊 Risk Overview</div>', unsafe_allow_html=True)

        a_score = active_doc.get("authenticity_score")
        a_level = active_doc.get("authenticity_level", "Unknown")
        a_color = "#00CC96" if a_level == "Authentic" else "#FECB52" if a_level == "Suspicious" else "#EF553B"

        stat_cols = st.columns([0.01, 1])
        if False:  # Authenticity is still calculated and stored; it is intentionally hidden from the UI.
            st.markdown(
                render_metric_card("Authenticity Score", f"{a_score}/100" if a_score is not None else "—", "🔍", accent=a_color),
                unsafe_allow_html=True,
            )
            if a_score is not None:
                st.markdown(f"<div style='text-align:center; margin-top:6px;'>{render_badge(a_level.upper(), a_color)}</div>", unsafe_allow_html=True)
        with stat_cols[1]:
            with st.container(border=True, key="quick_estimate_card"):
                st.markdown(
                    "<div style='text-align:center; opacity:0.65; font-size:0.72rem; text-transform:uppercase; "
                    "letter-spacing:0.06em; font-weight:700; margin-bottom:10px;'>📊 Document Risk</div>",
                    unsafe_allow_html=True,
                )
                run_quick = st.button("⚡ Quick Estimate", key="quick_estimate_btn", width="stretch", type="primary")
                st.caption("Rule-based score across every clause — instant, no LLM call.")

        quick_estimate_key = f"quick_estimate_{doc_id}"
        if run_quick:
            with st.spinner("Computing a fresh rule-based estimate…"):
                try:
                    from agents.risk_scoring_agent import assess_document_risk
                    st.session_state[quick_estimate_key] = assess_document_risk(doc_name, clauses)
                except Exception as e:
                    st.error(f"Failed to generate document risk score: {e}")

        risk_result = st.session_state.get(quick_estimate_key)
        if risk_result:
            st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
            gauge_col, detail_col = st.columns([1, 1.4])
            with gauge_col:
                from utils.visualizer import generate_risk_gauge_chart
                st.plotly_chart(generate_risk_gauge_chart(risk_result.risk_score), use_container_width=True)
            with detail_col:
                level_badge = render_badge(risk_result.risk_level.upper(), RISK_COLORS.get(risk_result.risk_level, "#888888"))
                st.markdown(f"**Risk Level:** {level_badge}", unsafe_allow_html=True)
                st.markdown("**Recommendations**")
                st.write(risk_result.recommendations)

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # ---------------------------------------------------------
    # FLAGGED CLAUSES
    # ---------------------------------------------------------
    risky_clauses_all = [c for c in clauses if c["risk_level"] in ("High", "Medium")]

    if not risky_clauses_all:
        st.success("✅ Excellent! No High or Medium risk clauses were detected in this agreement.")
        return

    categories = sorted({c.get("risk_category") or "Uncategorized" for c in risky_clauses_all})
    filter_cols = st.columns(2)
    with filter_cols[0]:
        selected_category = st.selectbox("🏷 Category", ["All Categories"] + categories, key="risk_category_filter")
    with filter_cols[1]:
        selected_level = st.selectbox("⚠ Risk Level", ["All Levels", "High", "Medium"], key="risk_level_filter")

    risky_clauses = risky_clauses_all
    if selected_category != "All Categories":
        risky_clauses = [c for c in risky_clauses if (c.get("risk_category") or "Uncategorized") == selected_category]
    if selected_level != "All Levels":
        risky_clauses = [c for c in risky_clauses if c["risk_level"] == selected_level]

    if not risky_clauses:
        st.info("No flagged clauses match the selected filters.")
        return

    st.divider()

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

    PREVIEW_CHARS = 260
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

            mini_cols = st.columns(3)
            with mini_cols[0]:
                st.markdown(render_mini_card("Category", _fmt(c.get("risk_category")), "🏷"), unsafe_allow_html=True)
            with mini_cols[1]:
                st.markdown(render_mini_card("Importance", importance_category, "📈"), unsafe_allow_html=True)
            with mini_cols[2]:
                st.markdown(render_mini_card("Confidence", confidence_display, "🎯"), unsafe_allow_html=True)

            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

            # ── Clause preview (fade-truncated ~4 lines) ────────────
            with st.container(key=f"clausepreview_{cid}"):
                st.write(full_text or "No text extracted for this clause.")

            if is_long:
                # Plain text link, not an AI call — just reveals the clause
                # text already fetched from the document.
                if render_toggle(f"clause_{cid}_full_expanded", f"btn_riskfull_{cid}", "View Full Clause"):
                    with st.container(border=True):
                        st.write(full_text)

            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

            # ── Why this clause is risky, in plain English ──────────
            st.markdown("##### 🧠 Why This Clause Is Risky")
            bullets = _risk_explanation_bullets(c.get("explanation"), c.get("dimension_breakdown"))
            if bullets:
                bullets_html = "".join(f"<li>{_highlight(b)}</li>" for b in bullets)
                st.markdown(f'<ul class="lq-explanation-list">{bullets_html}</ul>', unsafe_allow_html=True)
            else:
                st.caption("No explanation recorded for this clause yet.")

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
