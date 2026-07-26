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
export function MetricCard({ label, value, accent = "primary.main", onClick }: MetricCardProps) {
  const content = (
    <>
      <Typography sx={{ fontSize: "1.9rem", lineHeight: 1.15, fontWeight: 800, fontFamily: "'Manrope', sans-serif", letterSpacing: "-0.04em", overflow: "hidden", textOverflow: "ellipsis" }}>
        {value}
      </Typography>
      <Typography
        sx={{
          fontSize: "0.82rem",
          textTransform: "uppercase",
          letterSpacing: "1.3px",
          color: "text.secondary",
          fontWeight: 600,
        }}
      >
        {label}
      </Typography>
    </>
  );

  const cardSx = {
    bgcolor: "background.paper",
    border: "1px solid #e6e9f0",
    borderRadius: 3,
    p: 2.5,
    textAlign: "center" as const,
    height: "100%",
    minHeight: 150,
    width: "100%",
    display: "flex" as const,
    flexDirection: "column" as const,
    justifyContent: "center",
    boxShadow: "0 3px 12px rgba(20, 31, 61, 0.05)",
    transition: "transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease",
    "&:hover": onClick
      ? { transform: "translateY(-4px)", borderColor: accent, boxShadow: "0 12px 24px rgba(20, 31, 61, 0.10)" }
      : undefined,
  };

  if (onClick) {
    return (
      <ButtonBase onClick={onClick} sx={cardSx}>
        {content}
      </ButtonBase>
    );
  }

  return <Box sx={cardSx}>{content}</Box>;
}
