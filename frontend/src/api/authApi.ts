import { apiClient } from "./client";

export interface User {
  id: number;
  name: string;
  email: string;
}

export interface MessageResponse {
  message: string;
}

export async function signup(name: string, email: string, password: string): Promise<User> {
  const { data } = await apiClient.post<User>("/api/auth/signup", { name, email, password });
  return data;
}

export async function login(email: string, password: string): Promise<User> {
  const { data } = await apiClient.post<User>("/api/auth/login", { email, password });
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/api/auth/logout");
}

export async function forgotPassword(email: string): Promise<MessageResponse> {
  const { data } = await apiClient.post<MessageResponse>("/api/auth/forgot-password", { email });
  return data;
}

export async function resetPassword(token: string, newPassword: string): Promise<MessageResponse> {
  const { data } = await apiClient.post<MessageResponse>("/api/auth/reset-password", {
    token,
    newPassword,
  });
  return data;
}

export async function me(): Promise<User> {
  const { data } = await apiClient.get<User>("/api/auth/me");
  return data;
}

/** Pulls the FastAPI adapter's `{"detail": "..."}` error body into a plain
 * message string, mirroring the plain-text messages app.py showed via
 * st.error() for the same failures (invalid credentials, duplicate email,
 * expired reset token, ...). */
export function extractErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail ?? fallback;
}
