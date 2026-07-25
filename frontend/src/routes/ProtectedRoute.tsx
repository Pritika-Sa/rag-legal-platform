import { Box, CircularProgress } from "@mui/material";
import type { ReactElement } from "react";
import { Navigate } from "react-router-dom";
import { useMeQuery } from "../hooks/useAuth";
import { useAuthStore } from "../store/authStore";

export function ProtectedRoute({ children }: { children: ReactElement }) {
  const { isLoading } = useMeQuery();
  const status = useAuthStore((s) => s.status);

  if (isLoading && status === "idle") {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return children;
}
