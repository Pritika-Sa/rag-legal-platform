// Direct port of views/risk_analysis.py's plain-English "why is this risky"
// bullet generation — same dicts, same regexes, same precedence (structured
// dimension_breakdown preferred, then the older keyword-scorer explanation
// format, then plain sentence-splitting). This is UI/presentation logic
// that lived in the Streamlit view file itself (not risk_engine/ or
// agents/), so porting it to TypeScript is the correct migration move, not
// a duplication of immutable backend logic — it only ever reads fields the
// backend already computed and persisted (explanation, dimension_breakdown).

export const HIGHLIGHT_WORDS = [
  "vague", "unclear", "ambiguous", "ambiguity", "undefined", "missing",
  "unlimited", "uncapped", "penalt", "indemnif", "liability",
  "sole discretion", "unilateral", "without notice", "non-compliant",
  "breach", "dispute", "terminate", "termination",
  "one-sided", "no upper limit", "no limit", "not clearly stated", "lack of clarity",
];

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export const HIGHLIGHT_RE = new RegExp(`(${HIGHLIGHT_WORDS.map(escapeRegExp).join("|")})`, "gi");

const SIMPLIFY_MAP: Record<string, string> = {
  indemnification: "compensation for losses",
  indemnify: "compensate for losses",
  indemnity: "compensation for losses",
  unilaterally: "one-sided",
  unilateral: "one-sided",
  "sole discretion": "its own judgment, without asking you",
  ambiguous: "unclear",
  ambiguity: "lack of clarity",
  undefined: "not clearly stated",
  "liquidated damages": "a pre-agreed penalty amount",
  "governing law": "which state's or country's laws apply",
  jurisdiction: "which court has authority",
  "force majeure": "unforeseeable events beyond anyone's control",
  "cure period": "time allowed to fix the problem",
  statutory: "required by law",
  "non-compliant": "not following the rules",
  "unlimited liability": "no limit on what you could owe",
  uncapped: "with no upper limit",
  notwithstanding: "despite",
  herein: "in this document",
  thereof: "of it",
};
const SIMPLIFY_RE = new RegExp(
  `(${Object.keys(SIMPLIFY_MAP)
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|")})`,
  "gi",
);

const SCORE_EXPLANATION_RE =
  /^Classified as '(?<clauseType>[^']*)'\s*\((?<riskCategory>[^)]*) risk category\)\.\s*Risk score \d+\/100:\s*(?<contributions>.*)$/is;
const CONTRIBUTION_RE = /^'([^']+)'\s*([+-]\d+)$/;

export const CATEGORY_CONTEXT: Record<string, string> = {
  Financial: "This clause carries financial risk — it can directly affect what you pay, owe, or recover if something goes wrong.",
  Legal: "This clause carries legal risk — it can affect your legal standing, obligations, or ability to enforce your rights.",
  Compliance: "This clause carries compliance risk — failing to meet its requirements could expose you to regulatory or contractual consequences.",
  Operational: "This clause carries operational risk — it can disrupt how the agreement is carried out in practice.",
  Ambiguity: "This clause carries ambiguity risk — vague or hedged language makes its obligations harder to predict or enforce.",
};

const PHRASE_EXPLANATIONS: Record<string, string> = {
  "without notice": "it lets the other party act (e.g. terminate or change terms) without warning you first, leaving you no time to prepare or respond",
  "sole discretion": "the decision is left entirely to the other party's own judgment, with no requirement to consult you or explain it",
  "immediate termination": "the agreement can end right away, with no transition period to wind down obligations or find an alternative",
  immediately: "an obligation or consequence takes effect right away, with no buffer time to comply or react",
  "no cure period": "there's no window to fix a mistake or missed obligation before consequences like termination kick in",
  "at any time": "the other party can exercise this right whenever it wants, with no defined trigger or advance planning for you",
  "for convenience": "the agreement can be ended for no stated reason at all, not just for a breach — no cause is required",
  irrevocable: "once given, it cannot be taken back or changed later, even if circumstances change",
  "unlimited liability": "there is no cap on how much you could be required to pay if something goes wrong",
  unlimited: "there is no cap on the exposure this clause creates",
  uncapped: "no maximum limit is set on the financial exposure this clause creates",
  "no limitation": "the clause explicitly rules out any cap on liability or obligation",
  "without limitation": "this signals the surrounding obligation has no cap or boundary",
  "consequential damages": "you could be liable for indirect losses (like lost profits) on top of direct damages, which can be large and hard to predict",
  "punitive damages": "you could be liable for damages meant to punish, not just compensate — these can far exceed actual losses",
  "joint and several": "each party can be held responsible for the entire obligation, not just its own share, if another party can't pay",
  "non-refundable": "money already paid will not be returned, even if circumstances change or the agreement ends early",
  penalty: "a monetary penalty applies, adding cost on top of the underlying obligation",
  "liquidated damages": "a pre-agreed penalty amount applies automatically if there's a breach, regardless of your actual loss",
  "late fee": "falling behind on a deadline (usually payment) triggers an extra charge",
  interest: "outstanding amounts accrue interest, which increases what you owe the longer it stays unpaid",
  "immediate payment": "payment is due right away, leaving no time to arrange funds",
  acceleration: "missing one payment or obligation can trigger the entire remaining balance to become due at once",
  "no offset": "you can't reduce what you owe by amounts the other party separately owes you",
  forfeit: "you could lose money, property, or rights already paid for or earned, without compensation",
  "hold harmless": "you may be required to cover the other party's losses, even for issues you didn't directly cause",
  "unlimited indemnification": "there is no cap on how much you could owe to cover the other party's losses or claims",
  defend: "you may be required to pay for and manage the legal defense of claims brought against the other party",
  "third-party claims": "you could be responsible for claims brought by people or companies outside this agreement",
  "sole negligence": "you may owe compensation even for harm caused solely by the other party's own carelessness",
};

function simplify(text: string): string {
  if (!text) return text;
  return text.replace(SIMPLIFY_RE, (match) => SIMPLIFY_MAP[match.toLowerCase()] ?? match);
}

function bulletize(explanation: string): string[] {
  if (!explanation) return [];
  const text = explanation.trim();
  let parts: string[];
  if (text.startsWith("-") || text.includes("\n-")) {
    parts = text.split("\n").map((p) => p.replace(/^[- ]+|[- ]+$/g, "").trim());
  } else {
    parts = text.split(/(?<=[.;])\s+/);
  }
  return parts.map((p) => p.trim()).filter((p) => p.length > 3).slice(0, 6);
}

export interface DimensionBreakdownEntry {
  dimension?: string;
  contribution?: number;
  feature_evidence?: string[];
  semantic_evidence?: { prototype?: string; similarity?: number };
}

function dimensionBreakdownBullets(dimensionBreakdown: DimensionBreakdownEntry[]): string[] {
  const bullets: string[] = [];
  for (const dim of dimensionBreakdown) {
    if (typeof dim !== "object" || dim === null) continue;
    if ((dim.contribution ?? 0) <= 0) continue;
    const dimension = dim.dimension ?? "";
    const context = CATEGORY_CONTEXT[dimension] ?? (dimension ? `This clause carries ${dimension.toLowerCase()} risk.` : "");
    if (!context) continue;

    const evidenceBits: string[] = [];
    const featureEvidence = dim.feature_evidence ?? [];
    if (featureEvidence.length > 0) evidenceBits.push(featureEvidence[0]);
    const prototype = dim.semantic_evidence?.prototype;
    if (prototype) evidenceBits.push(`reads similarly to "${prototype}"`);

    const detail = evidenceBits.length > 0 ? ` (${evidenceBits.join("; ")})` : "";
    bullets.push(`${context}${detail}`);
  }
  return bullets.slice(0, 6);
}

export function riskExplanationBullets(
  explanation: string | null | undefined,
  dimensionBreakdown: DimensionBreakdownEntry[] | null | undefined,
): string[] {
  if (dimensionBreakdown && dimensionBreakdown.length > 0) {
    const bullets = dimensionBreakdownBullets(dimensionBreakdown);
    if (bullets.length > 0) return bullets;
  }

  if (!explanation) return [];
  const text = explanation.trim();
  const match = text.match(SCORE_EXPLANATION_RE);
  if (!match?.groups) {
    return bulletize(text).map(simplify);
  }

  const riskCategory = match.groups.riskCategory.trim();
  const bullets = [
    CATEGORY_CONTEXT[riskCategory] ?? "This clause was flagged for elevated risk based on its specific wording.",
  ];

  for (let part of match.groups.contributions.split(";")) {
    part = part.trim().replace(/\.$/, "");
    if (!part || part.toLowerCase().startsWith("base tier")) continue;
    const contributionMatch = part.match(CONTRIBUTION_RE);
    if (!contributionMatch) continue;
    const phrase = contributionMatch[1];
    const points = parseInt(contributionMatch[2], 10);
    if (points <= 0) continue;
    const reason = PHRASE_EXPLANATIONS[phrase.toLowerCase()];
    bullets.push(reason ? `Uses the phrase "${phrase}" — ${reason}.` : `Uses the phrase "${phrase}", which raises risk.`);
  }
  return bullets.slice(0, 6);
}
