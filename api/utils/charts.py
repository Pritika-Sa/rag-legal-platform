"""Transport-only helper: turns a plotly.graph_objects.Figure (already built
by utils/visualizer.py, unchanged) into the plain JSON react-plotly.js
expects. No chart data/trace/axis logic lives here — see Migration Risk #7 /
Part C's chart-technology justification in the migration plan.

Uses fig.to_json() (Plotly's own PlotlyJSONEncoder) rather than
fig.to_plotly_json(), which leaves trace arrays as numpy.ndarray — a type
FastAPI/Pydantic can't serialize. Round-tripping through Plotly's own
encoder is the standard way to get a plain-JSON-safe structure without
touching numpy conversion logic ourselves."""

import json
from typing import Any, Dict

import plotly.graph_objects as go


def figure_to_json(fig: go.Figure) -> Dict[str, Any]:
    return json.loads(fig.to_json())
