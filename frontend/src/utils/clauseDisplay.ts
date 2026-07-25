// Ports the color maps and small classification helpers from
// views/clause_analysis.py verbatim — same thresholds, same colors.

export const RISK_COLORS: Record<string, string> = {
  High: "#EF553B",
  Medium: "#FECB52",
  Low: "#636EFA",
  None: "#00CC96",
};

export const IMPORTANCE_COLORS: Record<string, string> = {
  Critical: "#EF553B",
  Important: "#FECB52",
  Informational: "#00CC96",
};

export const COMPLIANCE_COLORS: Record<string, string> = {
  "Needs Review": "#EF553B",
  Monitor: "#FECB52",
  Compliant: "#00CC96",
};

export const IMPACT_LEVEL_COLORS: Record<string, string> = {
  High: "#EF553B",
  Medium: "#FECB52",
  Low: "#00CC96",
};

export function confidenceTier(confidence: number | null): string {
  if (confidence === null) return "Unscored";
  if (confidence >= 0.7) return "High-Confidence Match";
  if (confidence >= 0.4) return "Moderate-Confidence Match";
  return "Low-Confidence Match";
}

export function complianceStatus(complianceImpact: number | null): string {
  if (complianceImpact === null) return "Unknown";
  if (complianceImpact >= 70) return "Needs Review";
  if (complianceImpact >= 40) return "Monitor";
  return "Compliant";
}

export function impactLevelScore(
  legal: number | null,
  financial: number | null,
  business: number | null,
  compliance: number | null,
): number | null {
  const scores = [legal, financial, business, compliance].filter((v): v is number => v !== null);
  if (scores.length === 0) return null;
  return Math.round(scores.reduce((sum, v) => sum + v, 0) / scores.length);
}

export function impactLevelLabel(score: number | null): string | null {
  if (score === null) return null;
  if (score >= 70) return "High";
  if (score >= 40) return "Medium";
  return "Low";
}
