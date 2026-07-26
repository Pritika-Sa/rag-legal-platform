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
  const chartText = "#182230";
  const chartMuted = "#475467";

  // Figures originate in the API and some Plotly templates carry pale text
  // colors with them. Apply our readable app palette at the final render
  // boundary so titles, axis labels, ticks, legends, and gauge annotations
  // remain legible regardless of the source figure.
  const readableData = Array.isArray(data)
    ? data.map((trace) => {
        const item = trace as Record<string, unknown>;
        const gauge = (item.gauge as Record<string, unknown> | undefined) ?? {};
        const axis = (gauge.axis as Record<string, unknown> | undefined) ?? {};
        return {
          ...item,
          title: { ...(item.title as Record<string, unknown> | undefined), font: { ...((item.title as Record<string, unknown> | undefined)?.font as Record<string, unknown> | undefined), color: chartText } },
          number: { ...(item.number as Record<string, unknown> | undefined), font: { ...((item.number as Record<string, unknown> | undefined)?.font as Record<string, unknown> | undefined), color: chartText } },
          gauge: { ...gauge, axis: { ...axis, tickfont: { ...(axis.tickfont as Record<string, unknown> | undefined), color: chartMuted } } },
        };
      })
    : data;

  const axisStyle = (axis: Record<string, unknown> | undefined = {}) => ({
    ...axis,
    tickfont: { ...(axis.tickfont as Record<string, unknown> | undefined), color: chartMuted },
    title: { ...(axis.title as Record<string, unknown> | undefined), font: { ...((axis.title as Record<string, unknown> | undefined)?.font as Record<string, unknown> | undefined), color: chartMuted } },
  });
  const polar = (layout.polar as Record<string, unknown> | undefined) ?? {};

  return (
    <Plot
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      data={readableData as any}
      layout={{
        ...layout,
        font: { ...(layout.font as Record<string, unknown> | undefined), color: chartText },
        title: { ...(layout.title as Record<string, unknown> | undefined), font: { ...((layout.title as Record<string, unknown> | undefined)?.font as Record<string, unknown> | undefined), color: chartText } },
        legend: { ...(layout.legend as Record<string, unknown> | undefined), font: { ...((layout.legend as Record<string, unknown> | undefined)?.font as Record<string, unknown> | undefined), color: chartMuted } },
        xaxis: axisStyle(layout.xaxis as Record<string, unknown> | undefined),
        yaxis: axisStyle(layout.yaxis as Record<string, unknown> | undefined),
        polar: { ...polar, radialaxis: axisStyle(polar.radialaxis as Record<string, unknown> | undefined), angularaxis: axisStyle(polar.angularaxis as Record<string, unknown> | undefined) },
        autosize: true,
        height,
        margin: { t: 48, b: 42, l: 42, r: 42 },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: `${height}px` }}
      useResizeHandler
    />
  );
}
