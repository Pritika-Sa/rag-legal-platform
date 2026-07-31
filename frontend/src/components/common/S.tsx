import { useStaticText } from "../../hooks/useStaticText";

// Drop-in replacement for rendering a raw string that is a fixed UI label
// (heading, button, nav item, filter option, badge text, etc.):
// <S text="Dashboard" /> instead of {"Dashboard"}. Looks the string up in
// the static dictionary instantly — never calls IndicTrans2. Use <T>
// instead for text that's only known at runtime (chat answers, clause
// explanations, summaries, risk recommendations, authenticity/contradiction
// explanations, original clause translation).
export function S({ text }: { text: string | null | undefined }) {
  return <>{useStaticText(text)}</>;
}
