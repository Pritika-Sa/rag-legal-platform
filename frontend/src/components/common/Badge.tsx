import { Box } from "@mui/material";

interface BadgeProps {
  label: string;
  color: string;
}

// Port of utils/theme.py's render_badge.
export function Badge({ label, color }: BadgeProps) {
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        fontWeight: 700,
        fontSize: "0.78rem",
        px: 1.4,
        py: 0.4,
        borderRadius: 1.2,
        whiteSpace: "nowrap",
        letterSpacing: "0.01em",
        bgcolor: `${color}26`,
        color,
        border: `1px solid ${color}55`,
      }}
    >
      {label}
    </Box>
  );
}
