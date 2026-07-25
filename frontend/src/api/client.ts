import axios from "axios";
import { useAuthStore } from "../store/authStore";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

const PUBLIC_PATHS = ["/login", "/reset-password"];

// Any 401 means the httpOnly session cookie is missing/expired (or the JWT's
// 7-day lifetime ran out) — clear local auth state and send the user back to
// the login screen, the same outcome app.py's
// `if st.session_state.user is None: render_auth_gate()` produced. A full
// navigation (not client-side routing) is used deliberately here: this
// interceptor runs outside the Router/QueryClient React tree, and a fresh
// load is the simplest way to guarantee no stale TanStack Query cache or
// component state survives an expired session.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !PUBLIC_PATHS.includes(window.location.pathname)) {
      useAuthStore.getState().clear();
      window.location.assign("/login");
    }
    return Promise.reject(error);
  },
);
