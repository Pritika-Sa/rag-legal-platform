import { Box } from "@mui/material";
import { Fragment } from "react";
import { HIGHLIGHT_RE } from "../../utils/riskExplanation";

// Port of views/risk_analysis.py's _highlight() — bolds known risk-trigger
// keywords in red. The Python version escaped HTML then injected a <strong>
// tag via unsafe_allow_html; here the split/map naturally produces safe JSX
// text nodes (React escapes them automatically), so no raw-HTML injection
// is needed at all to get the identical visual result.
export function HighlightedText({ text }: { text: string }) {
  const parts = text.split(HIGHLIGHT_RE);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <Box key={i} component="strong" sx={{ color: "error.main" }}>
            {part}
          </Box>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}
