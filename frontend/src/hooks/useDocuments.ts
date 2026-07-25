import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as documentsApi from "../api/documentsApi";

export function useDocumentsQuery() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: documentsApi.listDocuments,
  });
}

export function useDashboardQuery(docId: number | null) {
  return useQuery({
    queryKey: ["documents", docId, "dashboard"],
    queryFn: () => documentsApi.getDashboard(docId as number),
    enabled: docId !== null,
  });
}

export function useUploadMutation() {
  return useMutation({
    mutationFn: (file: File) => documentsApi.uploadDocument(file),
  });
}

export function useProcessMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ filePath, name }: { filePath: string; name: string }) =>
      documentsApi.processDocument(filePath, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useDeleteMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => documentsApi.deleteDocument(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });
}
