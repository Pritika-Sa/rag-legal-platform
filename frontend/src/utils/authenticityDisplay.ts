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

export const AUTHENTICITY_LEVEL_COLORS: Record<string, string> = {
  Authentic: "#00CC96",
  "Likely Authentic": "#00CC96",
  Suspicious: "#FECB52",
  "Highly Suspicious": "#EF553B",
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
