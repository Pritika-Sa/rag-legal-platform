import { apiClient } from "./client";

export interface ClauseWithIntelligence {
  id: number;
  section_name: string;
  text_content: string;
  classification: string | null;
  risk_category: string | null;
  risk_level: string;
  simplification: string | null;
  importance_score: number | null;
  importance_category: string;
  legal_impact: number | null;
  financial_impact: number | null;
  business_impact: number | null;
  compliance_impact: number | null;
  confidence_score: number | null;
  impact_chart: Record<string, unknown> | null;
}

export interface SimplifyResult {
  simplified_clause: string;
  easy_summary: string;
  rights: string;
  obligations: string;
  hidden_risks: string;
  ai_recommendation: string;
}

export async function getClauses(docId: number): Promise<ClauseWithIntelligence[]> {
  const { data } = await apiClient.get<ClauseWithIntelligence[]>(`/api/documents/${docId}/clauses`);
  return data;
}

export async function simplifyClause(docId: number, clauseId: number): Promise<SimplifyResult> {
  const { data } = await apiClient.post<SimplifyResult>(
    `/api/documents/${docId}/clauses/${clauseId}/simplify`,
  );
  return data;
}
