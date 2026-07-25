import { useMutation } from "@tanstack/react-query";
import * as comparisonApi from "../api/comparisonApi";

export function useCompareMutation() {
  return useMutation({
    mutationFn: ({ docAId, docBId }: { docAId: number; docBId: number }) =>
      comparisonApi.compareDocuments(docAId, docBId),
  });
}
