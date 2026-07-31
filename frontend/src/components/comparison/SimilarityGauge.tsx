import { useTheme } from "@mui/material";
import Plot from "react-plotly.js";
import { useStaticText } from "../../hooks/useStaticText";

// Port of views/comparison.py's inline go.Figure(go.Indicator(...)) gauge —
// unlike the Dashboard/Risk-Analysis charts, this one was never built via
// utils/visualizer.py to begin with (it's constructed directly in the
// Streamlit view file with plotly.graph_objects), so it's UI-layer code
// being ported to the UI layer, not a duplication of anything backend-owned.
// Light/dark colors are chosen from the MUI theme instead of Streamlit's
// is_light_theme(), consistent with the plan's chart-theming decision.
export function SimilarityGauge({ score }: { score: number }) {
  const theme = useTheme();
  const isLight = theme.palette.mode === "light";
  const textColor = isLight ? "#31333F" : "#FFFFFF";
  const gridColor = isLight ? "#D5D5D5" : "#333333";
  const titleText = useStaticText("Similarity Score");

  return (
    <Plot
      data={[
        {
          type: "indicator",
          mode: "gauge+number",
          value: score,
          domain: { x: [0, 1], y: [0, 1] },
          title: { text: titleText, font: { size: 24, color: textColor } },
          gauge: {
            axis: { range: [0, 100], tickcolor: gridColor },
            bar: { color: "#636EFA" },
            bgcolor: "rgba(0,0,0,0)",
            borderwidth: 2,
            bordercolor: gridColor,
          },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } as any,
      ]}
      layout={{
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: textColor },
        height: 300,
        margin: { t: 40, b: 20, l: 30, r: 30 },
        autosize: true,
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "300px" }}
      useResizeHandler
    />
  );
}
