import plotly.express as px
import plotly.graph_objects as go
from utils.theme import is_light_theme

# Plotly renders literal color values rather than reading the page's CSS, so
# chart chrome (axis text, gridlines, chart background) needs to be picked
# explicitly per theme instead of inheriting from app.py's CSS vars.
_CHART_COLORS = {
    "dark": {
        "text": "#E0E0E0", "grid": "#333333",
        "legend_bg": "rgba(0,0,0,0.5)", "threshold": "white", "muted": "#888888",
    },
    "light": {
        "text": "#31333F", "grid": "#D5D5D5",
        "legend_bg": "rgba(255,255,255,0.7)", "threshold": "#31333F", "muted": "#6b6b6b",
    },
}


def _chart_colors():
    return _CHART_COLORS["light"] if is_light_theme() else _CHART_COLORS["dark"]


def generate_risk_pie_chart(risk_dist):
    """Generates a Plotly Pie Chart for risk level distribution."""
    # Ensure risk_dist is formatted nicely
    data = {"Risk Level": [], "Count": []}
    for level in ["High", "Medium", "Low", "None"]:
        data["Risk Level"].append(level)
        data["Count"].append(risk_dist.get(level, 0))
        
    colors = {
        "High": "#EF553B",    # Sleek Red
        "Medium": "#FECB52",  # Sleek Amber
        "Low": "#636EFA",     # Sleek Blue
        "None": "#00CC96"     # Sleek Green
    }
    
    fig = px.pie(
        data_frame=data,
        names="Risk Level",
        values="Count",
        color="Risk Level",
        color_discrete_map=colors,
        hole=0.4,
        title="Clause Risk Level Distribution"
    )
    
    chart_colors = _chart_colors()
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color=chart_colors["text"],
        title_font_size=18,
        margin=dict(t=40, b=10, l=10, r=10)
    )
    return fig

def generate_category_bar_chart(clauses):
    """Generates a Plotly Bar Chart showing clause categories and their risk levels."""
    # clauses is a list of SQLite Row objects
    categories = {}
    for c in clauses:
        cat = c['risk_category'] or 'Uncategorized'
        level = c['risk_level'] or 'None'
        if cat not in categories:
            categories[cat] = {"High": 0, "Medium": 0, "Low": 0, "None": 0}
        categories[cat][level] += 1
        
    # Flatten database
    data = {"Category": [], "Risk Level": [], "Count": []}
    for cat, levels in categories.items():
        for lvl, val in levels.items():
            if val > 0:
                data["Category"].append(cat)
                data["Risk Level"].append(lvl)
                data["Count"].append(val)
                
    colors = {
        "High": "#EF553B",
        "Medium": "#FECB52",
        "Low": "#636EFA",
        "None": "#00CC96"
    }
    
    fig = px.bar(
        data_frame=data,
        x="Category",
        y="Count",
        color="Risk Level",
        color_discrete_map=colors,
        title="Risk Severity by Clause Category",
        barmode="stack"
    )
    
    chart_colors = _chart_colors()
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color=chart_colors["text"],
        title_font_size=18,
        xaxis=dict(gridcolor=chart_colors["grid"]),
        yaxis=dict(gridcolor=chart_colors["grid"]),
        margin=dict(t=40, b=20, l=10, r=10)
    )
    return fig

def generate_risk_gauge_chart(risk_score):
    """Generates a Plotly Gauge Chart for the overall Document Risk Score."""
    # Determine color based on score
    if risk_score < 40:
        bar_color = "#00CC96"  # Low risk - Green
    elif risk_score < 75:
        bar_color = "#FECB52"  # Medium risk - Amber
    else:
        bar_color = "#EF553B"  # High/Critical risk - Red

    chart_colors = _chart_colors()
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = risk_score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Document Risk Score", 'font': {'size': 24, 'color': chart_colors["text"]}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': chart_colors["grid"]},
            'bar': {'color': bar_color},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': chart_colors["grid"],
            'steps': [
                {'range': [0, 39], 'color': "rgba(0, 204, 150, 0.2)"},
                {'range': [40, 74], 'color': "rgba(254, 203, 82, 0.2)"},
                {'range': [75, 100], 'color': "rgba(239, 85, 59, 0.2)"}
            ],
            'threshold': {
                'line': {'color': chart_colors["threshold"], 'width': 4},
                'thickness': 0.75,
                'value': risk_score
            }
        }
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': chart_colors["text"], 'family': "Arial"},
        margin=dict(t=50, b=20, l=20, r=20),
        height=350
    )

    return fig

def generate_impact_radar_chart(legal: int, financial: int, business: int, compliance: int):
    """Generates a Plotly Radar Chart for Agent 6 Impact Analysis."""
    categories = ['Legal Impact', 'Financial Impact', 'Business Impact', 'Compliance Impact']
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=[legal, financial, business, compliance, legal], # close the loop
        theta=categories + [categories[0]],
        fill='toself',
        fillcolor='rgba(99, 110, 250, 0.5)',
        line=dict(color='#636EFA', width=3),
        name='Impact Profile'
    ))
    
    chart_colors = _chart_colors()
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickcolor=chart_colors["grid"],
                gridcolor=chart_colors["grid"],
                tickfont=dict(color=chart_colors["muted"])
            ),
            angularaxis=dict(
                gridcolor=chart_colors["grid"],
                tickfont=dict(color=chart_colors["text"], size=14)
            ),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': chart_colors["text"]},
        showlegend=False,
        margin=dict(t=40, b=40, l=40, r=40),
        height=400
    )

    return fig


def generate_clause_impact_radar_chart(impact_level: int, business_impact: int, legal_impact: int):
    """Generates a 3-axis Plotly Radar Chart for the consolidated Clause Analysis
    card's Impact Analysis section (Impact Level, Business Impact, Legal Impact) —
    a lighter alternative to generate_impact_radar_chart's 4-axis version."""
    categories = ['Impact Level', 'Business Impact', 'Legal Impact']

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=[impact_level, business_impact, legal_impact, impact_level],  # close the loop
        theta=categories + [categories[0]],
        fill='toself',
        fillcolor='rgba(99, 110, 250, 0.5)',
        line=dict(color='#636EFA', width=3),
        name='Clause Impact'
    ))

    chart_colors = _chart_colors()
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickcolor=chart_colors["grid"],
                gridcolor=chart_colors["grid"],
                tickfont=dict(color=chart_colors["muted"])
            ),
            angularaxis=dict(
                gridcolor=chart_colors["grid"],
                tickfont=dict(color=chart_colors["text"], size=14)
            ),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': chart_colors["text"]},
        showlegend=False,
        margin=dict(t=40, b=40, l=40, r=40),
        height=380
    )

    return fig

