import { useEffect, useState } from "react";
import { useTranslationStore } from "../store/translationStore";
import { requestTranslation } from "../utils/translationBatcher";

// Translates a single already-finalized *dynamic* string via IndicTrans2 for
// display when "View in Tamil" is on — reserved for runtime AI-generated
// content (chat answers, clause explanations, summaries, etc.) that can't be
// pre-translated. Static UI copy should use useStaticText/<S> instead, which
// looks the string up in the compile-time dictionary with no network call.
//
// Never called mid-stream — callers only ever pass complete response text
// (e.g. a resolved chat answer, not partial tokens), so there is no
// partial-content translation to guard against here.
//
// On failure (network error, missing API key, timeout) this silently keeps
// the original English text — it never throws and never renders empty.
export function useTranslatedText(text: string | null | undefined): string {
  const enabled = useTranslationStore((s) => s.enabled);
  const targetLanguage = useTranslationStore((s) => s.targetLanguage);
  const [translated, setTranslated] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !text || !text.trim()) {
      setTranslated(null);
      return;
    }

    let cancelled = false;
    requestTranslation(text, targetLanguage)
      .then((result) => {
        if (!cancelled) setTranslated(result);
      })
      .catch(() => {
        // Fall back to English — the UI must never break or show empty content.
        if (!cancelled) setTranslated(null);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, text, targetLanguage]);

  if (!text) return text ?? "";
  return enabled && translated ? translated : text;
}
