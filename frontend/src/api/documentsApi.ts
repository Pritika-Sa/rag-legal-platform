import { apiClient } from "./client";

export interface DocumentSummary {
  id: number;
  name: string;
  status: string;
  upload_date: string | null;
  document_type: string | null;
}

export interface DashboardData {
  total_clauses: number;
  risky_clauses: number;
  total_contradictions: number;
  document_type: string;
  risk_distribution: Record<string, number>;
  radar_chart: Record<string, unknown> | null;
  bar_chart: Record<string, unknown> | null;
}

export interface UploadResult {
  file_path: string;
  name: string;
}

export interface ProcessResult {
  doc_id: number;
  clause_count: number;
  document_risk_score: number;
  authenticity_score: number;
  parsing_quality_warning: string | null;
}

/** The 409 "already analyzed" branch returns detail as {message, doc_id}
 * (see api/routers/documents.py::process_document) rather than a plain
 * string like every other error here — this reads that shape specifically,
 * distinct from authApi's extractErrorMessage which assumes a string. */
export function extractAlreadyAnalyzedDocId(error: unknown): number | null {
  const detail = (error as { response?: { status?: number; data?: { detail?: { doc_id?: number } } } })?.response;
  if (detail?.status === 409) {
    return detail.data?.detail?.doc_id ?? null;
  }
  return null;
}

export async function listDocuments(): Promise<DocumentSummary[]> {
  const { data } = await apiClient.get<DocumentSummary[]>("/api/documents");
  return data;
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post<UploadResult>("/api/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getDashboard(docId: number): Promise<DashboardData> {
  const { data } = await apiClient.get<DashboardData>(`/api/documents/${docId}/dashboard`);
  return data;
}

export async function processDocument(filePath: string, name: string): Promise<ProcessResult> {
  const { data } = await apiClient.post<ProcessResult>("/api/documents/process", {
    file_path: filePath,
    name,
  });
  return data;
}

export async function deleteDocument(id: number): Promise<void> {
  await apiClient.delete(`/api/documents/${id}`);
}
