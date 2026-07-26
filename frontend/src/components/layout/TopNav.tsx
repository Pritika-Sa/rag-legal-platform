import { Box, Button, Stack } from "@mui/material";
import { Link, useLocation } from "react-router-dom";

// Direct port of app.py's NAV_ITEMS / sticky pill nav — same 5 pages, same
// order, same icons/labels. Active-state is computed explicitly from the
// current path (mirrors app.py's own
// `type="primary" if is_current else "secondary"` check) rather than relying
// on NavLink's automatic "active" class, which doesn't propagate through a
// wrapped MUI Button (MUI resolves `className` to a plain string before
// NavLink ever sees it, so NavLink's own active-class injection never fires).
const NAV_ITEMS = [
  { to: "/", label: "📊 Dashboard" },
  { to: "/clauses", label: "🔍 Clause Analysis" },
  { to: "/risk", label: "⚠️ Risk Analysis" },
  { to: "/contradiction", label: "⚡ Contradiction Detection" },
  { to: "/comparison", label: "🔀 Comparison Center" },
];

export function TopNav() {
  const { pathname } = useLocation();

  return (
    <Box
      sx={{
        position: "sticky",
        top: 0,
        zIndex: 10,
        py: 1.5,
        mb: 3,
        bgcolor: "rgba(247, 248, 252, 0.92)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid #e6e9f0",
        overflowX: "auto",
      }}
    >
      <Stack
        direction="row"
        sx={{
          gap: 0.75,
          width: { xs: "max-content", md: "100%" },
          minWidth: "max-content",
          p: 0.5,
          bgcolor: "#eef0f7",
          borderRadius: 2.5,
        }}
      >
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.to;
          return (
            <Button
              key={item.to}
              component={Link}
              to={item.to}
              variant={isActive ? "contained" : "outlined"}
              color={isActive ? "primary" : "inherit"}
              sx={{
                borderRadius: 2,
                px: 2,
                minHeight: 38,
                flex: { md: 1 },
                whiteSpace: "nowrap",
                borderColor: isActive ? "transparent" : "transparent",
                color: isActive ? "#fff" : "text.secondary",
                bgcolor: isActive ? "primary.main" : "transparent",
                boxShadow: isActive ? "0 4px 12px rgba(99, 110, 250, 0.28)" : "none",
                "&:hover": { bgcolor: isActive ? "primary.dark" : "rgba(99, 110, 250, 0.08)", borderColor: "transparent" },
              }}
            >
              {item.label}
            </Button>
          );
        })}
      </Stack>
    </Box>
  );
}
