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
        py: 1.25,
        mb: 2.5,
        bgcolor: "background.default",
        borderBottom: "1px solid",
        borderColor: "divider",
        overflowX: "auto",
      }}
    >
      <Stack direction="row" sx={{ gap: 1 }}>
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.to;
          return (
            <Button
              key={item.to}
              component={Link}
              to={item.to}
              variant={isActive ? "contained" : "outlined"}
              color={isActive ? "primary" : "inherit"}
              sx={{ borderRadius: 999, px: 2, whiteSpace: "nowrap" }}
            >
              {item.label}
            </Button>
          );
        })}
      </Stack>
    </Box>
  );
}
