import { Box, Chip, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

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
        pb: 1.75,
        mb: 2.5,
        borderBottom: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack direction="row" sx={{ alignItems: "center", gap: 1.5, minWidth: 0 }}>
        <Box sx={{ fontSize: "1.5rem", lineHeight: 1, flexShrink: 0 }}>{icon}</Box>
        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" sx={{ alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
            <Typography variant="h5" sx={{ fontSize: "1.3rem", m: 0 }}>
              {title}
            </Typography>
            {badge && (
              <Chip
                label={badge}
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
          <Typography variant="body2" sx={{ mt: 0.5, opacity: 0.65, maxWidth: 820 }}>
            {subtitle}
          </Typography>
        </Box>
      </Stack>

      <Chip
        label={docName ?? "No active document"}
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
