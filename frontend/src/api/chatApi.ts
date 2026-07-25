import { apiClient } from "./client";

export interface HallucinationReport {
  trust_score: number | null;
  hallucination_score: number;
  confidence: number;
  groundedness: string;
  citation_quality: string;
  unsupported_statements: string[];
}

export interface ChatResult {
  answer: string;
  supporting_clauses: string[];
  hallucination: HallucinationReport | null;
}

export async function askQuestion(query: string, docId: number | null): Promise<ChatResult> {
  const { data } = await apiClient.post<ChatResult>("/api/chat", { query, doc_id: docId });
  return data;
}
