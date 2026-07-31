import { apiClient } from "./client";

export async function translateTexts(texts: string[], targetLanguage: string): Promise<string[]> {
  const { data } = await apiClient.post<{ translations: string[] }>("/api/translate", {
    texts,
    target_language: targetLanguage,
  });
  return data.translations;
}
