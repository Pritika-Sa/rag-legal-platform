import { useMutation, useQuery } from "@tanstack/react-query";
import * as riskApi from "../api/riskApi";

export function useRiskOverviewQuery(docId: number | null) {
  return useQuery({
    queryKey: ["documents", docId, "risk-overview"],
    queryFn: () => riskApi.getRiskOverview(docId as number),
    enabled: docId !== null,
  });
}

export function useRiskyClausesQuery(docId: number | null) {
  return useQuery({
    queryKey: ["documents", docId, "risky-clauses"],
    queryFn: () => riskApi.getRiskyClauses(docId as number),
    enabled: docId !== null,
  });
}

export function useRecomputeAuthenticityMutation(docId: number) {
  return useMutation({
    mutationFn: () => riskApi.recomputeAuthenticity(docId),
  });
}

export function useQuickEstimateMutation(docId: number) {
  return useMutation({
    mutationFn: () => riskApi.quickEstimate(docId),
  });
}
