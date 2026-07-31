import { Box, Chip, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { S } from "./S";

interface PageHeaderProps {
  icon: ReactNode;
  title: string;
  subtitle: string;
  badge?: string;
  docName?: string | null;
}

// Direct port of utils/theme.py's render_header — same layout (icon + title +
// badge on the left, active-document pill on the right, bottom divider).
// Layout props are passed via `sx` throughout (rather than the old MUI
// system-prop shorthand like `alignItems=".."` directly on the component),
// since the installed MUI version no longer types those shorthand props on
// Box/Stack/Typography unless an explicit `component` is given.
export function PageHeader({ icon, title, subtitle, badge, docName }: PageHeaderProps) {
  return (
    <Stack
      direction="row"
      sx={{
        alignItems: "flex-start",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 2,
        p: { xs: 2, sm: 2.5 },
        mb: 3,
        border: "1px solid #e6e9f0",
        borderRadius: 3,
        bgcolor: "#fff",
        boxShadow: "0 2px 10px rgba(20, 31, 61, 0.04)",
      }}
    >
      <Stack direction="row" sx={{ alignItems: "center", gap: 1.5, minWidth: 0 }}>
        <Box sx={{ fontSize: "1.35rem", lineHeight: 1, flexShrink: 0, display: "grid", placeItems: "center", width: 42, height: 42, borderRadius: 2, bgcolor: "rgba(99, 110, 250, 0.10)" }}>{icon}</Box>
        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" sx={{ alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
            <Typography variant="h5" sx={{ fontSize: "1.35rem", m: 0, letterSpacing: "-0.02em" }}>
              <S text={title} />
            </Typography>
            {badge && (
              <Chip
                label={<S text={badge} />}
                size="small"
                sx={{
                  fontSize: "0.68rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "primary.main",
                  bgcolor: "rgba(99, 110, 250, 0.14)",
                  border: "1px solid rgba(99, 110, 250, 0.35)",
                  height: 22,
                }}
              />
            )}
          </Stack>
          <Typography variant="body2" sx={{ mt: 0.5, color: "text.secondary", maxWidth: 820 }}>
            <S text={subtitle} />
          </Typography>
        </Box>
      </Stack>

      <Chip
        label={docName ?? <S text="No active document" />}
        size="small"
        sx={{
          flexShrink: 0,
          fontWeight: 600,
          bgcolor: docName ? "rgba(99, 110, 250, 0.10)" : "transparent",
          border: "1px solid",
          borderColor: docName ? "rgba(99, 110, 250, 0.25)" : "divider",
          color: docName ? "primary.main" : "text.secondary",
        }}
      />
    </Stack>
  );
}
