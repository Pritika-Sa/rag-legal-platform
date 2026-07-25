import { Accordion, AccordionDetails, AccordionSummary, Box, Stack, Typography } from "@mui/material";
import type { Contradiction } from "../../api/contradictionsApi";
import { Badge } from "../common/Badge";

const SEVERITY_COLORS: Record<string, string> = {
  High: "#EF553B",
  Medium: "#FECB52",
  Low: "#636EFA",
};

// Direct port of views/contradiction.py's per-contradiction expander: same
// severity badge, same affected-clauses list (with value callout when
// present), same explanation box and resolution success banner.
export function ContradictionCard({ contradiction }: { contradiction: Contradiction }) {
  const severity = (contradiction.severity ?? "Medium").replace(/^\w/, (c) => c.toUpperCase());
  const sevColor = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS.Medium;
  const contradictionType = contradiction.contradiction_type || "Contradiction";
  const affected = contradiction.affected_clauses || [];
  const clauseCountLabel = affected.length > 2 ? ` (${affected.length} clauses)` : "";

  return (
    <Accordion defaultExpanded disableGutters sx={{ mb: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 2 }}>
      <AccordionSummary>
        ⚠️ {contradictionType}
        {clauseCountLabel} - {severity.toUpperCase()} Severity
      </AccordionSummary>
      <AccordionDetails>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Badge label={`${severity.toUpperCase()} SEVERITY`} color={sevColor} />
          <Typography variant="body2" sx={{ opacity: 0.65, fontWeight: 700 }}>
            {contradictionType}
          </Typography>
        </Stack>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          🔍 Affected Clauses
        </Typography>
        {affected
          .filter((c) => c.section_name)
          .map((c, i) => (
            <Typography key={i} variant="body2" sx={{ mb: 0.5 }}>
              {c.value ? (
                <>
                  • <strong>{c.section_name}</strong> →{" "}
                  <Box component="code" sx={{ bgcolor: "action.hover", px: 0.5, borderRadius: 0.5 }}>
                    {c.value}
                  </Box>
                </>
              ) : (
                `• ${c.section_name}`
              )}
            </Typography>
          ))}

        <Box
          sx={{
            bgcolor: "action.hover",
            p: 1.5,
            borderRadius: 1.5,
            borderLeft: "3px solid",
            borderColor: sevColor,
            mt: 1.5,
            mb: 2,
          }}
        >
          <Typography variant="subtitle2">Explanation of Conflict:</Typography>
          <Typography variant="body2" sx={{ opacity: 0.85, mt: 0.5 }}>
            {contradiction.explanation || ""}
          </Typography>
        </Box>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          💡 Suggested Resolution
        </Typography>
        <Box sx={{ bgcolor: "success.main", color: "success.contrastText", p: 1.5, borderRadius: 1.5, opacity: 0.9 }}>
          {contradiction.resolution || "No specific resolution suggested."}
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
