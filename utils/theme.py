import streamlit as st


def is_light_theme() -> bool:
    """Returns True if the client's active theme is light.

    Reflects manual overrides made via Streamlit's Settings menu (not just
    the config.toml default), since st.context.theme is resolved per
    session. Used for chart libraries like Plotly/PyVis that render color
    values directly and can't pick up the page's CSS custom properties.
    """
    try:
        return st.context.theme.type == "light"
    except Exception:
        return False


# Sentinel distinguishing "caller didn't pass doc_name" (no badge slot at
# all — e.g. Comparison Center, which manages its own two documents and has
# no single active document) from "caller passed doc_name=None" (show the
# badge slot with a muted "No active document" state).
_DOC_NAME_UNSET = object()


def render_header(icon: str, title: str, subtitle: str = "", badge: str = "", doc_name=_DOC_NAME_UNSET) -> None:
    """Renders the shared, compact page banner used at the top of every page.

    Slimmer than a filled card — just an icon, heading, muted subtitle, and
    (optionally) the currently active document shown as a badge on the same
    row, so pages no longer need their own separate "Active Document: X"
    info banner underneath.
    """
    badge_html = f'<span class="page-header-badge">{badge}</span>' if badge else ""
    subtitle_html = f'<p class="page-header-subtitle">{subtitle}</p>' if subtitle else ""

    if doc_name is _DOC_NAME_UNSET:
        doc_html = ""
    elif doc_name:
        doc_html = (
            '<div class="page-header-docname">'
            f'<span class="page-header-docname-icon">📄</span>'
            f'<span class="page-header-docname-value">{doc_name}</span>'
            '</div>'
        )
    else:
        doc_html = '<div class="page-header-docname page-header-docname-empty">No active document</div>'

    st.markdown(
        f"""
        <div class="page-header">
            <div class="page-header-left">
                <span class="page-header-icon-inline">{icon}</span>
                <div class="page-header-text">
                    <div class="page-header-title-row">
                        <h1 class="page-header-title">{title}</h1>
                        {badge_html}
                    </div>
                    {subtitle_html}
                </div>
            </div>
            {doc_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value, icon: str = "", accent: str = "var(--lq-accent)") -> str:
    """Returns HTML for a single premium KPI card (caller wraps in st.markdown).

    The value is always rendered in the neutral text color (not `accent`) so
    a row of cards reads as one professional set of numbers instead of a
    multi-color scatter — `accent` now only tints the small icon. `title=`
    on the value holds the full text as a tooltip since long values (e.g. a
    document type name) are truncated with an ellipsis rather than wrapped,
    which is what kept breaking row alignment when one card's value ran
    longer than its neighbors'.
    """
    return f"""
    <div class="lq-metric-card">
        <div class="lq-metric-icon" style="color: {accent};">{icon}</div>
        <div class="lq-metric-val" title="{value}">{value}</div>
        <div class="lq-metric-title">{label}</div>
    </div>
    """


def render_mini_card(label: str, value, icon: str = "") -> str:
    """Returns HTML for a compact summary card (title/page/category/type/
    character-count row above a clause's info table) — lighter-weight than
    render_metric_card since many of these render per page."""
    return f"""
    <div class="lq-mini-card">
        <div class="lq-mini-card-icon">{icon}</div>
        <div class="lq-mini-card-value" title="{value}">{value}</div>
        <div class="lq-mini-card-label">{label}</div>
    </div>
    """


def render_badge(text: str, color: str, text_color: str = "#121212") -> str:
    """Returns HTML for a single colored status pill (risk/importance/compliance/
    authenticity/contradiction indicators). Caller embeds it inline inside a larger
    st.markdown(unsafe_allow_html=True) block — it is not a standalone widget."""
    return (
        f'<span class="lq-badge" style="background-color:{color}; color:{text_color};">'
        f'{text}</span>'
    )
