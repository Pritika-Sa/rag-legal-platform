import { useMutation, useQuery } from "@tanstack/react-query";
import * as clausesApi from "../api/clausesApi";

export function useClausesQuery(docId: number | null) {
  return useQuery({
    queryKey: ["documents", docId, "clauses"],
    queryFn: () => clausesApi.getClauses(docId as number),
    enabled: docId !== null,
  });
}

export function useSimplifyMutation(docId: number) {
  return useMutation({
    mutationFn: (clauseId: number) => clausesApi.simplifyClause(docId, clauseId),
  });
}
