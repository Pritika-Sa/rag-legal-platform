import { create } from "zustand";
import { clearTranslationCache } from "../utils/translationBatcher";

interface TranslationState {
  enabled: boolean;
  targetLanguage: string;
  toggle: () => void;
}

// Deliberately NOT wrapped in zustand's `persist` middleware (unlike
// activeDocumentStore) — the language preference must live in memory only
// for the current tab session and reset on reload, per the "View in
// Tamil" feature spec (no localStorage, no DB, no cookie).
export const useTranslationStore = create<TranslationState>()((set) => ({
  enabled: false,
  targetLanguage: "ta",
  toggle: () =>
    set((s) => {
      const next = !s.enabled;
      // Turning off: drop cached translations immediately rather than
      // letting them sit around unused until the next toggle-on.
      if (!next) clearTranslationCache();
      return { enabled: next };
    }),
}));
