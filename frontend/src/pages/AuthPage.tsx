import { Alert, Box, Button, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { extractErrorMessage } from "../api/authApi";
import { AuthLayout } from "../layouts/AuthLayout";
import { useForgotPasswordMutation, useLoginMutation, useSignupMutation } from "../hooks/useAuth";

type TabKey = "login" | "signup" | "forgot";

// Mirrors app.py's render_auth_gate st.tabs(["Log In", "Sign Up", "Forgot Password"]) —
// one page, three tabs, not three routes, so tab-switching behaves exactly
// like the Streamlit version (no navigation, no lost input in the other tabs).
export function AuthPage() {
  const [tab, setTab] = useState<TabKey>("login");

  return (
    <AuthLayout>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="fullWidth" sx={{ mb: 2 }}>
        <Tab label="Log In" value="login" />
        <Tab label="Sign Up" value="signup" />
        <Tab label="Forgot Password" value="forgot" />
      </Tabs>
      {tab === "login" && <LoginForm />}
      {tab === "signup" && <SignupForm />}
      {tab === "forgot" && <ForgotPasswordForm />}
    </AuthLayout>
  );
}

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const loginMutation = useLoginMutation();
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loginMutation.mutate(
      { email, password },
      { onSuccess: () => navigate("/", { replace: true }) },
    );
  };

  return (
    <Box component="form" onSubmit={handleSubmit}>
      <Stack spacing={2}>
        <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required fullWidth />
        <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required fullWidth />
        {loginMutation.isError && (
          <Alert severity="error">{extractErrorMessage(loginMutation.error, "Invalid email or password.")}</Alert>
        )}
        <Button type="submit" variant="contained" fullWidth loading={loginMutation.isPending}>
          Log In
        </Button>
      </Stack>
    </Box>
  );
}

function SignupForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [clientError, setClientError] = useState<string | null>(null);
  const signupMutation = useSignupMutation();
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setClientError(null);
    // Mirrors app.py's own client-side check before calling auth.create_user
    // (password-length/email-format validation still happens server-side too).
    if (password !== confirmPassword) {
      setClientError("Passwords do not match.");
      return;
    }
    signupMutation.mutate(
      { name, email, password },
      { onSuccess: () => navigate("/", { replace: true }) },
    );
  };

  return (
    <Box component="form" onSubmit={handleSubmit}>
      <Stack spacing={2}>
        <TextField label="Full name" value={name} onChange={(e) => setName(e.target.value)} required fullWidth />
        <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required fullWidth />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          helperText="At least 8 characters."
          required
          fullWidth
        />
        <TextField
          label="Confirm password"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
          fullWidth
        />
        {clientError && <Alert severity="error">{clientError}</Alert>}
        {signupMutation.isError && (
          <Alert severity="error">{extractErrorMessage(signupMutation.error, "Could not create account.")}</Alert>
        )}
        <Button type="submit" variant="contained" fullWidth loading={signupMutation.isPending}>
          Create Account
        </Button>
      </Stack>
    </Box>
  );
}

function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const forgotMutation = useForgotPasswordMutation();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    forgotMutation.mutate(email);
  };

  if (forgotMutation.isSuccess) {
    return <Alert severity="success">{forgotMutation.data.message}</Alert>;
  }

  return (
    <Box component="form" onSubmit={handleSubmit}>
      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
        Enter your account email and we&apos;ll send you a reset link.
      </Typography>
      <Stack spacing={2}>
        <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required fullWidth />
        <Button type="submit" variant="contained" fullWidth loading={forgotMutation.isPending}>
          Send Reset Link
        </Button>
      </Stack>
    </Box>
  );
}
