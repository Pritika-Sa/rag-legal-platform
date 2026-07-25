import { create } from "zustand";
import type { ChatResult } from "../api/chatApi";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  resultPayload?: ChatResult;
}

interface ChatState {
  isOpen: boolean;
  messages: ChatMessage[];
  toggle: () => void;
  close: () => void;
  addMessage: (message: ChatMessage) => void;
  clearMessages: () => void;
}

// Equivalent of app.py's st.session_state.chat_open/messages — plain
// in-memory store (no persist middleware), matching the original's own
// behavior: chat history was never persisted across a browser reload
// either, only across page navigation within the same session (which this
// store also matches, since it lives above the router in AppLayout).
export const useChatStore = create<ChatState>((set) => ({
  isOpen: false,
  messages: [],
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
  close: () => set({ isOpen: false }),
  addMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  clearMessages: () => set({ messages: [] }),
}));
