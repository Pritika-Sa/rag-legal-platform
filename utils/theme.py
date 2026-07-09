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


def render_header(icon: str, title: str, subtitle: str = "", badge: str = "") -> None:
    """Renders the shared professional page banner used at the top of every page.

    Replaces the old bare `st.title()` + `st.markdown()` subtitle pattern with
    a consistent gradient icon badge, heading, and muted subtitle so every
    page reads as part of one product instead of a loose collection of scripts.
    """
    badge_html = f'<span class="page-header-badge">{badge}</span>' if badge else ""
    subtitle_html = f'<p class="page-header-subtitle">{subtitle}</p>' if subtitle else ""

    st.markdown(
        f"""
        <div class="page-header">
            <div class="page-header-icon">{icon}</div>
            <div class="page-header-text">
                <div class="page-header-title-row">
                    <h1 class="page-header-title">{title}</h1>
                    {badge_html}
                </div>
                {subtitle_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value, icon: str = "", accent: str = "var(--lq-accent)") -> str:
    """Returns HTML for a single premium KPI card (caller wraps in st.markdown)."""
    return f"""
    <div class="lq-metric-card">
        <div class="lq-metric-icon" style="color: {accent};">{icon}</div>
        <div class="lq-metric-val" style="color: {accent};">{value}</div>
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
