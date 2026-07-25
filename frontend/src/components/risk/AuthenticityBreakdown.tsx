import { Box, Grid, Typography } from "@mui/material";
import type { AuthenticityFactor } from "../../api/riskApi";
import { factorDisplay, factorScoreColor } from "../../utils/authenticityDisplay";

interface AuthenticityBreakdownProps {
  factors: AuthenticityFactor[];
  documentType: string | null;
  documentTypeConfidence: number | null;
  confidence: number | null;
}

// Port of views/risk_analysis.py's authenticity factor breakdown panel —
// same per-factor progress bar, same "Not applicable" / evidence caption
// handling.
export function AuthenticityBreakdown({
  factors,
  documentType,
  documentTypeConfidence,
  confidence,
}: AuthenticityBreakdownProps) {
  const metaBits: string[] = [];
  if (documentType) {
    const confStr = documentTypeConfidence !== null ? ` (${Math.round(documentTypeConfidence * 100)}% confidence)` : "";
    metaBits.push(`Detected type: ${documentType}${confStr}`);
  }
  if (confidence !== null) metaBits.push(`Overall confidence: ${confidence.toFixed(0)}/100`);

  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, p: 2 }}>
      {metaBits.length > 0 && (
        <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mb: 1.5 }}>
          {metaBits.join("  ·  ")}
        </Typography>
      )}
      {factors.map((factor) => {
        const [icon, displayName] = factorDisplay(factor.name);
        const { applicable, score, weight, evidence } = factor;
        const barColor = factorScoreColor(score);

        return (
          <Grid container spacing={2} key={factor.name} sx={{ alignItems: "center", mb: 1.5 }}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {icon} {displayName}
              </Typography>
            </Grid>
            <Grid size={{ xs: 8, sm: 6 }}>
              {applicable && score !== null ? (
                <Box sx={{ bgcolor: "action.disabledBackground", borderRadius: 1.5, height: 10, mt: 1 }}>
                  <Box
                    sx={{
                      bgcolor: barColor,
                      width: `${Math.max(0, Math.min(1, score)) * 100}%`,
                      height: 10,
                      borderRadius: 1.5,
                    }}
                  />
                </Box>
              ) : (
                <Typography variant="caption" sx={{ opacity: 0.6 }}>
                  Not applicable to this document
                </Typography>
              )}
            </Grid>
            <Grid size={{ xs: 4, sm: 2 }}>
              {applicable && score !== null ? (
                <>
                  <Typography variant="body2" sx={{ textAlign: "right" }}>
                    {Math.round(score * 100)}%
                  </Typography>
                  {weight !== null && (
                    <Typography variant="caption" sx={{ opacity: 0.6, display: "block", textAlign: "right" }}>
                      weight {Math.round(weight * 100)}%
                    </Typography>
                  )}
                </>
              ) : (
                <Typography variant="body2" sx={{ textAlign: "right" }}>
                  —
                </Typography>
              )}
            </Grid>
            {evidence?.[0] && (
              <Grid size={12}>
                <Typography variant="caption" sx={{ opacity: 0.65 }}>
                  {applicable ? evidence[0] : `ℹ️ ${evidence[0]}`}
                </Typography>
              </Grid>
            )}
          </Grid>
        );
      })}
    </Box>
  );
}
