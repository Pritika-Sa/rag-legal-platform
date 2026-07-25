import { Box, ButtonBase, Typography } from "@mui/material";
import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: ReactNode;
  icon: string;
  accent?: string;
  onClick?: () => void;
}

// Port of utils/theme.py's render_metric_card / the clickable "dash_nav_"
// card variant in views/dashboard.py — same icon/value/label layout, same
// hover-lift treatment. A single component handles both the static
// "Document Type" card and the three clickable metric cards (rendered as a
// real button, matching why the Streamlit version used a real st.button
// instead of an HTML overlay — see that file's own comment on why).
export function MetricCard({ label, value, icon, accent = "primary.main", onClick }: MetricCardProps) {
  const content = (
    <>
      <Box sx={{ fontSize: "1.4rem", mb: 0.75 }}>{icon}</Box>
      <Typography sx={{ fontSize: "1.7rem", fontWeight: 800, fontFamily: "'Manrope', sans-serif" }}>
        {value}
      </Typography>
      <Typography
        sx={{
          fontSize: "0.82rem",
          textTransform: "uppercase",
          letterSpacing: "1.3px",
          opacity: 0.6,
          fontWeight: 600,
        }}
      >
        {label}
      </Typography>
    </>
  );

  const cardSx = {
    bgcolor: "background.paper",
    border: "1px solid",
    borderColor: "divider",
    borderRadius: 3.5,
    p: 2.75,
    textAlign: "center" as const,
    height: "100%",
    width: "100%",
    boxShadow: 2,
    transition: "transform 0.2s ease, border-color 0.2s ease",
    "&:hover": onClick
      ? { transform: "translateY(-4px)", borderColor: accent }
      : undefined,
  };

  if (onClick) {
    return (
      <ButtonBase onClick={onClick} sx={{ ...cardSx, display: "block" }}>
        {content}
      </ButtonBase>
    );
  }

  return <Box sx={cardSx}>{content}</Box>;
}
