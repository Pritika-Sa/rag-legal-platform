import { Fab } from "@mui/material";
import { useChatStore } from "../../store/chatStore";

// Port of app.py's `with st.container(key="lq_chat_fab"):` toggle button.
export function ChatFab() {
  const { isOpen, toggle } = useChatStore();

  return (
    <Fab
      color="primary"
      onClick={toggle}
      sx={{ position: "fixed", bottom: 24, right: 24, zIndex: 1000 }}
    >
      {isOpen ? "✕" : "💬"}
    </Fab>
  );
}
