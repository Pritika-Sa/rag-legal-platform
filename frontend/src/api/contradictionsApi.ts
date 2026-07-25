import { apiClient } from "./client";

export interface AffectedClause {
  id: number | null;
  section_name: string;
  text_content: string;
  value: string | null;
}

export interface Contradiction {
  id: number;
  contradiction_type: string | null;
  explanation: string | null;
  resolution: string | null;
  severity: string | null;
  affected_clauses: AffectedClause[];
}

export async function getContradictions(docId: number): Promise<Contradiction[]> {
  const { data } = await apiClient.get<Contradiction[]>(`/api/documents/${docId}/contradictions`);
  return data;
}

export async function reanalyzeContradictions(docId: number): Promise<Contradiction[]> {
  const { data } = await apiClient.post<Contradiction[]>(`/api/documents/${docId}/contradictions/reanalyze`);
  return data;
}
