import { apiClient } from "./client";

export interface AuthenticityFactor {
  name: string;
  applicable: boolean;
  score: number | null;
  weight: number | null;
  evidence: string[];
  [key: string]: unknown;
}

export interface RiskOverview {
  authenticity_score: number | null;
  authenticity_level: string;
  authenticity_document_type: string | null;
  authenticity_document_type_confidence: number | null;
  authenticity_confidence: number | null;
  authenticity_factors: AuthenticityFactor[] | null;
}

export interface QuickEstimateResult {
  risk_score: number;
  risk_level: string;
  recommendations: string;
  risk_gauge_chart: Record<string, unknown>;
}

export interface DimensionBreakdownEntry {
  dimension?: string;
  contribution?: number;
  feature_evidence?: string[];
  semantic_evidence?: { prototype?: string; similarity?: number };
}

export interface RiskyClause {
  id: number;
  section_name: string;
  text_content: string;
  risk_level: string;
  risk_category: string | null;
  explanation: string | null;
  dimension_breakdown: DimensionBreakdownEntry[];
  importance_category: string | null;
  confidence_score: number | null;
}

export async function getRiskOverview(docId: number): Promise<RiskOverview> {
  const { data } = await apiClient.get<RiskOverview>(`/api/documents/${docId}/risk-overview`);
  return data;
}

export async function recomputeAuthenticity(docId: number): Promise<RiskOverview> {
  const { data } = await apiClient.post<RiskOverview>(`/api/documents/${docId}/authenticity/recompute`);
  return data;
}

export async function quickEstimate(docId: number): Promise<QuickEstimateResult> {
  const { data } = await apiClient.post<QuickEstimateResult>(`/api/documents/${docId}/risk/quick-estimate`);
  return data;
}

export async function getRiskyClauses(docId: number): Promise<RiskyClause[]> {
  const { data } = await apiClient.get<RiskyClause[]>(`/api/documents/${docId}/risky-clauses`);
  return data;
}
