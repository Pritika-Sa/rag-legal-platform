import { Alert, Box } from "@mui/material";
import type { HallucinationReport as HallucinationReportData } from "../../api/chatApi";

const LABEL_WIDTH = 18;

function padLabel(label: string): string {
  return label.padEnd(LABEL_WIDTH, " ");
}

// Direct port of app.py's post-answer hallucination block: same monospace
// trust-score readout, same unsupported-claims warning/success, same
// >50% hallucination-score extra warning.
export function HallucinationReport({ hallucination }: { hallucination: HallucinationReportData }) {
  if (hallucination.trust_score === null) {
    return (
      <Box component="pre" sx={{ fontFamily: "monospace", fontSize: "0.8rem", bgcolor: "action.hover", p: 1.5, borderRadius: 1.5 }}>
        Trust Score: Unknown{"\n"}Hallucination Check: Failed
      </Box>
    );
  }

  const unsupported = hallucination.unsupported_statements || [];

  return (
    <>
      <Box component="pre" sx={{ fontFamily: "monospace", fontSize: "0.8rem", bgcolor: "action.hover", p: 1.5, borderRadius: 1.5 }}>
        {"------------------------------------\n"}
        {padLabel("Trust Score")}
        {hallucination.trust_score}%{"\n"}
        {padLabel("Hallucination")}
        {hallucination.hallucination_score}%{"\n"}
        {padLabel("Confidence")}
        {hallucination.confidence}%{"\n"}
        {padLabel("Groundedness")}
        {hallucination.groundedness}
        {"\n"}
        {padLabel("Citation Quality")}
        {hallucination.citation_quality}
      </Box>

      {unsupported.length > 0 ? (
        <Alert severity="warning" sx={{ mt: 1, fontSize: "0.82rem" }}>
          ⚠ Unsupported Claims
          <br />
          {unsupported.map((s, i) => (
            <div key={i}>• {s}</div>
          ))}
        </Alert>
      ) : (
        <Alert severity="success" sx={{ mt: 1, fontSize: "0.82rem" }}>
          ✅ No unsupported claims detected.
        </Alert>
      )}

      {(hallucination.hallucination_score || 0) > 50 && (
        <Alert severity="warning" sx={{ mt: 1, fontSize: "0.82rem" }}>
          ⚠ This answer may contain information not fully supported by the uploaded legal document.
        </Alert>
      )}
    </>
  );
}
