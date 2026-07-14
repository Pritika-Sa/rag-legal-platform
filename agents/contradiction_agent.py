import re
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from agents.rule_engine import (
    extract_clause_number,
    extract_dates,
    extract_durations,
    extract_money,
    extract_obligations,
    normalize_clause_title,
)
from services.semantic_similarity import cosine_similarity_matrix, embed_texts

TEMPORAL_KEYWORDS = ["effective date", "notice period", "cure period", "term of this agreement", "renewal"]
PAYMENT_KEYWORDS = ["late fee", "interest", "penalty", "due within", "payment terms"]
JURISDICTION_KEYWORDS = ["governing law", "governed by", "jurisdiction", "venue", "courts of", "laws of", "state of"]

MAX_CONTRADICTIONS = 20

SEVERITY_RANK = {"High": 3, "Medium": 2, "Low": 1, "None": 0}

# Minimum cosine similarity between two clauses' embeddings for them to be
# considered "plausibly about the same subject" and worth an LLM contradiction
# check. Deliberately generous (recall over precision) since the LLM's own
# "be conservative" instruction is the real precision gate downstream — a
# pair that passes this floor but isn't a real contradiction just costs one
# extra (cheap, single-clause-pair) LLM call, not a wrong answer shown to the
# user.
SEMANTIC_SIMILARITY_FLOOR = 0.35

# A "clause title" shared by more than this many clauses is almost certainly
# not a genuine repeated heading — section_name is sometimes populated from
# the detected clause TYPE rather than the document's real heading text (see
# agents/orchestrator.py), so e.g. every clause in an NDA getting classified
# as "Confidentiality" would otherwise look like a document with a dozen+
# duplicated clauses. Real accidental clause duplication is essentially
# always 2, occasionally 3, instances — never a dozen — so title-based
# duplicate grouping is skipped above this size rather than flagging every
# pairwise combination as a false "duplicate."
MAX_TITLE_GROUP_SIZE = 4

# Terms whose numeric value is expected to be a single, consistent figure
# across a document — if two clauses each attach a different number to the
# same label ("Penalty = 2%" vs "Penalty = 10%"), that's a contradiction
# regardless of clause classification or wording similarity.
_LABELED_NUMBER_RE = re.compile(
    r"\b(penalty|late fee|interest(?:\s+rate)?|security deposit|deposit|discount|"
    r"commission|royalty|rent|liability cap|cap on liability|notice period|"
    r"cure period|grace period|annual fee|service fee|subscription fee|"
    r"management fee|processing fee)\b"
    r"[^.\n%$]{0,25}?"
    r"(\d+(?:\.\d+)?\s?%|(?:USD|US\$|\$|₹|INR|Rs\.?|€|£)\s?[\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)


class ContradictionItem(BaseModel):
    """One issue-level finding — already consolidated across every clause
    involved, never a single clause-pair. See find_contradictions/_consolidate."""
    contradiction_type: str = Field(
        description="Type: Duplicate Clause, Numeric Conflict, Contradictory Dates, Conflicting Durations, "
                    "Payment Conflict, Conflicting Jurisdiction, Opposite Statements, Conflicting Obligations, "
                    "or Semantic Contradiction."
    )
    severity: str = Field(description="Severity: High, Medium, or Low — the highest severity among the merged findings")
    affected_clauses: List[str] = Field(description="Section names of every clause involved in this issue")
    clause_ids: List[int] = Field(description="Database IDs of every clause involved in this issue")
    clause_values: Dict[str, str] = Field(
        default_factory=dict,
        description="clause_id (as string) -> the specific conflicting value that clause states, "
                    "for issue types with a natural single value (numeric/date/duration/money/jurisdiction). "
                    "Empty for types without one (e.g. Duplicate Clause, Opposite Statements).",
    )
    explanation: str = Field(description="One consolidated explanation covering every clause in this issue")
    resolution: str = Field(description="One suggested resolution covering the whole issue")


class SemanticContradictionCheck(BaseModel):
    is_contradiction: bool = Field(description="True only if the two clauses state genuinely incompatible requirements")
    contradiction_type: str = Field(description="Short label for the type of conflict, e.g. 'Conflicting Obligations'")
    severity: str = Field(description="High, Medium, or Low")
    explanation: str = Field(description="One or two plain-English sentences on why they conflict")
    resolution: str = Field(description="A concrete suggested fix")


def _labeled_numbers(text: str) -> Dict[str, set]:
    out: Dict[str, set] = {}
    for label, value in _LABELED_NUMBER_RE.findall(text):
        out.setdefault(label.lower().strip(), set()).add(value.strip())
    return out


def _enrich(clause: Dict[str, Any]) -> Dict[str, Any]:
    text = clause.get("text_content", "") or ""
    text_lower = text.lower()
    section_name = clause.get("section_name") or "Clause"
    return {
        "id": clause.get("id"),
        "section_name": section_name,
        "classification": clause.get("classification", "General"),
        "text": text,
        "text_lower": text_lower,
        "clause_number": extract_clause_number(section_name, text),
        "title_key": normalize_clause_title(section_name),
        "dates": extract_dates(text),
        "durations": extract_durations(text),
        "money": extract_money(text),
        "obligations": extract_obligations(text),
        "labeled_numbers": _labeled_numbers(text),
    }


# ── Step 1 + 2: group by clause number/title, compare duplicates ───────────

def _detect_duplicates(enriched: List[Dict[str, Any]], add) -> None:
    by_number = defaultdict(list)
    by_title = defaultdict(list)
    for c in enriched:
        if c["clause_number"]:
            by_number[c["clause_number"]].append(c)
        if c["title_key"]:
            by_title[c["title_key"]].append(c)

    def _compare_group(group, label_kind, label_value):
        topic = f"duplicate:{label_kind}:{label_value}"
        for a, b in combinations(group, 2):
            # Numeric/date/duration diffs are checked *before* any similarity
            # gate — a duplicated clause with just one figure changed (e.g.
            # "penalty of 2%" vs "penalty of 10%") is textually very similar
            # but exactly the contradiction being looked for, so it must
            # never be filtered out as a "near-identical, ignore" repeat.
            detail = []
            if a["money"] and b["money"] and set(a["money"]) != set(b["money"]):
                detail.append(f"monetary/numeric values differ ({sorted(a['money'])} vs {sorted(b['money'])})")
            if a["dates"] and b["dates"] and set(a["dates"]) != set(b["dates"]):
                detail.append(f"dates differ ({sorted(a['dates'])} vs {sorted(b['dates'])})")
            if a["durations"] and b["durations"] and set(a["durations"]) != set(b["durations"]):
                detail.append(f"durations differ ({sorted(a['durations'])} vs {sorted(b['durations'])})")

            if detail:
                add(
                    "Duplicate Clause", "High", a, b,
                    f"Both '{a['section_name']}' and '{b['section_name']}' share the same {label_kind} "
                    f"('{label_value}') but {'; '.join(detail)}.",
                    "Merge into a single clause, or clearly state which version supersedes the other.",
                    topic=topic,
                )
                continue

            ratio = SequenceMatcher(None, a["text_lower"], b["text_lower"]).ratio()
            if ratio >= 0.97:
                continue  # essentially character-identical repeat — not a real conflict

            add(
                "Duplicate Clause", "Medium", a, b,
                f"Both '{a['section_name']}' and '{b['section_name']}' share the same {label_kind} "
                f"('{label_value}') but their wording diverges despite sharing the same clause identity.",
                "Merge into a single clause, or clearly state which version supersedes the other.",
                topic=topic,
            )

    for number, group in by_number.items():
        if len(group) > 1:
            _compare_group(group, "clause number", number)
    for title, group in by_title.items():
        if 1 < len(group) <= MAX_TITLE_GROUP_SIZE:
            _compare_group(group, "clause title", title)


# ── Step 3: numeric mismatches via regex (label-anchored, classification-agnostic) ─

def _detect_numeric_conflicts(enriched: List[Dict[str, Any]], add) -> None:
    for a, b in combinations(enriched, 2):
        for label, values_a in a["labeled_numbers"].items():
            values_b = b["labeled_numbers"].get(label)
            if values_b and values_a != values_b:
                add(
                    "Numeric Conflict", "High", a, b,
                    f"'{a['section_name']}' states {label} = {', '.join(sorted(values_a))} while "
                    f"'{b['section_name']}' states {label} = {', '.join(sorted(values_b))} for the same term.",
                    f"Confirm the correct {label} value across the document and remove the conflicting figure.",
                    topic=f"numeric:{label}",
                    value_a=", ".join(sorted(values_a)), value_b=", ".join(sorted(values_b)),
                )


# ── Step 4a: dates / durations, payment figures, jurisdiction ──────────────

def _detect_temporal_conflicts(enriched: List[Dict[str, Any]], add) -> None:
    for a, b in combinations(enriched, 2):
        if not (any(kw in a["text_lower"] for kw in TEMPORAL_KEYWORDS) and any(kw in b["text_lower"] for kw in TEMPORAL_KEYWORDS)):
            continue

        dates_a, dates_b = set(a["dates"]), set(b["dates"])
        if dates_a and dates_b and not (dates_a & dates_b):
            add(
                "Contradictory Dates", "Medium", a, b,
                f"'{a['section_name']}' references date(s) {sorted(dates_a)} while "
                f"'{b['section_name']}' references different date(s) {sorted(dates_b)} "
                f"for related time-sensitive terms.",
                "Align the referenced dates or clarify which clause governs.",
                topic="temporal:dates",
                value_a=", ".join(sorted(dates_a)), value_b=", ".join(sorted(dates_b)),
            )

        durations_a, durations_b = set(a["durations"]), set(b["durations"])
        if durations_a and durations_b and durations_a != durations_b:
            add(
                "Conflicting Durations", "Medium", a, b,
                f"'{a['section_name']}' specifies duration(s) {sorted(durations_a)} while "
                f"'{b['section_name']}' specifies {sorted(durations_b)} for related obligations.",
                "Reconcile the durations referenced in both clauses.",
                topic="temporal:durations",
                value_a=", ".join(f"{n} {u}" for n, u in sorted(durations_a)),
                value_b=", ".join(f"{n} {u}" for n, u in sorted(durations_b)),
            )


def _detect_payment_conflicts(enriched: List[Dict[str, Any]], add) -> None:
    # No classification-equality requirement: a payment clause that the rule
    # engine mis-tagged as something else (e.g. "General") must still be
    # comparable — the payment-keyword gate below is what actually scopes
    # this check to payment-relevant language, not the (unreliable) label.
    for a, b in combinations(enriched, 2):
        if not (any(kw in a["text_lower"] for kw in PAYMENT_KEYWORDS) and any(kw in b["text_lower"] for kw in PAYMENT_KEYWORDS)):
            continue
        money_a, money_b = set(a["money"]), set(b["money"])
        if money_a and money_b and money_a != money_b:
            add(
                "Payment Conflict", "High", a, b,
                f"'{a['section_name']}' cites payment figures {sorted(money_a)} while "
                f"'{b['section_name']}' cites {sorted(money_b)}, which may conflict.",
                "Confirm which payment terms are authoritative and remove the conflicting figure.",
                topic="payment",
                value_a=", ".join(sorted(money_a)), value_b=", ".join(sorted(money_b)),
            )


def _detect_jurisdiction_conflicts(enriched: List[Dict[str, Any]], add) -> None:
    candidates = [c for c in enriched if any(kw in c["text_lower"] for kw in JURISDICTION_KEYWORDS)]
    for a, b in combinations(candidates, 2):
        states_a = {s.strip() for s in re.findall(r"state of ([a-z]+(?:\s[a-z]+){0,2})", a["text_lower"])}
        states_b = {s.strip() for s in re.findall(r"state of ([a-z]+(?:\s[a-z]+){0,2})", b["text_lower"])}
        if states_a and states_b and states_a != states_b:
            add(
                "Conflicting Jurisdiction", "High", a, b,
                f"'{a['section_name']}' designates {sorted(states_a)} as governing jurisdiction "
                f"while '{b['section_name']}' designates {sorted(states_b)}.",
                "Consolidate into a single governing law/jurisdiction clause.",
                topic="jurisdiction",
                value_a=", ".join(sorted(states_a)), value_b=", ".join(sorted(states_b)),
            )


# ── Step 4b: party obligations — opposite statements & conflicting figures ─

def _detect_obligation_conflicts(enriched: List[Dict[str, Any]], add) -> None:
    for a, b in combinations(enriched, 2):
        for s1, r1, t1 in a["obligations"]:
            for s2, r2, t2 in b["obligations"]:
                if SequenceMatcher(None, s1.lower(), s2.lower()).ratio() < 0.6:
                    continue  # not the same party/subject

                target_ratio = SequenceMatcher(None, t1.lower(), t2.lower()).ratio()
                negated_1 = bool(re.search(r"\bnot\b", r1.lower()))
                negated_2 = bool(re.search(r"\bnot\b", r2.lower()))

                if target_ratio >= 0.55 and negated_1 != negated_2:
                    add(
                        "Opposite Statements", "High", a, b,
                        f"'{a['section_name']}' states \"{s1} {r1} {t1}\" while '{b['section_name']}' "
                        f"states \"{s2} {r2} {t2}\" — one requires/permits the action and the other "
                        f"prohibits it.",
                        "Clarify which obligation applies and remove the conflicting statement.",
                        topic="obligation:opposite",
                    )
                    continue

                if negated_1 == negated_2 and target_ratio > 0.4:
                    money_1, money_2 = set(extract_money(t1)), set(extract_money(t2))
                    dur_1, dur_2 = set(extract_durations(t1)), set(extract_durations(t2))
                    if money_1 and money_2 and money_1 != money_2:
                        add(
                            "Conflicting Obligations", "Medium", a, b,
                            f"'{a['section_name']}' requires \"{s1} {r1} {t1}\" while '{b['section_name']}' "
                            f"requires \"{s2} {r2} {t2}\" — the amounts referenced differ.",
                            "Confirm which figure is correct and align both clauses.",
                            topic="obligation:amount",
                            value_a=", ".join(sorted(money_1)), value_b=", ".join(sorted(money_2)),
                        )
                    elif dur_1 and dur_2 and dur_1 != dur_2:
                        add(
                            "Conflicting Obligations", "Medium", a, b,
                            f"'{a['section_name']}' requires \"{s1} {r1} {t1}\" while '{b['section_name']}' "
                            f"requires \"{s2} {r2} {t2}\" — the timeframes referenced differ.",
                            "Confirm which timeframe is correct and align both clauses.",
                            topic="obligation:duration",
                            value_a=", ".join(f"{n} {u}" for n, u in sorted(dur_1)),
                            value_b=", ".join(f"{n} {u}" for n, u in sorted(dur_2)),
                        )


# ── Step 5: LLM semantic pass, restricted to candidate pairs the rules ─────
# above didn't already resolve — never the full document, and never a
# replacement for the deterministic checks.

def _embedding_candidate_pairs(
    enriched: List[Dict[str, Any]], flagged_pairs: set, limit: int
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Ranks every not-yet-flagged clause pair by embedding (meaning)
    similarity and returns the top `limit`. Deliberately does NOT require
    matching classification — clause classification is itself an imperfect
    rule-based guess (see rule_engine.detect_clause_type's confidence score),
    so gating semantic comparison behind it silently hides real
    contradictions whenever either clause was mistagged. A generous
    SEMANTIC_SIMILARITY_FLOOR keeps recall high; precision is enforced later
    by the LLM's own "be conservative" instruction, not here."""
    n = len(enriched)
    if n < 2:
        return []

    vectors = embed_texts([c["text"] for c in enriched])
    similarity = cosine_similarity_matrix(vectors, vectors)

    scored = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = enriched[i], enriched[j]
            if frozenset([a["id"], b["id"]]) in flagged_pairs:
                continue
            score = float(similarity[i, j])
            if score >= SEMANTIC_SIMILARITY_FLOOR:
                scored.append((score, a, b))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(a, b) for _, a, b in scored[:limit]]


def _llm_semantic_check(clause_a: Dict[str, Any], clause_b: Dict[str, Any]) -> Optional[SemanticContradictionCheck]:
    from utils.llm_client import invoke_llm_structured

    system_prompt = (
        "You are a contract-review assistant. Decide whether two clauses from the same legal "
        "document genuinely contradict each other — i.e. they impose incompatible requirements — "
        "as opposed to simply covering different topics or complementing one another. Be "
        "conservative: if in doubt, say it is not a contradiction."
    )
    user_prompt = (
        f"Clause A ('{clause_a['section_name']}'):\n{clause_a['text'][:800]}\n\n"
        f"Clause B ('{clause_b['section_name']}'):\n{clause_b['text'][:800]}\n\n"
        "Do these two clauses contradict each other?"
    )
    try:
        return invoke_llm_structured(system_prompt, user_prompt, SemanticContradictionCheck, temperature=0.0)
    except Exception:
        return None


# ── Step 6: consolidate pairwise findings into issue-level groups ──────────

def _consolidate(raw_findings: List[Dict[str, Any]], id_to_name: Dict[int, str]) -> List[ContradictionItem]:
    """Merges pairwise findings sharing a (contradiction_type, topic) into one
    issue per connected component of clauses — i.e. if clause A conflicts
    with B and also with C on the same topic, A/B/C become ONE consolidated
    finding covering all three, even though B and C were never directly
    compared to each other. Findings with different topics (e.g. a "late fee"
    numeric conflict vs an "interest rate" one) never merge, even if they
    happen to share a clause, since they're substantively different issues."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for f in raw_findings:
        groups[(f["contradiction_type"], f["topic"])].append(f)

    consolidated: List[ContradictionItem] = []

    for (contradiction_type, _topic), findings in groups.items():
        parent: Dict[int, int] = {}

        def find(x: int) -> int:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        for f in findings:
            union(f["a_id"], f["b_id"])

        clusters: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for f in findings:
            clusters[find(f["a_id"])].append(f)

        for cluster_findings in clusters.values():
            clause_ids = sorted({cid for f in cluster_findings for cid in (f["a_id"], f["b_id"])})
            affected_clauses = [id_to_name.get(cid, f"Clause {cid}") for cid in clause_ids]

            clause_values: Dict[str, str] = {}
            for f in cluster_findings:
                if f["value_a"]:
                    clause_values[str(f["a_id"])] = f["value_a"]
                if f["value_b"]:
                    clause_values[str(f["b_id"])] = f["value_b"]

            severity = max((f["severity"] for f in cluster_findings), key=lambda s: SEVERITY_RANK.get(s, 0))

            if clause_values:
                value_lines = [
                    f"'{id_to_name.get(int(cid), cid)}' → {value}"
                    for cid, value in clause_values.items()
                ]
                explanation = (
                    f"{len(clause_ids)} clauses state conflicting values for this term: "
                    + "; ".join(value_lines) + "."
                )
            else:
                distinct_explanations = []
                for f in cluster_findings:
                    if f["explanation"] not in distinct_explanations:
                        distinct_explanations.append(f["explanation"])
                explanation = (
                    distinct_explanations[0] if len(distinct_explanations) == 1
                    else f"{len(clause_ids)} clauses are involved in this conflict: " + " | ".join(distinct_explanations)
                )

            consolidated.append(ContradictionItem(
                contradiction_type=contradiction_type,
                severity=severity,
                affected_clauses=affected_clauses,
                clause_ids=clause_ids,
                clause_values=clause_values,
                explanation=explanation,
                resolution=cluster_findings[0]["resolution"],
            ))

    consolidated.sort(key=lambda item: SEVERITY_RANK.get(item.severity, 0), reverse=True)
    return consolidated


def find_contradictions(
    clauses: List[Dict[str, Any]], use_llm: bool = False, max_llm_pairs: int = 12
) -> List[ContradictionItem]:
    """Hybrid contradiction detection pipeline (Stage 2 rule-based, with an
    optional Stage 3 LLM pass), consolidated to issue level before returning:

      1. Group clauses by clause number/title.
      2. Compare duplicate clauses for diverging content.
      3. Detect numeric mismatches via label-anchored regex (e.g. "Penalty
         2%" vs "Penalty 10%"), independent of clause classification.
      4. Detect entity mismatches: dates, durations, monetary values,
         jurisdictions, and party obligations (including plain negation —
         "shall" vs "shall not") — none of these require matching
         classification either, only the presence of the relevant language.
      5. Only if `use_llm=True`: embed every clause and rank all
         not-yet-flagged pairs by meaning similarity (see
         _embedding_candidate_pairs) — no classification-match requirement —
         then run an LLM semantic check on the top `max_llm_pairs`. Never the
         full document, and never a replacement for steps 1-4.
      6. Consolidate: every pairwise finding above is merged with any other
         finding of the same (contradiction_type, topic) that shares a
         clause, transitively — so one clause conflicting with several others
         on the same point becomes one issue-level result, not N pairwise
         rows (see _consolidate).

    Document clause counts are small (tens, not thousands), so both the O(n^2)
    pairwise regex scan and the one-time embedding pass are cheap.
    """
    if len(clauses) < 2:
        return []

    enriched = [_enrich(c) for c in clauses]
    id_to_name = {c["id"]: c["section_name"] for c in enriched}
    raw_findings: List[Dict[str, Any]] = []
    seen_keys = set()
    flagged_pairs = set()

    def _add(contradiction_type, severity, a, b, explanation, resolution,
             topic=None, value_a=None, value_b=None):
        key = (contradiction_type, frozenset([a["id"], b["id"]]))
        if key in seen_keys:
            return
        seen_keys.add(key)
        flagged_pairs.add(frozenset([a["id"], b["id"]]))
        raw_findings.append({
            "contradiction_type": contradiction_type,
            "severity": severity,
            "topic": topic or contradiction_type,
            "a_id": a["id"], "b_id": b["id"],
            "explanation": explanation,
            "resolution": resolution,
            "value_a": value_a, "value_b": value_b,
        })

    _detect_duplicates(enriched, _add)
    _detect_numeric_conflicts(enriched, _add)
    _detect_temporal_conflicts(enriched, _add)
    _detect_payment_conflicts(enriched, _add)
    _detect_jurisdiction_conflicts(enriched, _add)
    _detect_obligation_conflicts(enriched, _add)

    if use_llm:
        for clause_a, clause_b in _embedding_candidate_pairs(enriched, flagged_pairs, max_llm_pairs):
            result = _llm_semantic_check(clause_a, clause_b)
            if result and result.is_contradiction:
                _add(
                    result.contradiction_type or "Semantic Contradiction",
                    result.severity or "Medium",
                    clause_a, clause_b,
                    result.explanation, result.resolution,
                    topic=result.contradiction_type or "Semantic Contradiction",
                )

    return _consolidate(raw_findings, id_to_name)[:MAX_CONTRADICTIONS]
