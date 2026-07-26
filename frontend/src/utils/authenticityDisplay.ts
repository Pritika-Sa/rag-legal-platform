// Ports views/risk_analysis.py's AUTHENTICITY_FACTOR_DISPLAY /
// AUTHENTICITY_LEVEL_COLORS / _factor_score_color verbatim.

export const AUTHENTICITY_FACTOR_DISPLAY: Record<string, [string, string]> = {
  structure: ["📐", "Document Structure"],
  clause_completeness: ["📋", "Mandatory Clauses"],
  cross_field: ["🔗", "Cross-Field Consistency"],
  entity_verification: ["👥", "Entity Verification"],
  digital_verification: ["🔏", "Digital Verification"],
  metadata_validation: ["🗂️", "Metadata Validation"],
  semantic_consistency: ["🧭", "Semantic Consistency"],
  document_type_validator: ["🧾", "Document-Type Checks"],
};

// 2026-07-26 calibration pass: authenticity/dai.py now classifies into 6
// tiers (95/90/80/65/40 cuts) instead of 4 — see DAI_TIER_LABELS. Colors
// step from green (most authentic) through yellow/orange to red (least),
// keeping the pre-existing green/yellow/red anchors so a document that
// used to read "Authentic" (green) or "Highly Suspicious" (red) still
// lands on a visually consistent color under the finer-grained labels.
export const AUTHENTICITY_LEVEL_COLORS: Record<string, string> = {
  "Highly Authentic": "#00CC96",
  "Strongly Authentic": "#00CC96",
  "Likely Authentic": "#4CD97B",
  "Mostly Authentic": "#FECB52",
  Suspicious: "#F0932B",
  "Likely Manipulated or Forged": "#EF553B",
  "Insufficient Signal": "#888888",
};

export function factorDisplay(name: string): [string, string] {
  return AUTHENTICITY_FACTOR_DISPLAY[name] ?? ["•", name];
}

export function factorScoreColor(score: number | null): string {
  if (score === null) return "#888888";
  if (score >= 0.7) return "#00CC96";
  if (score >= 0.4) return "#FECB52";
  return "#EF553B";
}
