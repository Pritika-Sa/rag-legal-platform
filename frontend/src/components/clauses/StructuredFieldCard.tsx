import { Box, Typography } from "@mui/material";
import type { ClauseWithIntelligence } from "../../api/clausesApi";

interface StructuredFieldCardProps {
  clause: ClauseWithIntelligence;
}

// Deliberately lightweight, NOT a reuse of ClauseCard: a structured/metadata
// field (Policy Number, IDV, Nominee Name, ...) has no legal risk, no
// compliance status, no impact score, and "Simplify with AI" makes no sense
// on a bare label:value pair -- showing ClauseCard's full risk/compliance/
// impact/simplify UI on this content would just render a wall of "Not
// Applicable"/"—" badges. This shows exactly what a structured field
// actually has: its label and its value.
export function StructuredFieldCard({ clause }: StructuredFieldCardProps) {
  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 3, p: 2, mb: 1.5 }}>
      <Typography variant="caption" sx={{ opacity: 0.65, fontWeight: 600 }}>
        {clause.section_name}
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.5 }}>
        {clause.text_content || "No value extracted."}
      </Typography>
    </Box>
  );
}
