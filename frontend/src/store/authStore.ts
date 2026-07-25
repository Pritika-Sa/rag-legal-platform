import { create } from "zustand";
import type { User } from "../api/authApi";

type AuthStatus = "idle" | "authenticated" | "unauthenticated";

interface AuthState {
  user: User | null;
  status: AuthStatus;
  setUser: (user: User) => void;
  clear: () => void;
}

// The direct equivalent of `st.session_state.user` — held client-side for
// the duration of the tab, hydrated from GET /api/auth/me on load (see
// hooks/useAuth.ts) instead of Streamlit's server-memory session.
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: "idle",
  setUser: (user) => set({ user, status: "authenticated" }),
  clear: () => set({ user: null, status: "unauthenticated" }),
}));
