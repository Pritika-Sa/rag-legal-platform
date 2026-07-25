import Plot from "react-plotly.js";

interface PlotlyChartProps {
  figure: Record<string, unknown>;
  height?: number;
}

// Renders exactly the Plotly figure JSON the FastAPI adapter serialized from
// utils/visualizer.py's Figure objects (api/utils/charts.py) — no chart
// construction happens here, only display. The cast is the single, narrow
// boundary where the backend's untyped JSON meets react-plotly.js's
// Plotly.PlotParams typing; the data itself is exactly what Plotly's own
// to_json()/from_json() round-trip already produces.
export function PlotlyChart({ figure, height = 320 }: PlotlyChartProps) {
  const { data, layout } = figure as { data: unknown; layout: Record<string, unknown> };

  return (
    <Plot
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      data={data as any}
      layout={{ ...layout, autosize: true, height, margin: { t: 40, b: 30, l: 30, r: 30 } }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: `${height}px` }}
      useResizeHandler
    />
  );
}
