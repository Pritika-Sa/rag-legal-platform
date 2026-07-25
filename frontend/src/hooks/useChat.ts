import { useMutation } from "@tanstack/react-query";
import * as chatApi from "../api/chatApi";

export function useAskQuestionMutation() {
  return useMutation({
    mutationFn: ({ query, docId }: { query: string; docId: number | null }) =>
      chatApi.askQuestion(query, docId),
  });
}
