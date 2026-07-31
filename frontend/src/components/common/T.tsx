import { useTranslatedText } from "../../hooks/useTranslatedText";

// Drop-in replacement for rendering a raw string that only exists at
// runtime — chat answers, clause explanations/simplifications, easy
// summaries, risk recommendations, authenticity/contradiction
// explanations, original clause text — anything IndicTrans2 has to
// translate because it can't be enumerated ahead of time. Renders English
// immediately and swaps to Tamil once translated; see useTranslatedText for
// the fallback/caching/batching behavior.
//
// For fixed UI copy (labels, headings, buttons, nav items, badge/filter
// text) use <S>/useStaticText instead — a compile-time literal has a known
// Tamil translation ahead of time, so it doesn't need a network round trip
// through this component.
export function T({ text }: { text: string | null | undefined }) {
  return <>{useTranslatedText(text)}</>;
}
