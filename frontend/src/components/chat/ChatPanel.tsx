import { Box, Button, IconButton, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useAskQuestionMutation } from "../../hooks/useChat";
import { useDocumentsQuery } from "../../hooks/useDocuments";
import { useStaticText } from "../../hooks/useStaticText";
import { useActiveDocumentStore } from "../../store/activeDocumentStore";
import { useChatStore } from "../../store/chatStore";
import { useComparisonStore } from "../../store/comparisonStore";
import { S } from "../common/S";
import { ChatBubble } from "./ChatBubble";

const SUGGESTED_QUESTIONS = [
  "What is the termination clause?",
  "What are my obligations?",
  "Is there a liability cap?",
];

const OUT_OF_SCOPE_MESSAGE =
  "This question is not related to the active document. Legal AI can answer only questions based on the active document.";

// Port of app.py's `with st.container(key="lq_chat_panel"):` block: same
// scope resolution (active document by default; a doc-A/doc-B picker when
// on the Comparison page with both selected), same suggested-questions row,
// same clear/minimize controls.
export function ChatPanel() {
  const { pathname } = useLocation();
  const { isOpen, messages, close, addMessage, clearMessages } = useChatStore();
  const { activeDocId, activeDocName } = useActiveDocumentStore();
  const { docAId, docBId } = useComparisonStore();
  const documentsQuery = useDocumentsQuery();
  const askMutation = useAskQuestionMutation();
  const [inputValue, setInputValue] = useState("");
  const [comparisonScope, setComparisonScope] = useState<number | null>(null);
  const askPlaceholder = useStaticText("Ask a legal question…");

  if (!isOpen) return null;

  const inComparison = pathname === "/comparison";
  const bothComparisonDocsSelected = inComparison && docAId !== null && docBId !== null;

  let targetDocId: number | null = activeDocId;
  // JSX (not a plain string) so the static "Scope:" wording can be
  // translated while the dynamic document name stays exactly as stored.
  let scopeCaption: React.ReactNode = targetDocId ? (
    <>
      <S text="Scope: active document" /> ({activeDocName})
    </>
  ) : (
    <S text="Scope: entire workspace" />
  );

  if (bothComparisonDocsSelected) {
    const allDocs = new Map((documentsQuery.data ?? []).map((d) => [d.id, d.name]));
    const scopeChoice = comparisonScope ?? docAId!;
    targetDocId = scopeChoice;
    const compareDocName = allDocs.get(scopeChoice);
    scopeCaption = (
      <>
        <S text="Scope:" /> {compareDocName ?? <S text="compared document" />} (<S text="Comparison Center" />)
      </>
    );
  }

  const submitQuery = (query: string) => {
    addMessage({ role: "user", content: query });
    askMutation.mutate(
      { query, docId: targetDocId },
      {
        onSuccess: (result) => {
          addMessage(
            result.answer.trim() === OUT_OF_SCOPE_MESSAGE
              ? { role: "assistant", content: result.answer }
              : { role: "assistant", content: result.answer, resultPayload: result },
          );
        },
        onError: (error) => {
          addMessage({ role: "assistant", content: `Failed to answer: ${error}` });
        },
      },
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = inputValue.trim();
    if (!query) return;
    setInputValue("");
    submitQuery(query);
  };

  return (
    <Box
      sx={{
        position: "fixed",
        bottom: 92,
        right: 24,
        zIndex: 1000,
        width: 400,
        maxWidth: "92vw",
        maxHeight: "70vh",
        display: "flex",
        flexDirection: "column",
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 3,
        boxShadow: 8,
        p: 2,
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        💬 <S text="Legal AI Assistant" />
      </Typography>

      {bothComparisonDocsSelected ? (
        <TextField
          select
          size="small"
          label={<S text="Answer using:" />}
          value={comparisonScope ?? docAId}
          onChange={(e) => setComparisonScope(Number(e.target.value))}
          sx={{ mb: 1 }}
        >
          {[docAId, docBId].map((id) => (
            <MenuItem key={id} value={id!}>
              {documentsQuery.data?.find((d) => d.id === id)?.name ?? (
                <>
                  <S text="Doc" /> {id}
                </>
              )}
            </MenuItem>
          ))}
        </TextField>
      ) : null}
      <Typography variant="caption" sx={{ opacity: 0.65, mb: 1 }}>
        {scopeCaption}
      </Typography>

      <Stack direction="row" sx={{ gap: 1, mb: 1 }}>
        <Button size="small" fullWidth onClick={clearMessages}>
          🗑️ <S text="Clear Chat" />
        </Button>
        <Button size="small" fullWidth onClick={close}>
          ➖ <S text="Minimize" />
        </Button>
      </Stack>

      <Box sx={{ flexGrow: 1, overflowY: "auto", minHeight: 100 }}>
        {messages.length === 0 && (
          <Box sx={{ mb: 1 }}>
            <Typography variant="caption" sx={{ opacity: 0.65 }}>
              <S text="Suggested questions:" />
            </Typography>
            <Stack sx={{ gap: 0.5, mt: 0.5 }}>
              {SUGGESTED_QUESTIONS.map((q) => (
                <Button key={q} size="small" variant="outlined" onClick={() => submitQuery(q)}>
                  <S text={q} />
                </Button>
              ))}
            </Stack>
          </Box>
        )}

        {messages.map((m, i) => (
          <ChatBubble key={i} message={m} />
        ))}

        {askMutation.isPending && (
          <Typography variant="caption" sx={{ opacity: 0.6 }}>
            <S text="Legal AI is thinking… (this may take a few seconds)" />
          </Typography>
        )}
      </Box>

      <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1, display: "flex", gap: 1 }}>
        <TextField
          size="small"
          fullWidth
          placeholder={askPlaceholder}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
        />
        <IconButton type="submit" color="primary" disabled={!inputValue.trim() || askMutation.isPending}>
          ➤
        </IconButton>
      </Box>
    </Box>
  );
}
