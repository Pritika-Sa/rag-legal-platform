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
from views import dashboard, clause_analysis, risk_analysis, contradiction, comparison

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
        padding-top: 1.2rem !important;
    }

    /* ---------------------------------------------------------------- */
    /* Shared page header banner (utils.theme.render_header)             */
    /* Deliberately not a filled/bordered card — just a slim row with a  */
    /* bottom divider, so it reads as a page title, not another box.    */
    /* ---------------------------------------------------------------- */
    .page-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        padding: 2px 2px 14px 2px;
        margin-bottom: 20px;
        border-bottom: 1px solid var(--lq-border);
        flex-wrap: wrap;
    }
    .page-header-left {
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 0;
    }
    .page-header-icon-inline {
        flex-shrink: 0;
        font-size: 1.5rem;
        line-height: 1;
    }
    .page-header-text { min-width: 0; }
    .page-header-title-row {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }
    .page-header-title {
        margin: 0 !important;
        font-size: 1.3rem !important;
        line-height: 1.25 !important;
    }
    .page-header-badge {
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--lq-accent);
        background: rgba(99, 110, 250, 0.14);
        border: 1px solid rgba(99, 110, 250, 0.35);
        padding: 2px 9px;
        border-radius: 20px;
    }
    .page-header-subtitle {
        margin: 4px 0 0 0 !important;
        font-size: 0.86rem;
        color: var(--text-color);
        opacity: 0.65;
        max-width: 820px;
    }
    .page-header-docname {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--text-color);
        background: rgba(99, 110, 250, 0.10);
        border: 1px solid rgba(99, 110, 250, 0.25);
        padding: 6px 14px;
        border-radius: 999px;
        white-space: nowrap;
        margin-top: 2px;
    }
    .page-header-docname-value { color: var(--lq-accent); font-weight: 700; }
    .page-header-docname-empty {
        color: var(--text-color);
        opacity: 0.5;
        font-weight: 500;
        background: transparent;
        border-color: var(--lq-border);
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

    /* ---------------------------------------------------------------- */
    /* Sidebar profile card                                              */
    /* ---------------------------------------------------------------- */
    .lq-profile-card {
        display: flex;
        align-items: center;
        gap: 12px;
        background: linear-gradient(135deg, rgba(99, 110, 250, 0.14) 0%, rgba(99, 110, 250, 0.03) 100%);
        border: 1px solid rgba(99, 110, 250, 0.25);
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 10px;
    }
    .lq-profile-avatar {
        flex-shrink: 0;
        width: 42px;
        height: 42px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
        font-weight: 800;
        color: white;
        background: linear-gradient(135deg, var(--lq-accent-dark) 0%, var(--lq-accent-2) 100%);
    }
    .lq-profile-name { font-weight: 700; font-size: 0.95rem; color: var(--text-color); }
    .lq-profile-email { font-size: 0.76rem; opacity: 0.6; color: var(--text-color); }
    .lq-profile-workspace {
        font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.06em;
        opacity: 0.5; margin-top: 2px; color: var(--lq-accent);
    }

    /* ---------------------------------------------------------------- */
    /* Document Management — upload + document cards                    */
    /* ---------------------------------------------------------------- */
    .lq-doc-card {
        border: 1px solid var(--lq-border);
        border-radius: 12px;
        padding: 10px 12px;
        margin-bottom: 8px;
        background: var(--background-color);
        transition: border-color 0.2s ease;
    }
    .lq-doc-card.active {
        border-color: var(--lq-accent);
        box-shadow: 0 0 0 1px var(--lq-accent);
    }
    .lq-doc-title { font-weight: 700; font-size: 0.86rem; color: var(--text-color); overflow-wrap: anywhere; }
    .lq-doc-meta { font-size: 0.7rem; opacity: 0.6; margin-top: 2px; }
    .lq-status-pill {
        display: inline-block; font-size: 0.66rem; font-weight: 700;
        padding: 2px 8px; border-radius: 20px; text-transform: uppercase;
        letter-spacing: 0.04em; margin-left: 6px;
    }

    /* ---------------------------------------------------------------- */
    /* Sticky top pill navigation                                       */
    /* ---------------------------------------------------------------- */
    div[class*="st-key-lq_topnav"] {
        position: sticky;
        top: 0;
        z-index: 998;
        padding: 10px 6px;
        margin: 1.5rem -6px 20px -6px;
        background: color-mix(in srgb, var(--background-color) 85%, transparent);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--lq-border);
        overflow-x: auto;
    }
    div[class*="st-key-lq_topnav"] .stButton>button {
        border-radius: 999px !important;
        padding: 8px 16px !important;
        font-size: 0.85rem !important;
        white-space: nowrap !important;
        overflow: hidden;
        text-overflow: ellipsis;
        min-height: 2.6rem;
    }
    div[class*="st-key-lq_topnav"] .stButton>button > div,
    div[class*="st-key-lq_topnav"] .stButton>button p {
        white-space: nowrap !important;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    div[class*="st-key-lq_topnav"] .stButton>button[kind="secondary"] {
        background: transparent !important;
        color: var(--text-color) !important;
        border: 1px solid var(--lq-border) !important;
        box-shadow: none !important;
    }
    div[class*="st-key-lq_topnav"] .stButton>button[kind="secondary"]:hover {
        border-color: rgba(99, 110, 250, 0.5) !important;
        transform: translateY(-2px) !important;
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
    /* Consolidated clause card (views/clause_analysis.py)                */
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
       "Simplify Clause") — styled to match the native st.expander rows
       used elsewhere (e.g. the Simplify Risk / Re-analyze Risk controls
       on the Risk Analysis page) instead of the app's default gradient
       CTA button. Both have to stay real st.button widgets (not
       st.expander) so their body only executes once opened — Streamlit
       still executes a collapsed expander's body every rerun, which would
       defeat lazy-loading for large clause text. Scoped via the button's
       own key-derived class (all such buttons share the "btn_clause_" key
       prefix) so no other button in the app is affected. */
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
    /* Risk Analysis dashboard (views/risk_analysis.py)                   */
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

    /* Fade-truncated clause preview (~4 lines, gradient fade into the
       card background instead of a hard cutoff). */
    div[class*="st-key-clausepreview_"] p {
        display: -webkit-box;
        -webkit-line-clamp: 4;
        -webkit-box-orient: vertical;
        overflow: hidden;
        position: relative;
        max-height: 6.6em;
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

    /* "Why This Clause Is Risky" bullet list */
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

    .lq-overview-title {
        font-family: 'Manrope', sans-serif;
        font-weight: 800;
        font-size: 1.05rem;
        letter-spacing: -0.01em;
        color: var(--text-color);
        margin-bottom: 14px;
    }
    /* "Quick Estimate" trigger card — same footprint/height as the
       Authenticity metric card next to it, so the top row stays balanced. */
    div[class*="st-key-quick_estimate_card"] {
        border-radius: 14px !important;
        padding: 22px 18px !important;
        display: flex;
        flex-direction: column;
        justify-content: center;
        height: 100%;
    }

    /* "View Full Clause" toggle — a plain text link instead of the app's
       default gradient CTA button, so it doesn't compete visually with
       real actions. Fetches text already loaded from the document; no
       AI call involved. */
    div[class*="st-key-btn_riskfull_"] .stButton>button {
        background: transparent !important;
        color: var(--lq-accent) !important;
        border: none !important;
        box-shadow: none !important;
        padding: 4px 0 !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        width: auto !important;
        min-height: unset !important;
    }
    div[class*="st-key-btn_riskfull_"] .stButton>button:hover {
        text-decoration: underline !important;
        transform: none !important;
        box-shadow: none !important;
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
        font-size: 1.7rem;
        font-weight: 800;
        font-family: 'Manrope', sans-serif;
        color: var(--text-color);
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
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

    /* ---------------------------------------------------------------- */
    /* Clickable dashboard metric cards — a real st.button restyled to   */
    /* look like .lq-metric-card, not an overlay on separate HTML (an   */
    /* earlier attempt at overlaying an invisible button on top of a    */
    /* markdown card fought Streamlit's own Emotion-generated button    */
    /* sizing and lost even with !important). The button's label is     */
    /* "icon\n\n**value**\n\nlabel" (Streamlit renders \n\n as line      */
    /* breaks and **..** as a real <strong>), so `strong` below is      */
    /* targetable to give the value the same visual weight as           */
    /* .lq-metric-val.                                                  */
    /* ---------------------------------------------------------------- */
    div[class*="st-key-dash_nav_"] .stButton > button {
        width: 100% !important;
        height: auto !important;
        min-height: unset !important;
        white-space: pre-line !important;
        text-align: center !important;
        line-height: 1.4 !important;
        background: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        border: 1px solid rgba(128, 128, 128, 0.18) !important;
        border-radius: 14px !important;
        padding: 20px 14px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.10) !important;
        transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease !important;
    }
    div[class*="st-key-dash_nav_"] .stButton > button:hover {
        transform: translateY(-4px) !important;
        border-color: rgba(99, 110, 250, 0.5) !important;
        box-shadow: 0 10px 28px rgba(99, 110, 250, 0.18) !important;
    }
    div[class*="st-key-dash_nav_"] .stButton > button p {
        font-size: 0.95rem !important;
        margin: 2px 0 !important;
        color: var(--text-color) !important;
    }
    div[class*="st-key-dash_nav_"] .stButton > button strong {
        display: block;
        font-size: 1.9rem;
        font-family: 'Manrope', sans-serif;
        font-weight: 800;
        margin: 2px 0;
    }

    /* ---------------------------------------------------------------- */
    /* Floating Legal AI Chat                                            */
    /* ---------------------------------------------------------------- */
    div[class*="st-key-lq_chat_fab"] {
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 1000;
        width: auto;
    }
    div[class*="st-key-lq_chat_fab"] .stButton>button {
        border-radius: 50% !important;
        width: 58px !important;
        height: 58px !important;
        padding: 0 !important;
        font-size: 1.5rem !important;
        box-shadow: 0 8px 24px rgba(99, 110, 250, 0.45) !important;
    }
    div[class*="st-key-lq_chat_panel"] {
        position: fixed !important;
        bottom: 92px;
        right: 24px;
        z-index: 1000;
        width: 400px;
        max-height: 70vh;
        overflow-y: auto;
        background: var(--secondary-background-color) !important;
        opacity: 1 !important;
        isolation: isolate;
        border: 1px solid var(--lq-border) !important;
        border-radius: 18px !important;
        padding: 16px !important;
        box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
    }
    /* Streamlit's own generated styles on the inner vertical block can carry
       a transparent background; without this the panel behind them shows
       through the fixed, positioned panel above instead of being opaque. */
    div[class*="st-key-lq_chat_panel"] [data-testid="stVerticalBlock"] {
        background: var(--secondary-background-color) !important;
    }
    @media (max-width: 500px) {
        div[class*="st-key-lq_chat_panel"] { width: 92vw; right: 4vw; }
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

# ── Global session state ─────────────────────────────────────────────────
if "current_page" not in st.session_state:
    st.session_state.current_page = "dashboard"
if "active_doc_id" not in st.session_state:
    st.session_state.active_doc_id = None
if "active_doc_name" not in st.session_state:
    st.session_state.active_doc_name = None
if "chat_open" not in st.session_state:
    st.session_state.chat_open = False
if "messages" not in st.session_state:
    st.session_state.messages = []


FILE_ICONS = {
    "pdf": "📕", "docx": "📘", "txt": "📄",
    "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️",
}
STATUS_COLORS = {"processing": "var(--lq-warning)", "processed": "var(--lq-success)", "failed": "var(--lq-danger)"}


def _file_type(doc_name: str) -> str:
    return os.path.splitext(doc_name)[1].lstrip(".").lower() or "file"


# =============================================================================
# SIDEBAR — Profile + Document Management only (no page navigation)
# =============================================================================
with st.sidebar:
    st.markdown(
        """
        <div class="lq-brand">
            <div class="lq-brand-mark">⚖️ LQ-LegalAI</div>
            <div class="lq-brand-tag">Legal Intelligence Platform</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Profile card (top of sidebar) ────────────────────────────────
    user = st.session_state.user
    initials = "".join(part[0].upper() for part in user["name"].split()[:2]) or "U"
    st.markdown(
        f"""
        <div class="lq-profile-card">
            <div class="lq-profile-avatar">{initials}</div>
            <div>
                <div class="lq-profile-name">{user["name"]}</div>
                <div class="lq-profile-email">{user["email"]}</div>
                <div class="lq-profile-workspace">Personal Workspace</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Log Out", use_container_width=True):
        st.session_state.user = None
        st.session_state.active_doc_id = None
        st.session_state.active_doc_name = None
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")

    # ── Document Management ──────────────────────────────────────────
    st.markdown("#### 📁 Document Management")

    if "last_analysis_summary" in st.session_state:
        summary = st.session_state.pop("last_analysis_summary")
        st.success(f"🎉 '{summary['doc_name']}' processed — {summary['clause_count']} clauses found.")
        st.caption(
            f"Risk {summary['document_risk_score']}/100 · Authenticity {summary['authenticity_score']}/100"
        )
        if summary.get("parsing_quality_warning"):
            st.warning(f"⚠️ {summary['parsing_quality_warning']}")

    uploaded_file = st.file_uploader(
        "Upload a document",
        type=["pdf", "docx", "txt", "png", "jpg", "jpeg"],
        help="PDF, Word, or text contracts. Images are OCR'd automatically before analysis.",
    )

    if uploaded_file is not None:
        uploads_dir = os.path.join(os.getenv("UPLOADS_DIR", "uploads"), str(user["id"]))
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if st.button("🚀 Process Document", use_container_width=True, type="primary"):
            with st.spinner("Processing Status: running multi-agent analysis…"):
                try:
                    from agents.orchestrator import run_orchestration
                    result = run_orchestration(file_path, user_id=user["id"])

                    if result.get("error") and "already analyzed" in result["error"].lower():
                        st.warning("This document has already been analyzed.")
                        st.session_state.active_doc_id = result["doc_id"]
                        st.session_state.active_doc_name = uploaded_file.name
                        st.rerun()
                    elif result.get("error"):
                        if result.get("doc_id"):
                            crud.update_document_analysis(result["doc_id"], status="failed")
                        st.error(f"❌ Analysis failed: {result['error']}")
                    else:
                        crud.update_document_analysis(result["doc_id"], status="processed")
                        st.session_state.active_doc_id = result["doc_id"]
                        st.session_state.active_doc_name = uploaded_file.name
                        st.session_state.last_analysis_summary = {
                            "doc_name": uploaded_file.name,
                            "clause_count": len(result.get("db_clauses", [])),
                            "document_risk_score": result.get("document_risk_score", 0),
                            "authenticity_score": result.get("authenticity_score", 0),
                            "parsing_quality_warning": result.get("parsing_quality_warning"),
                        }
                        crud.add_audit_log(
                            "analysis_completed",
                            f"Completed multi-agent processing for '{uploaded_file.name}'"
                        )
                        st.rerun()
                except RuntimeError as e:
                    # e.g. OCR engine not found — user-friendly message, no crash.
                    st.error(f"⚠️ {e}")
                except Exception as e:
                    st.error(f"❌ An error occurred during analysis: {e}")

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
    search_query = st.text_input("🔍 Search documents", placeholder="Search by name…", label_visibility="collapsed")

    documents = crud.get_all_documents(user_id=user["id"])
    if search_query:
        documents = [d for d in documents if search_query.lower() in d["name"].lower()]

    if not documents:
        st.info("No documents yet. Upload one above to begin.")
    else:
        for doc in documents:
            is_active = doc["id"] == st.session_state.active_doc_id
            status = doc.get("status", "processed")
            status_color = STATUS_COLORS.get(status, "var(--lq-success)")
            file_type = _file_type(doc["name"])
            icon = FILE_ICONS.get(file_type, "📁")
            upload_date = doc.get("upload_date")
            date_str = upload_date.strftime("%Y-%m-%d") if hasattr(upload_date, "strftime") else str(upload_date or "")

            st.markdown(
                f"""
                <div class="lq-doc-card{' active' if is_active else ''}">
                    <div class="lq-doc-title">{icon} {doc['name']}</div>
                    <div class="lq-doc-meta">
                        {file_type.upper()} · {date_str}
                        <span class="lq-status-pill" style="background:{status_color}33; color:{status_color};">{status}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            btn_cols = st.columns(2)
            with btn_cols[0]:
                if st.button(
                    "✓ Active" if is_active else "Set Active",
                    key=f"setactive_{doc['id']}", use_container_width=True,
                    disabled=is_active,
                ):
                    st.session_state.active_doc_id = doc["id"]
                    st.session_state.active_doc_name = doc["name"]
                    st.rerun()
            with btn_cols[1]:
                if st.button("Delete", key=f"delete_{doc['id']}", use_container_width=True):
                    crud.delete_document(doc["id"])
                    if is_active:
                        st.session_state.active_doc_id = None
                        st.session_state.active_doc_name = None
                    st.rerun()

    st.markdown(
        '<div class="lq-sidebar-footer">LQ-LegalAI &middot; Multi-Agent Legal Intelligence</div>',
        unsafe_allow_html=True
    )


# =============================================================================
# TOP NAVIGATION — sticky pill bar
# =============================================================================
NAV_ITEMS = [
    ("dashboard", "📊 Dashboard"),
    ("clause_analysis", "🔍 Clause Analysis"),
    ("risk_analysis", "⚠️ Risk Analysis"),
    ("contradiction", "⚡ Contradiction Detection"),
    ("comparison", "🔀 Comparison Center"),
]

with st.container(key="lq_topnav"):
    # An equal 5-way split wraps "Contradiction Detection" onto two lines
    # (it's the longest label), throwing off the whole pill row's height —
    # give it extra width, taken evenly from the shorter labels either side.
    NAV_COL_WEIGHTS = [1.0, 1.15, 1.05, 1.55, 1.15]
    nav_cols = st.columns(NAV_COL_WEIGHTS)
    for col, (page_key, label) in zip(nav_cols, NAV_ITEMS):
        with col:
            is_current = st.session_state.current_page == page_key
            if st.button(
                label, key=f"navbtn_{page_key}", use_container_width=True,
                type="primary" if is_current else "secondary",
            ):
                st.session_state.current_page = page_key
                st.rerun()

# =============================================================================
# DYNAMIC CONTENT AREA
# =============================================================================
PAGE_RENDERERS = {
    "dashboard": dashboard.render,
    "clause_analysis": clause_analysis.render,
    "risk_analysis": risk_analysis.render,
    "contradiction": contradiction.render,
    "comparison": comparison.render,
}
PAGE_RENDERERS[st.session_state.current_page]()


# =============================================================================
# FLOATING LEGAL AI CHAT
# =============================================================================
with st.container(key="lq_chat_fab"):
    if st.button("💬" if not st.session_state.chat_open else "✕", key="lq_chat_toggle"):
        st.session_state.chat_open = not st.session_state.chat_open
        st.rerun()

if st.session_state.chat_open:
    with st.container(key="lq_chat_panel"):
        st.markdown("##### 💬 Legal AI Assistant")

        in_comparison = st.session_state.current_page == "comparison"
        comparison_doc_a_id = st.session_state.get("comparison_doc_a_id")
        comparison_doc_b_id = st.session_state.get("comparison_doc_b_id")

        target_doc_id = st.session_state.active_doc_id
        scope_caption = f"Scope: active document ({st.session_state.active_doc_name})" if target_doc_id else "Scope: entire workspace"

        if in_comparison and comparison_doc_a_id and comparison_doc_b_id:
            all_docs = {d["id"]: d["name"] for d in crud.get_all_documents(user_id=user["id"])}
            scope_choice = st.selectbox(
                "Answer using:",
                options=[comparison_doc_a_id, comparison_doc_b_id],
                format_func=lambda x: all_docs.get(x, f"Doc {x}"),
                key="chat_comparison_scope",
            )
            target_doc_id = scope_choice
            scope_caption = f"Scope: {all_docs.get(target_doc_id, 'compared document')} (Comparison Center)"

        st.caption(scope_caption)

        top_row = st.columns([1, 1])
        with top_row[0]:
            if st.button("🗑️ Clear Chat", key="chat_clear", use_container_width=True):
                st.session_state.messages = []
                st.rerun()
        with top_row[1]:
            if st.button("➖ Minimize", key="chat_minimize", use_container_width=True):
                st.session_state.chat_open = False
                st.rerun()

        if not st.session_state.messages:
            st.caption("Suggested questions:")
            for q in ["What is the termination clause?", "What are my obligations?", "Is there a liability cap?"]:
                if st.button(q, key=f"suggest_{q}", use_container_width=True):
                    st.session_state.chat_pending_query = q
                    st.rerun()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and "result_payload" in msg:
                    res = msg["result_payload"]
                    with st.expander("🔍 Citations"):
                        for sc in res.supporting_clauses:
                            st.markdown(f"- {sc}")

        pending_query = st.session_state.pop("chat_pending_query", None)
        typed_query = st.chat_input("Ask a legal question…")
        prompt = pending_query or typed_query

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.spinner("Agent 9 is retrieving and validating answers…"):
                try:
                    from agents.qa_agent import answer_legal_question
                    doc_id_str = str(target_doc_id) if target_doc_id else None
                    result = answer_legal_question(prompt, doc_id_str)
                    st.session_state.messages.append({
                        "role": "assistant", "content": result.answer, "result_payload": result,
                    })
                except Exception as e:
                    st.session_state.messages.append({"role": "assistant", "content": f"Failed to answer: {e}"})
            st.rerun()
