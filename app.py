import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*HF_TOKEN.*")
warnings.filterwarnings("ignore", message=".*huggingface_hub.*cache.*symlinks.*")

import streamlit as st
from dotenv import load_dotenv
from database.models import init_db
from database import crud, auth

load_dotenv()

# Page configurations
st.set_page_config(
    page_title="LQ-LegalAI | Legal Intelligence Platform",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling inject — uses Streamlit's theme CSS custom
# properties (--background-color, --secondary-background-color, --text-color)
# instead of hardcoded dark hex values, so the layout stays correct whether
# the active theme (config default or a user override via Settings) is dark
# or light.
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;700;800&family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --lq-accent: #636EFA;
        --lq-accent-2: #8385f7;
        --lq-accent-dark: #4b4fd1;
        --lq-success: #00CC96;
        --lq-warning: #FECB52;
        --lq-danger: #EF553B;
        --lq-border: rgba(128, 128, 128, 0.18);
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background: var(--background-color);
        color: var(--text-color);
    }

    /* Elegant Title and Header styling */
    h1, h2, h3 {
        color: var(--text-color) !important;
        font-family: 'Manrope', 'Inter', sans-serif !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }

    /* Reduce default top padding so the shared page header sits closer to the top */
    .block-container {
        padding-top: 2.2rem !important;
    }

    /* ---------------------------------------------------------------- */
    /* Shared page header banner (utils.theme.render_header)             */
    /* ---------------------------------------------------------------- */
    .page-header {
        display: flex;
        align-items: center;
        gap: 18px;
        padding: 22px 26px;
        margin-bottom: 28px;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(99, 110, 250, 0.14) 0%, rgba(99, 110, 250, 0.03) 100%);
        border: 1px solid rgba(99, 110, 250, 0.25);
    }
    .page-header-icon {
        flex-shrink: 0;
        width: 54px;
        height: 54px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.7rem;
        border-radius: 14px;
        background: linear-gradient(135deg, var(--lq-accent-dark) 0%, var(--lq-accent-2) 100%);
        box-shadow: 0 6px 18px rgba(99, 110, 250, 0.35);
    }
    .page-header-text { min-width: 0; }
    .page-header-title-row {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
    }
    .page-header-title {
        margin: 0 !important;
        font-size: 1.65rem !important;
        line-height: 1.2 !important;
    }
    .page-header-badge {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--lq-accent);
        background: rgba(99, 110, 250, 0.14);
        border: 1px solid rgba(99, 110, 250, 0.35);
        padding: 3px 10px;
        border-radius: 20px;
    }
    .page-header-subtitle {
        margin: 6px 0 0 0 !important;
        font-size: 0.98rem;
        color: var(--text-color);
        opacity: 0.7;
        max-width: 900px;
    }

    /* Sidebar styling override */
    [data-testid="stSidebar"] {
        background-color: var(--secondary-background-color) !important;
        border-right: 1px solid rgba(128, 128, 128, 0.2);
    }
    [data-testid="stSidebar"] .block-container {
        padding-top: 1.2rem;
    }

    .lq-brand {
        text-align: center;
        padding: 6px 0 16px 0;
    }
    .lq-brand-mark {
        font-size: 1.55rem;
        font-weight: 800;
        font-family: 'Manrope', sans-serif;
        background: linear-gradient(90deg, var(--lq-accent-dark), var(--lq-accent-2));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .lq-brand-tag {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: var(--text-color);
        opacity: 0.55;
        margin-top: 2px;
    }
    .lq-sidebar-card {
        background: var(--background-color);
        border: 1px solid var(--lq-border);
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 4px;
        font-size: 0.82rem;
        opacity: 0.85;
    }
    .lq-sidebar-footer {
        text-align: center;
        font-size: 0.72rem;
        opacity: 0.45;
        margin-top: 18px;
        letter-spacing: 0.02em;
    }

    /* Premium visual KPI cards */
    .metric-card, .lq-metric-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 14px;
        padding: 22px;
        text-align: center;
        transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.10);
        height: 100%;
    }
    .metric-card:hover, .lq-metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(99, 110, 250, 0.5);
        box-shadow: 0 10px 28px rgba(99, 110, 250, 0.18);
    }
    .metric-val, .lq-metric-val {
        font-size: 2.1rem;
        font-weight: 800;
        font-family: 'Manrope', sans-serif;
        color: var(--lq-accent);
        margin-bottom: 4px;
    }
    .lq-metric-icon {
        font-size: 1.4rem;
        margin-bottom: 6px;
    }
    .metric-title, .lq-metric-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 1.3px;
        color: var(--text-color);
        opacity: 0.6;
        font-weight: 600;
    }

    /* Gradient Button (brand accent, unchanged across themes) */
    .stButton>button {
        background: linear-gradient(90deg, #5e60ce 0%, #636EFA 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(99, 110, 250, 0.3) !important;
    }
    .stButton>button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(99, 110, 250, 0.5) !important;
    }
    .stButton>button:active {
        transform: translateY(0) !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 1px solid var(--lq-border);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0 !important;
        font-weight: 600;
        padding: 10px 16px !important;
    }
    .stTabs [aria-selected="true"] {
        color: var(--lq-accent) !important;
        background: rgba(99, 110, 250, 0.10) !important;
    }

    /* Expanders */
    [data-testid="stExpander"] {
        border: 1px solid var(--lq-border) !important;
        border-radius: 10px !important;
        overflow: hidden;
    }

    /* Metrics rendered via st.metric */
    [data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border: 1px solid var(--lq-border);
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    }
    [data-testid="stMetricLabel"] {
        opacity: 0.7;
        font-weight: 600;
    }

    /* Dataframes / tables */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--lq-border);
        border-radius: 10px;
        overflow: hidden;
    }

    /* Chat messages */
    [data-testid="stChatMessage"] {
        border: 1px solid var(--lq-border);
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
    }

    /* Inputs */
    .stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] {
        border-radius: 8px !important;
    }

    /* Slim scrollbar for a cleaner feel */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-thumb { background: rgba(99, 110, 250, 0.35); border-radius: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }

    /* ---------------------------------------------------------------- */
    /* Consolidated clause card (pages/clause_analysis.py)               */
    /* ---------------------------------------------------------------- */
    .lq-badge {
        display: inline-block;
        font-weight: 700;
        font-size: 0.78rem;
        padding: 3px 11px;
        border-radius: 6px;
        white-space: nowrap;
        letter-spacing: 0.01em;
    }
    .lq-clause-table {
        width: 100%;
        border-collapse: collapse;
        margin: 14px 0 18px 0;
        font-size: 0.92rem;
    }
    .lq-clause-table tr { border-bottom: 1px solid var(--lq-border); }
    .lq-clause-table tr:last-child { border-bottom: none; }
    .lq-clause-table td {
        padding: 9px 14px;
        vertical-align: top;
        color: var(--text-color);
    }
    .lq-clause-table td.lq-field {
        width: 220px;
        font-weight: 600;
        opacity: 0.65;
        white-space: nowrap;
    }
    .lq-clause-table tr:nth-child(odd) td {
        background: rgba(128, 128, 128, 0.05);
    }

    /* Compact summary "mini cards" above the clause table (five-up grid:
       Title / Page / Category / Type / Characters) — lighter than
       .lq-metric-card since dozens of these can appear on one page. */
    .lq-mini-card {
        background: var(--secondary-background-color);
        border: 1px solid var(--lq-border);
        border-radius: 8px;
        padding: 8px 12px;
        height: 100%;
    }
    .lq-mini-card-icon { font-size: 0.85rem; opacity: 0.7; line-height: 1; }
    .lq-mini-card-value {
        font-size: 0.88rem;
        font-weight: 700;
        color: var(--text-color);
        margin-top: 3px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .lq-mini-card-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-color);
        opacity: 0.55;
        font-weight: 600;
        margin-top: 1px;
    }

    /* Compact lazy-load toggle rows ("View Original Clause Text" and
       "Simplified Version") — styled to match the native st.expander rows
       used elsewhere (e.g. the Mitigation Strategy / Re-analyze Risk
       controls on the Risk Analysis page) instead of the app's default
       gradient CTA button. Both have to stay real st.button widgets (not
       st.expander) so their body only executes once opened — Streamlit
       still executes a collapsed expander's body every rerun, which would
       defeat lazy-loading for large clause text and would re-call the
       Simplification agent on every single page interaction. Scoped via
       the button's own key-derived class (all such buttons share the
       "btn_clause_" key prefix) so no other button in the app is affected. */
    div[class*="st-key-btn_clause_"] .stButton>button {
        background: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--lq-border) !important;
        box-shadow: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 8px 14px !important;
        border-radius: 8px !important;
    }
    /* Streamlit centers the label via an inner wrapper div, not the button
       itself -- override that div directly or `justify-content` above has
       no visible effect and the label stays centered. */
    div[class*="st-key-btn_clause_"] .stButton>button > div {
        justify-content: flex-start !important;
        width: 100%;
    }
    div[class*="st-key-btn_clause_"] .stButton>button:hover {
        border-color: rgba(99, 110, 250, 0.5) !important;
        transform: none !important;
        box-shadow: 0 2px 8px rgba(99, 110, 250, 0.12) !important;
    }

    /* ---------------------------------------------------------------- */
    /* Risk Analysis dashboard (pages/risk_analysis.py)                  */
    /* ---------------------------------------------------------------- */
    /* Per-clause card — same st-key-derived-class trick as the toggle
       buttons above, applied to a keyed st.container(border=True) so the
       flagged-clause cards get a heavier "enterprise SaaS" treatment than
       Streamlit's plain default bordered box. */
    div[class*="st-key-riskcard_"] {
        border-radius: 16px !important;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.08);
        transition: box-shadow 0.25s ease, border-color 0.25s ease;
        padding: 4px 6px 10px 6px;
    }
    div[class*="st-key-riskcard_"]:hover {
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.14);
    }

    /* Fade-truncated clause preview (~5 lines, gradient fade into the
       card background instead of a hard cutoff). */
    div[class*="st-key-clausepreview_"] p {
        display: -webkit-box;
        -webkit-line-clamp: 5;
        -webkit-box-orient: vertical;
        overflow: hidden;
        position: relative;
        max-height: 8.2em;
        line-height: 1.55;
        margin-bottom: 0 !important;
    }
    div[class*="st-key-clausepreview_"] {
        position: relative;
    }
    div[class*="st-key-clausepreview_"]::after {
        content: "";
        position: absolute;
        left: 0; right: 0; bottom: 0;
        height: 2.2em;
        background: linear-gradient(to bottom, transparent, var(--secondary-background-color));
        pointer-events: none;
    }

    /* Risk factor chips — subtle tinted pills, color set inline per-chip. */
    .lq-risk-chip {
        display: inline-block;
        font-size: 0.76rem;
        font-weight: 700;
        padding: 4px 12px;
        margin: 2px 6px 2px 0;
        border-radius: 20px;
        border: 1px solid;
        letter-spacing: 0.01em;
    }

    /* "Why was this clause flagged?" bullet list */
    .lq-explanation-list {
        margin: 6px 0 14px 0;
        padding-left: 1.3em;
    }
    .lq-explanation-list li {
        margin-bottom: 7px;
        font-size: 0.92rem;
        line-height: 1.5;
        color: var(--text-color);
        opacity: 0.9;
    }

    /* Before/After risk comparison (Re-analyze result) */
    .lq-compare-box {
        text-align: center;
        background: var(--secondary-background-color);
        border: 1px solid var(--lq-border);
        border-radius: 12px;
        padding: 14px 10px;
    }
    .lq-compare-label {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        opacity: 0.55;
        margin-bottom: 8px;
    }
    .lq-compare-score {
        font-size: 1.2rem;
        font-weight: 800;
        font-family: 'Manrope', sans-serif;
        margin-top: 8px;
        color: var(--text-color);
    }
    .lq-compare-arrow {
        text-align: center;
        font-size: 1.6rem;
        opacity: 0.4;
        padding-top: 28px;
    }
</style>
""", unsafe_allow_html=True)

# 1. Initialize MongoDB Database
init_db()

# Ensure directories exist
os.makedirs(os.getenv("UPLOADS_DIR", "uploads"), exist_ok=True)
os.makedirs(os.getenv("REPORTS_DIR", "reports"), exist_ok=True)


def render_auth_gate():
    """Blocks the rest of the app until the user is logged in. Handles
    login, signup, requesting a password-reset email, and consuming a
    reset link (?reset_token=... from that email) to set a new password."""
    st.markdown(
        """
        <div class="lq-brand" style="padding-top: 24px;">
            <div class="lq-brand-mark">⚖️ LQ-LegalAI</div>
            <div class="lq-brand-tag">Legal Intelligence Platform</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.3, 1])
    with center:
        reset_token = st.query_params.get("reset_token")
        if reset_token:
            st.subheader("🔑 Set a New Password")
            with st.form("reset_password_form"):
                new_password = st.text_input("New password", type="password")
                confirm_password = st.text_input("Confirm new password", type="password")
                submitted = st.form_submit_button("Reset Password", use_container_width=True)
            if submitted:
                if new_password != confirm_password:
                    st.error("Passwords do not match.")
                elif auth.reset_password(reset_token, new_password):
                    st.success("Password reset. You can now log in below.")
                    st.query_params.clear()
                else:
                    st.error("This reset link is invalid or has expired. Request a new one from the Forgot Password tab.")
                    if st.button("Back to login"):
                        st.query_params.clear()
                        st.rerun()
            st.stop()

        tab_login, tab_signup, tab_forgot = st.tabs(["Log In", "Sign Up", "Forgot Password"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log In", use_container_width=True)
            if submitted:
                user = auth.authenticate(email, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Invalid email or password.")

        with tab_signup:
            with st.form("signup_form"):
                name = st.text_input("Full name")
                email = st.text_input("Email", key="signup_email")
                password = st.text_input("Password", type="password", key="signup_password", help="At least 8 characters.")
                confirm_password = st.text_input("Confirm password", type="password", key="signup_confirm")
                submitted = st.form_submit_button("Create Account", use_container_width=True)
            if submitted:
                if password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    try:
                        user = auth.create_user(name, email, password)
                        st.session_state.user = user
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        with tab_forgot:
            st.caption("Enter your account email and we'll send you a reset link.")
            with st.form("forgot_password_form"):
                email = st.text_input("Email", key="forgot_email")
                submitted = st.form_submit_button("Send Reset Link", use_container_width=True)
            if submitted:
                token = auth.request_password_reset(email)
                if token:
                    auth.send_reset_email(email.strip().lower(), token)
                # Same message whether or not the email is registered, so this
                # can't be used to enumerate valid accounts.
                st.success("If an account exists for that email, a reset link has been sent.")

    st.stop()


if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    render_auth_gate()

# Global Session State
if "active_doc_id" not in st.session_state:
    st.session_state.active_doc_id = None
if "active_doc_name" not in st.session_state:
    st.session_state.active_doc_name = None

# Sidebar document selector
st.sidebar.markdown(
    """
    <div class="lq-brand">
        <div class="lq-brand-mark">⚖️ LQ-LegalAI</div>
        <div class="lq-brand-tag">Legal Intelligence Platform</div>
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.markdown(
    f'<div class="lq-sidebar-card">👤 <strong>{st.session_state.user["name"]}</strong><br>'
    f'<span style="opacity:0.6;">{st.session_state.user["email"]}</span></div>',
    unsafe_allow_html=True,
)
if st.sidebar.button("Log Out", use_container_width=True):
    st.session_state.user = None
    st.session_state.active_doc_id = None
    st.session_state.active_doc_name = None
    st.rerun()
st.sidebar.markdown("---")

documents = crud.get_all_documents(user_id=st.session_state.user["id"])
if documents:
    doc_options = {doc['id']: doc['name'] for doc in documents}

    st.sidebar.caption("ACTIVE WORKSPACE DOCUMENT")
    # Selected doc configuration
    selected_id = st.sidebar.selectbox(
        "Active Workspace Document:",
        options=list(doc_options.keys()),
        format_func=lambda x: doc_options[x],
        label_visibility="collapsed"
    )

    # Store in session state
    st.session_state.active_doc_id = selected_id
    st.session_state.active_doc_name = doc_options[selected_id]
    st.sidebar.markdown(
        f'<div class="lq-sidebar-card">📄 <strong>{doc_options[selected_id]}</strong></div>',
        unsafe_allow_html=True
    )
else:
    st.sidebar.warning("No documents uploaded yet.")
    st.session_state.active_doc_id = None
    st.session_state.active_doc_name = None

st.sidebar.markdown("---")
st.sidebar.info("💡 Select a document above, then navigate using the pages menu to audit and interact.")
st.sidebar.markdown(
    '<div class="lq-sidebar-footer">LQ-LegalAI &middot; Multi-Agent Legal Intelligence</div>',
    unsafe_allow_html=True
)


# Define Pages
pg_dashboard = st.Page("pages/dashboard.py", title="1. Dashboard", icon="📊", default=True)
pg_upload = st.Page("pages/upload.py", title="2. Upload Document", icon="📤")
pg_clause = st.Page("pages/clause_analysis.py", title="3. Clause Analysis", icon="📑")
pg_risk = st.Page("pages/risk_analysis.py", title="4. Risk Analysis", icon="⚠️")
pg_contradiction = st.Page("pages/contradiction.py", title="5. Contradiction Detection", icon="⚡")
pg_simplification = st.Page("pages/simplification.py", title="6. Simplification", icon="✨")
pg_translation = st.Page("pages/translation.py", title="7. Translation", icon="🌍")
pg_qa = st.Page("pages/legal_qa.py", title="8. Legal Q&A", icon="💬")
pg_comparison = st.Page("pages/comparison.py", title="9. Comparison Center", icon="🔄")
pg_kg = st.Page("pages/knowledge_graph.py", title="10. Knowledge Graph", icon="🕸️")
pg_dg = st.Page("pages/dependency_graph.py", title="11. Dependency Graph", icon="🔗")
pg_re = st.Page("pages/risk_evolution.py", title="12. Risk Evolution", icon="📈")
pg_vh = st.Page("pages/version_history.py", title="13. Version History", icon="🕒")
pg_audit = st.Page("pages/audit_report.py", title="14. Audit Report", icon="📋")

pg = st.navigation({
    "Core Platform": [pg_dashboard, pg_upload],
    "Analytics & Risk": [pg_clause, pg_risk, pg_contradiction, pg_comparison],
    "AI Tools": [pg_simplification, pg_translation, pg_qa],
    "Visualizations": [pg_kg, pg_dg, pg_re],
    "Governance": [pg_vh, pg_audit]
})

pg.run()
