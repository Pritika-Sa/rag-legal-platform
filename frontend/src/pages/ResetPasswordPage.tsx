import { Alert, Box, Button, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { extractErrorMessage } from "../api/authApi";
import { AuthLayout } from "../layouts/AuthLayout";
import { useResetPasswordMutation } from "../hooks/useAuth";

// Consumes ?reset_token=... from the emailed link — the React equivalent of
// app.py checking st.query_params.get("reset_token") before showing the
// login tabs at all.
export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("reset_token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [clientError, setClientError] = useState<string | null>(null);
  const resetMutation = useResetPasswordMutation();
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setClientError(null);
    if (newPassword !== confirmPassword) {
      setClientError("Passwords do not match.");
      return;
    }
    resetMutation.mutate({ token, newPassword });
  };

  return (
    <AuthLayout>
      <Typography variant="h6" gutterBottom>
        🔑 Set a New Password
      </Typography>

      {resetMutation.isSuccess ? (
        <Stack spacing={2}>
          <Alert severity="success">{resetMutation.data.message}</Alert>
          <Button variant="contained" fullWidth onClick={() => navigate("/login", { replace: true })}>
            Back to login
          </Button>
        </Stack>
      ) : (
        <Box component="form" onSubmit={handleSubmit}>
          <Stack spacing={2}>
            <TextField
              label="New password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              fullWidth
            />
            <TextField
              label="Confirm new password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              fullWidth
            />
            {clientError && <Alert severity="error">{clientError}</Alert>}
            {resetMutation.isError && (
              <Alert severity="error">
                {extractErrorMessage(
                  resetMutation.error,
                  "This reset link is invalid or has expired. Request a new one from the Forgot Password tab.",
                )}
              </Alert>
            )}
            <Button type="submit" variant="contained" fullWidth loading={resetMutation.isPending}>
              Reset Password
            </Button>
            {resetMutation.isError && (
              <Button variant="text" fullWidth onClick={() => navigate("/login", { replace: true })}>
                Back to login
              </Button>
            )}
          </Stack>
        </Box>
      )}
    </AuthLayout>
  );
}
