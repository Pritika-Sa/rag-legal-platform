import { Alert, Box, Stack } from "@mui/material";
import type { ReactNode } from "react";
import type { HallucinationReport as HallucinationReportData } from "../../api/chatApi";
import { S } from "../common/S";

// Row-based (flex column widths), not character-padded like the original
// Streamlit monospace block — a fixed space-padding width tuned for English
// label lengths misaligns as soon as the label is translated (Tamil glyphs
// aren't the same width as Latin ones), so alignment is done with CSS here
// instead of padEnd().
function ReportRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Stack direction="row" sx={{ gap: 1 }}>
      <Box sx={{ width: "9.5em", flexShrink: 0, opacity: 0.75 }}>
        <S text={label} />
      </Box>
      <Box>{value}</Box>
    </Stack>
  );
}

// Direct port of app.py's post-answer hallucination block: same
// trust-score readout, same unsupported-claims warning/success, same
// >50% hallucination-score extra warning.
export function HallucinationReport({ hallucination }: { hallucination: HallucinationReportData }) {
  if (hallucination.trust_score === null) {
    return (
      <Box sx={{ fontFamily: "monospace", fontSize: "0.8rem", bgcolor: "action.hover", p: 1.5, borderRadius: 1.5 }}>
        <ReportRow label="Trust Score" value="Unknown" />
        <ReportRow label="Hallucination Check" value="Failed" />
      </Box>
    );
  }

  const unsupported = hallucination.unsupported_statements || [];

  return (
    <>
      <Box sx={{ fontFamily: "monospace", fontSize: "0.8rem", bgcolor: "action.hover", p: 1.5, borderRadius: 1.5 }}>
        <ReportRow label="Trust Score" value={`${hallucination.trust_score}%`} />
        <ReportRow label="Hallucination" value={`${hallucination.hallucination_score}%`} />
        <ReportRow label="Confidence" value={`${hallucination.confidence}%`} />
        <ReportRow label="Groundedness" value={hallucination.groundedness} />
        <ReportRow label="Citation Quality" value={hallucination.citation_quality} />
      </Box>

      {unsupported.length > 0 ? (
        <Alert severity="warning" sx={{ mt: 1, fontSize: "0.82rem" }}>
          ⚠ <S text="Unsupported Claims" />
          <br />
          {unsupported.map((s, i) => (
            <div key={i}>• {s}</div>
          ))}
        </Alert>
      ) : (
        <Alert severity="success" sx={{ mt: 1, fontSize: "0.82rem" }}>
          ✅ <S text="No unsupported claims detected." />
        </Alert>
      )}

      {(hallucination.hallucination_score || 0) > 50 && (
        <Alert severity="warning" sx={{ mt: 1, fontSize: "0.82rem" }}>
          ⚠ <S text="This answer may contain information not fully supported by the uploaded legal document." />
        </Alert>
      )}
    </>
  );
}
