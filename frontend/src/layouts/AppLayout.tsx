import { Box } from "@mui/material";
import { Outlet } from "react-router-dom";
import { ChatFab } from "../components/chat/ChatFab";
import { ChatPanel } from "../components/chat/ChatPanel";
import { Sidebar } from "../components/layout/Sidebar";
import { TopNav } from "../components/layout/TopNav";

// Structural port of app.py's overall page shell: persistent sidebar +
// sticky top nav + dynamic content area + floating chat widget (mounted
// here, above the route Outlet, so it persists across page navigation —
// same as app.py's lq_chat_fab/lq_chat_panel rendering outside the
// per-page dynamic content block).
export function AppLayout() {
  return (
    <Box sx={{ display: "flex" }}>
      <Sidebar />
      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, px: 3, pb: 4 }}>
        <TopNav />
        <Outlet />
      </Box>
      <ChatFab />
      <ChatPanel />
    </Box>
  );
}
