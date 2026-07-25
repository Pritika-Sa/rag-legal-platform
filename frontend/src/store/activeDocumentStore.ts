import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ActiveDocumentState {
  activeDocId: number | null;
  activeDocName: string | null;
  setActiveDocument: (id: number, name: string) => void;
  clearActiveDocument: () => void;
}

// Equivalent of st.session_state.active_doc_id/active_doc_name — persisted
// to localStorage (via zustand's persist middleware) so it survives a page
// refresh, matching how the value stayed put across Streamlit reruns within
// the same browser tab.
export const useActiveDocumentStore = create<ActiveDocumentState>()(
  persist(
    (set) => ({
      activeDocId: null,
      activeDocName: null,
      setActiveDocument: (id, name) => set({ activeDocId: id, activeDocName: name }),
      clearActiveDocument: () => set({ activeDocId: null, activeDocName: null }),
    }),
    { name: "lq-active-document" },
  ),
);
