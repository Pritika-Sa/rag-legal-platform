import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import * as authApi from "../api/authApi";
import { useAuthStore } from "../store/authStore";

/** Hydrates auth state from the session cookie on app load — the React
 * equivalent of app.py's `if "user" not in st.session_state: ... = None`
 * check, except here the source of truth is the server (via the cookie),
 * not client memory that starts empty every reload. */
export function useMeQuery() {
  const setUser = useAuthStore((s) => s.setUser);
  const clear = useAuthStore((s) => s.clear);

  const query = useQuery({
    queryKey: ["auth", "me"],
    queryFn: authApi.me,
    retry: false,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (query.data) setUser(query.data);
    else if (query.isError) clear();
  }, [query.data, query.isError, setUser, clear]);

  return query;
}

export function useLoginMutation() {
  const setUser = useAuthStore((s) => s.setUser);
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.login(email, password),
    onSuccess: (user) => setUser(user),
  });
}

export function useSignupMutation() {
  const setUser = useAuthStore((s) => s.setUser);
  return useMutation({
    mutationFn: ({ name, email, password }: { name: string; email: string; password: string }) =>
      authApi.signup(name, email, password),
    onSuccess: (user) => setUser(user),
  });
}

export function useLogoutMutation() {
  const clear = useAuthStore((s) => s.clear);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      clear();
      queryClient.clear();
    },
  });
}

export function useForgotPasswordMutation() {
  return useMutation({
    mutationFn: (email: string) => authApi.forgotPassword(email),
  });
}

export function useResetPasswordMutation() {
  return useMutation({
    mutationFn: ({ token, newPassword }: { token: string; newPassword: string }) =>
      authApi.resetPassword(token, newPassword),
  });
}
