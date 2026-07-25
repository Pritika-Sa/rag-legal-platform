import { apiClient } from "./client";

export interface ClauseForComparison {
  id: number;
  section_name: string;
  classification: string | null;
  text_content: string;
}

export interface ComparisonResult {
  doc_a_name: string;
  doc_b_name: string;
  similarity_score: number;
  change_summary: string;
  added_clauses: string[];
  removed_clauses: string[];
  modified_clauses: string[];
  risk_changes: string;
  difference_report: string;
  clauses_a: ClauseForComparison[];
  clauses_b: ClauseForComparison[];
}

export async function compareDocuments(docAId: number, docBId: number): Promise<ComparisonResult> {
  const { data } = await apiClient.post<ComparisonResult>("/api/comparison", {
    doc_a_id: docAId,
    doc_b_id: docBId,
  });
  return data;
}
