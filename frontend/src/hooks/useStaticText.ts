import { useTranslationStore } from "../store/translationStore";
import { STATIC_STRINGS_TA } from "../i18n/staticStrings";

// Translates a fixed UI label/heading/button/nav string via the static
// dictionary — synchronous, no network call, no IndicTrans2. Use this (or
// <S>) for anything whose English text is a compile-time literal; reserve
// useTranslatedText/<T> for text that only exists at runtime (AI-generated
// answers/explanations/summaries), which the dictionary can't enumerate.
//
// A literal missing from the dictionary falls back to English rather than
// throwing or hitting the network, so a forgotten entry degrades gracefully
// instead of reintroducing the per-string translation delay this replaces.
export function useStaticText(text: string | null | undefined): string {
  const enabled = useTranslationStore((s) => s.enabled);
  const targetLanguage = useTranslationStore((s) => s.targetLanguage);

  if (!text) return text ?? "";
  if (!enabled || targetLanguage !== "ta") return text;

  const translated = STATIC_STRINGS_TA[text];
  if (translated === undefined) {
    if (import.meta.env.DEV) {
      console.warn(`[i18n] Missing static Tamil translation for: "${text}"`);
    }
    return text;
  }
  return translated;
}
