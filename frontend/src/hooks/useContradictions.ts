import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as contradictionsApi from "../api/contradictionsApi";

export function useContradictionsQuery(docId: number | null) {
  return useQuery({
    queryKey: ["documents", docId, "contradictions"],
    queryFn: () => contradictionsApi.getContradictions(docId as number),
    enabled: docId !== null,
  });
}

export function useReanalyzeContradictionsMutation(docId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => contradictionsApi.reanalyzeContradictions(docId),
    onSuccess: (data) => {
      queryClient.setQueryData(["documents", docId, "contradictions"], data);
    },
  });
}
