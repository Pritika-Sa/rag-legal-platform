import { create } from "zustand";

interface ComparisonState {
  docAId: number | null;
  docBId: number | null;
  setDocA: (id: number) => void;
  setDocB: (id: number) => void;
}

// Separate from activeDocumentStore on purpose — mirrors the original
// app.py's actual mechanism: Streamlit widgets with a `key=` (like
// comparison_doc_a_id/comparison_doc_b_id) automatically populate
// st.session_state under that key, making them globally readable (the
// floating chat widget reads them for its comparison-scope picker) while
// staying entirely independent of active_doc_id. A plain local useState in
// ComparisonPage can't be read from the chat widget elsewhere in the tree,
// so this store is the correct port of that behavior, not scope creep.
export const useComparisonStore = create<ComparisonState>((set) => ({
  docAId: null,
  docBId: null,
  setDocA: (id) => set({ docAId: id }),
  setDocB: (id) => set({ docBId: id }),
}));
