import { Box, Typography } from "@mui/material";
import type { ReactNode } from "react";

interface MiniCardProps {
  label: string;
  value: ReactNode;
  icon: string;
}

// Port of utils/theme.py's render_mini_card (Title/Category/Type/etc. row
// above each clause card).
export function MiniCard({ label, value, icon }: MiniCardProps) {
  return (
    <Box
      sx={{
        bgcolor: "action.hover",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        px: 1.5,
        py: 1,
        height: "100%",
      }}
    >
      <Typography sx={{ fontSize: "0.85rem", opacity: 0.7, lineHeight: 1 }}>{icon}</Typography>
      <Typography
        sx={{
          fontSize: "0.88rem",
          fontWeight: 700,
          mt: 0.4,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </Typography>
      <Typography
        sx={{
          fontSize: "0.68rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          opacity: 0.55,
          fontWeight: 600,
          mt: 0.1,
        }}
      >
        {label}
      </Typography>
    </Box>
  );
}
