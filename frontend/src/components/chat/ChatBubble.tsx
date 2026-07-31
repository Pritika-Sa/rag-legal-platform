import { Accordion, AccordionDetails, AccordionSummary, Avatar, Box, Stack, Typography } from "@mui/material";
import type { ChatMessage } from "../../store/chatStore";
import { useInViewOnce } from "../../hooks/useInViewOnce";
import { S } from "../common/S";
import { T } from "../common/T";
import { HallucinationReport } from "./HallucinationReport";

// Port of app.py's st.chat_message loop: user/assistant bubble, with the
// hallucination report and a "🔍 Citations" expander beneath assistant
// answers that carried a result_payload.
export function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  // Chat history can grow long; only translate a bubble once it's actually
  // been scrolled into view, so reopening a long conversation with Tamil
  // mode on doesn't fire a translation call per past message at once.
  const [bubbleRef, visible] = useInViewOnce<HTMLDivElement>();

  return (
    <Stack ref={bubbleRef} direction="row" sx={{ gap: 1, mb: 1.5, flexDirection: isUser ? "row-reverse" : "row" }}>
      <Avatar sx={{ width: 28, height: 28, fontSize: "0.9rem", bgcolor: isUser ? "primary.main" : "secondary.main" }}>
        {isUser ? "🙂" : "⚖️"}
      </Avatar>
      <Box
        sx={{
          maxWidth: "82%",
          bgcolor: isUser ? "primary.main" : "action.hover",
          color: isUser ? "primary.contrastText" : "text.primary",
          borderRadius: 2,
          px: 1.5,
          py: 1,
        }}
      >
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
          {visible ? <T text={message.content} /> : message.content}
        </Typography>

        {!isUser && message.resultPayload && (
          <Box sx={{ mt: 1 }}>
            {message.resultPayload.hallucination && (
              <HallucinationReport hallucination={message.resultPayload.hallucination} />
            )}

            <Accordion disableGutters sx={{ mt: 1, bgcolor: "transparent" }}>
              <AccordionSummary sx={{ px: 0, minHeight: 0 }}>🔍 <S text="Citations" /></AccordionSummary>
              <AccordionDetails sx={{ px: 0 }}>
                {message.resultPayload.supporting_clauses.map((sc, i) => (
                  <Typography key={i} variant="caption" sx={{ display: "block", mb: 0.5 }}>
                    - {sc}
                  </Typography>
                ))}
              </AccordionDetails>
            </Accordion>
          </Box>
        )}
      </Box>
    </Stack>
  );
}
