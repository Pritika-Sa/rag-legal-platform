import { Box, Container, Paper } from "@mui/material";
import type { ReactNode } from "react";

// Mirrors app.py's render_auth_gate: a centered card on a plain background,
// no sidebar/nav — auth screens are the one place in the app with no chrome.
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        bgcolor: "background.default",
        py: 4,
      }}
    >
      <Container maxWidth="xs">
        <Box sx={{ textAlign: "center", pt: 3, pb: 2 }}>
          <Box
            sx={{
              fontSize: "1.55rem",
              fontWeight: 800,
              fontFamily: "'Manrope', sans-serif",
              background: "linear-gradient(90deg, #4b4fd1, #8385f7)",
              backgroundClip: "text",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            ⚖️ LQ-LegalAI
          </Box>
          <Box
            sx={{
              fontSize: "0.72rem",
              textTransform: "uppercase",
              letterSpacing: "0.12em",
              opacity: 0.55,
              mt: 0.5,
            }}
          >
            Legal Intelligence Platform
          </Box>
        </Box>
        <Paper elevation={2} sx={{ p: 3, borderRadius: 3 }}>
          {children}
        </Paper>
      </Container>
    </Box>
  );
}
