import { Alert, Avatar, Box, Button, Chip, CircularProgress, Drawer, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useLogoutMutation } from "../../hooks/useAuth";
import { useDeleteMutation, useDocumentsQuery } from "../../hooks/useDocuments";
import { useActiveDocumentStore } from "../../store/activeDocumentStore";
import { useAuthStore } from "../../store/authStore";
import { fileIcon, fileType, STATUS_COLORS } from "../../utils/documentDisplay";
import { UploadPanel } from "./UploadPanel";

export const SIDEBAR_WIDTH = 280;

// Structural port of app.py's `with st.sidebar:` block. Phase 4 adds
// Set Active / Delete per document card (same two-button row, same
// no-confirmation-dialog delete behavior as the original) — search remains
// later-phase scope.
export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logoutMutation = useLogoutMutation();
  const navigate = useNavigate();
  const documentsQuery = useDocumentsQuery();
  const deleteMutation = useDeleteMutation();
  const { activeDocId, setActiveDocument, clearActiveDocument } = useActiveDocumentStore();

  const handleDelete = (docId: number, isActive: boolean) => {
    deleteMutation.mutate(docId, {
      onSuccess: () => {
        if (isActive) clearActiveDocument();
      },
    });
  };

  const initials = user?.name
    ? user.name
        .split(" ")
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("")
    : "U";

  const handleLogout = () => {
    logoutMutation.mutate(undefined, { onSuccess: () => navigate("/login", { replace: true }) });
  };

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: SIDEBAR_WIDTH,
        flexShrink: 0,
        [`& .MuiDrawer-paper`]: {
          width: SIDEBAR_WIDTH,
          boxSizing: "border-box",
          p: 2,
          display: "flex",
          flexDirection: "column",
          height: "100dvh",
          overflow: "hidden",
          borderRight: "1px solid #e4e7ee",
          bgcolor: "#ffffff",
        },
      }}
    >
      <Box sx={{ textAlign: "center", pt: 1, pb: 2, flexShrink: 0 }}>
        <Box
          sx={{
            fontSize: "1.4rem",
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
        <Box sx={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.12em", opacity: 0.55, mt: 0.5 }}>
          Legal Intelligence Platform
        </Box>
      </Box>

      <Stack
        direction="row"
        sx={{
          alignItems: "center",
          gap: 1.5,
          background: "linear-gradient(135deg, rgba(99,110,250,0.14) 0%, rgba(99,110,250,0.03) 100%)",
          border: "1px solid rgba(99,110,250,0.25)",
          borderRadius: 3,
          p: 1.75,
          mb: 1.5,
        }}
      >
        <Avatar sx={{ bgcolor: "primary.main", fontWeight: 800 }}>{initials}</Avatar>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, fontSize: "0.95rem" }} noWrap>
            {user?.name}
          </Typography>
          <Typography sx={{ fontSize: "0.76rem", opacity: 0.6 }} noWrap>
            {user?.email}
          </Typography>
        </Box>
      </Stack>

      <Button variant="outlined" fullWidth onClick={handleLogout} loading={logoutMutation.isPending} sx={{ flexShrink: 0 }}>
        Log Out
      </Button>

      <Box sx={{ borderTop: "1px solid", borderColor: "divider", my: 2 }} />

      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
        📁 Document Management
      </Typography>

      <UploadPanel />

      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 1, flexShrink: 0 }}>
        <Typography sx={{ fontSize: "0.7rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em", color: "text.secondary" }}>
          Your documents
        </Typography>
        <Chip label={documentsQuery.data?.length ?? 0} size="small" sx={{ height: 20, minWidth: 28, fontSize: "0.68rem", fontWeight: 700, bgcolor: "rgba(99, 110, 250, 0.10)", color: "primary.main" }} />
      </Stack>

      <Box sx={{ flexGrow: 1, overflowY: "auto", overflowX: "hidden", minHeight: 0, pr: 0.5, mr: -0.5 }}>
        {documentsQuery.isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
            <CircularProgress size={22} />
          </Box>
        )}
        {documentsQuery.isError && <Alert severity="error" sx={{ fontSize: "0.8rem" }}>Failed to load documents.</Alert>}
        {documentsQuery.data?.length === 0 && (
          <Alert severity="info" sx={{ fontSize: "0.8rem" }}>No documents yet.</Alert>
        )}
        {documentsQuery.data?.map((doc) => {
          const isActive = doc.id === activeDocId;
          const statusColor = STATUS_COLORS[doc.status] ?? STATUS_COLORS.processed;
          const isDeletingThis = deleteMutation.isPending && deleteMutation.variables === doc.id;
          return (
            <Box
              key={doc.id}
              sx={{
                border: "1px solid",
                borderColor: isActive ? "primary.main" : "#e4e7ee",
                boxShadow: isActive ? "0 0 0 1px rgba(99, 110, 250, 0.16)" : "none",
                borderRadius: 2,
                p: 1.25,
                mb: 1,
                bgcolor: isActive ? "rgba(99, 110, 250, 0.035)" : "#fff",
              }}
            >
              <Typography sx={{ fontWeight: 700, fontSize: "0.86rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={doc.name}>
                {fileIcon(doc.name)} {doc.name}
              </Typography>
              <Stack direction="row" sx={{ alignItems: "center", gap: 0.75, mt: 0.5, mb: 1 }}>
                <Typography sx={{ fontSize: "0.7rem", opacity: 0.6 }}>
                  {fileType(doc.name).toUpperCase()}
                </Typography>
                <Chip
                  label={doc.status}
                  size="small"
                  sx={{
                    height: 18,
                    fontSize: "0.62rem",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    bgcolor: `${statusColor}33`,
                    color: statusColor,
                  }}
                />
              </Stack>
              <Stack direction="row" sx={{ gap: 1 }}>
                <Button
                  size="small"
                  variant={isActive ? "contained" : "outlined"}
                  disabled={isActive}
                  onClick={() => setActiveDocument(doc.id, doc.name)}
                  sx={{ flex: 1, fontSize: "0.72rem" }}
                >
                  {isActive ? "✓ Active" : "Set Active"}
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  onClick={() => handleDelete(doc.id, isActive)}
                  loading={isDeletingThis}
                  sx={{ flex: 1, fontSize: "0.72rem" }}
                >
                  Delete
                </Button>
              </Stack>
            </Box>
          );
        })}
      </Box>
      <Typography sx={{ display: "none" }}>
        LQ-LegalAI · Multi-Agent Legal Intelligence
      </Typography>
    </Drawer>
  );
}
