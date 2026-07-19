"""Legal Feature Extraction Agent (Stage 2, no LLM) — produces a
risk_engine.schemas.LegalFeatureVector per clause via NER and dependency
parsing (spaCy), replacing regex/keyword matching as the *primary* signal
feeding the Hybrid Explainable Risk Engine. This is the module the risk
engine design doc describes as agents/feature_extraction_agent.py: it never
assigns a risk weight itself — it only detects and structures what is
present in a clause. All risk-magnitude decisions happen downstream, in
risk_engine/ (corpus-relative normalization + entropy-weighted fusion).

Two categories of extraction stay deterministic/regex-based rather than
NER-based, deliberately:
  - Dates, durations, and monetary figures (agents.rule_engine.extract_dates
    /extract_durations/extract_money) — these are already precise, cheap,
    and don't benefit from a learned model; spaCy's own DATE/MONEY entities
    are noisier on legal-formatted figures ("₹50,00,000", "Rs. 5 Lakh") than
    the existing hand-tuned regex, so the proven extractor is kept as the
    source of truth here.
  - Explicit cross-clause dependencies — resolved via the existing
    agents.dependency_agent (regex cross-reference + static domain table)
    rather than reimplemented, per extract_legal_features_batch below.

Known limitation, stated plainly rather than glossed over: `en_core_web_sm`
is a general-purpose English model, not a legal-domain one. Spot-checking it
against real clause text mislabels legal defined terms and jurisdictional
phrases as ORG instead of GPE/LAW reasonably often. Its dependency parser
(used for obligation/right/prohibition extraction) is far more reliable
than its NER on this kind of text, which is why entity/jurisdiction
extraction below leans on the existing proven regexes
(agents.knowledge_graph_agent.PARTY_RE / JURISDICTION_RE) as the primary
signal and spaCy NER as a secondary contributor, not the reverse. Swapping
FEATURE_EXTRACTION_MODEL to a legal-domain NER model later (see the design
doc's Embedding workflow tiering) needs no code change here.
"""

import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from agents.knowledge_graph_agent import JURISDICTION_RE, PARTY_RE
from agents.rule_engine import extract_dates, extract_durations, extract_money
from agents.rule_engine import extract_obligations as _regex_extract_obligations
from risk_engine.dimensions import COMPLIANCE_ACTION_TYPES, LEGAL_ACTION_TYPES
from risk_engine.schemas import (
    Deadline, Dependency, Entity, FinancialTerm, LegalAction, LegalFeatureVector, Obligation, Polarity,
)
from utils.confidence import evidence_confidence as _evidence_confidence

FEATURE_EXTRACTION_MODEL = os.getenv("FEATURE_EXTRACTION_MODEL", "en_core_web_sm")

_nlp_instance = None


def _get_nlp():
    """Lazy-loads and caches the spaCy pipeline singleton, matching the
    existing get_embeddings()/_get_reranker() pattern elsewhere in the
    repo — the model loads once per process, not once per clause."""
    global _nlp_instance
    if _nlp_instance is None:
        import spacy
        _nlp_instance = spacy.load(FEATURE_EXTRACTION_MODEL)
    return _nlp_instance


# _evidence_confidence (imported above as utils.confidence.evidence_confidence)
# replaced 4 hand-picked per-extractor-type constants here (0.85 for
# dependency parsing, 0.7 for spaCy NER, 0.9 for regex, 0.6 for the lexical
# action lookup) with one shared formula: every extraction confidence in
# this module is computed the same way, from how many independent
# detectors agree, not asserted reliability differences between methods
# with no evidence behind the specific numbers. This does not eliminate
# every judgment call — the *pairs* of signals treated as "independent
# corroboration" below are still a design choice — but it removes the
# per-type magic numbers themselves. Promoted to utils/confidence.py so
# services/document_classifier.py's document-type confidence can reuse the
# identical formula without services/ importing from agents/.

# ── Obligations / rights / prohibitions — dependency parse ─────────────────

STRONG_MODALS = {"shall", "must", "will"}
WEAK_MODALS = {"may", "might", "could", "should"}
# Closed grammatical set of English modal auxiliaries — see rule_engine's
# own "why this isn't keywords again" note in the design doc: this
# classifies polarity, it never assigns a point value.

_SUBJECT_AGREEMENT_RATIO = 0.5  # loose fuzzy-match threshold for "same subject", same style
                                # of threshold already used for subject matching in contradiction_agent.py


def _regex_corroborates_subject(subject: str, regex_hits: List[tuple]) -> bool:
    """True if agents.rule_engine's older, surface-pattern regex extractor
    (kept only as a corroboration signal now, not the primary extractor —
    see the module docstring) independently found an obligation with a
    similar subject in the same text. Obligations both methods agree on
    are, almost by construction, the unambiguous cases (a clear capitalized
    subject immediately followed by a modal) — exactly the cases a parse
    error is least likely; obligations only the dependency parser finds are
    the harder ones (pronouns, coordinated/elided subjects, lowercase
    phrasing) where a mis-parse is comparatively more likely."""
    return any(
        SequenceMatcher(None, subject.lower(), regex_subject.lower()).ratio() >= _SUBJECT_AGREEMENT_RATIO
        for regex_subject, _relation, _target in regex_hits
    )


def _polarity_for(modal_lemma: str, negated: bool) -> Polarity:
    if negated:
        return Polarity.PROHIBITION
    if modal_lemma in STRONG_MODALS:
        return Polarity.OBLIGATION
    return Polarity.RIGHT


def _find_subject(verb_token):
    """Direct nsubj/nsubjpass child of `verb_token`, or — for a coordinated
    verb whose subject was elided ('X shall A and shall not B and shall C')
    — the subject inherited from the verb it's conjoined to, found by
    walking up the conj chain. Without this, only the first conjunct in a
    coordinated clause gets a subject and every later one (often the
    negated one — see the module's obligation-extraction note) is silently
    dropped."""
    subject = next((c for c in verb_token.children if c.dep_ in ("nsubj", "nsubjpass")), None)
    if subject is not None:
        return subject
    if verb_token.dep_ == "conj":
        return _find_subject(verb_token.head)
    return None


def extract_obligations(doc) -> List[Obligation]:
    """Walks the dependency tree for every modal auxiliary (tag_ == 'MD'):
    the modal's head is the governing verb, _find_subject locates its
    (possibly inherited) subject, and a 'neg' child flips polarity to
    Prohibition. Replaces rule_engine._OBLIGATION_RE, which only matched a
    rigid '[Capitalized Subject] shall/must/will [rest of sentence]' surface
    pattern and missed subjects introduced earlier in a sentence, pronouns,
    or non-capitalized phrasing that a real parse tree handles natively.

    Coordinated clauses ('Party shall A and shall not B') get one Obligation
    per conjunct, each independently negatable — a single shared 'action
    text' spanning every conjunct would otherwise merge B's words (and its
    negation) into A's action, corrupting exactly the clause most likely to
    matter (the negated one)."""
    regex_hits = _regex_extract_obligations(doc.text)
    obligations: List[Obligation] = []
    seen_heads = set()
    for token in doc:
        if token.tag_ != "MD" or token.head.i in seen_heads:
            continue
        head = token.head
        seen_heads.add(head.i)

        subject_token = _find_subject(head)
        if subject_token is None:
            continue

        negated = any(c.dep_ == "neg" for c in head.children)
        conjunct_subtrees = set()
        for child in head.children:
            if child.dep_ == "conj":
                conjunct_subtrees.update(child.subtree)

        excluded = set(subject_token.subtree) | {token} | conjunct_subtrees
        action_tokens = sorted(
            (t for t in head.subtree if t not in excluded and t.dep_ not in ("neg", "cc")),
            key=lambda t: t.i,
        )
        while action_tokens and action_tokens[-1].is_punct:
            action_tokens.pop()
        action_text = " ".join(t.text for t in action_tokens).strip()
        if not action_text:
            continue

        subject_text = " ".join(t.text for t in subject_token.subtree)
        corroborated = _regex_corroborates_subject(subject_text, regex_hits)
        obligations.append(Obligation(
            subject=subject_text,
            modal=token.text,
            polarity=_polarity_for(token.lemma_.lower(), negated),
            action=action_text,
            confidence=_evidence_confidence(2 if corroborated else 1),
        ))
    return obligations


# ── Entities / jurisdiction — proven regex first, spaCy NER as backup ──────

def _spans_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def extract_entities(doc) -> List[Entity]:
    """Every entity's confidence is evidence-count-derived (see
    _evidence_confidence): spaCy NER and the PARTY_RE regex are two
    independent detectors for the same underlying thing (a named party),
    so an entity either method finds on its own gets the single-detector
    baseline, and one both methods agree on (overlapping character spans)
    gets the higher, corroborated value — replacing the old scheme, which
    asserted regex matches are inherently more trustworthy than the NER
    model (0.9 vs 0.7) with no evidence behind either specific number."""
    ner_ents = list(doc.ents)
    party_matches = list(PARTY_RE.finditer(doc.text))

    entities = []
    for ent in ner_ents:
        corroborated = any(_spans_overlap(ent.start_char, ent.end_char, m.start(), m.end()) for m in party_matches)
        entities.append(Entity(
            text=ent.text, entity_type=ent.label_,
            confidence=_evidence_confidence(2 if corroborated else 1),
        ))
    for m in party_matches:
        corroborated = any(_spans_overlap(m.start(), m.end(), ent.start_char, ent.end_char) for ent in ner_ents)
        entities.append(Entity(
            text=m.group(2), entity_type="PARTY",
            confidence=_evidence_confidence(2 if corroborated else 1),
        ))
    return entities


def extract_jurisdiction(text: str) -> Optional[str]:
    match = JURISDICTION_RE.search(text)
    return match.group(1).strip() if match else None


# ── Deadlines — reuses the proven date/duration regex, adds normalization ──

_DAYS_PER_UNIT = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30, "year": 365, "years": 365}


def extract_deadlines(text: str) -> List[Deadline]:
    deadlines = [Deadline(kind="date", value=d) for d in extract_dates(text)]
    for n, unit in extract_durations(text):
        deadlines.append(Deadline(
            kind="duration", value=f"{n} {unit}",
            normalized_days=float(n) * _DAYS_PER_UNIT.get(unit.lower(), 1),
        ))
    return deadlines


# ── Financial terms — reuses the proven money regex, adds parsing ──────────

_CURRENCY_PREFIXES = [("US$", "USD"), ("USD", "USD"), ("$", "USD"), ("₹", "INR"), ("INR", "INR"),
                      ("Rs.", "INR"), ("Rs", "INR"), ("€", "EUR"), ("£", "GBP")]
_SCALE_WORDS = {"thousand": 1_000, "lakh": 100_000, "crore": 10_000_000, "million": 1_000_000, "billion": 1_000_000_000}
CAP_WORDS = ("cap", "capped", "limited to", "maximum of", "not to exceed")
UNCAP_WORDS = ("uncapped", "unlimited", "without limit", "no limitation")


def _capped_flag(text_lower: str) -> Optional[bool]:
    if any(w in text_lower for w in UNCAP_WORDS):
        return False
    if any(w in text_lower for w in CAP_WORDS):
        return True
    return None


def _parse_money_string(raw: str) -> FinancialTerm:
    s = raw.strip()
    if s.endswith("%"):
        num_match = re.search(r"[\d,.]+", s)
        amount = float(num_match.group().replace(",", "")) if num_match else None
        return FinancialTerm(amount=amount, currency=None, is_percentage=True)

    currency = next((code for prefix, code in _CURRENCY_PREFIXES if s.startswith(prefix)), None)
    num_match = re.search(r"[\d,]+(?:\.\d+)?", s)
    amount = float(num_match.group().replace(",", "")) if num_match else None
    scale = next((mult for word, mult in _SCALE_WORDS.items() if word in s.lower()), 1)
    if amount is not None:
        amount *= scale
    return FinancialTerm(amount=amount, currency=currency, is_percentage=False)


def extract_financial_terms(text: str) -> List[FinancialTerm]:
    capped = _capped_flag(text.lower())
    terms = []
    for raw in extract_money(text):
        term = _parse_money_string(raw)
        term.is_capped = capped
        terms.append(term)
    return terms


# ── Legal actions — lexical placeholder classifier ──────────────────────────
# Stated explicitly: this is a cold-start lexical lookup, not a trained
# classifier. It exists to unblock the Legal/Compliance dimensions today;
# the design doc's "legal actions" row calls for a zero-shot or fine-tuned
# classifier as the eventual replacement — swapping it in only requires
# this function to keep returning LegalAction objects with action_type
# values drawn from risk_engine.dimensions.LEGAL_ACTION_TYPES /
# COMPLIANCE_ACTION_TYPES.

_ACTION_PHRASES = {"hold harmless": "indemnification", "limitation of liability": "limitation_of_liability"}
_ACTION_LEMMAS = {
    "terminate": "termination", "termination": "termination",
    "indemnify": "indemnification", "indemnification": "indemnification", "indemnity": "indemnification",
    "waive": "waiver", "waiver": "waiver",
    "assign": "assignment", "assignment": "assignment",
    "comply": "compliance", "compliance": "compliance", "compliant": "compliance",
    "sanction": "sanctions", "sanctions": "sanctions",
}

assert set(_ACTION_PHRASES.values()) | set(_ACTION_LEMMAS.values()) <= (LEGAL_ACTION_TYPES | COMPLIANCE_ACTION_TYPES), (
    "every ACTION_LEXICON value must be a member of risk_engine.dimensions' taxonomy contract"
)


def extract_legal_actions(doc) -> List[LegalAction]:
    """Confidence is evidence-count-derived (see _evidence_confidence): the
    phrase lexicon and the lemma lexicon are two independent detection
    routes to the same action_type (e.g. 'indemnification' is reachable via
    either the phrase "hold harmless" or the lemma "indemnify") — an
    action_type only one route finds gets the single-detector baseline; one
    both routes independently confirm gets the higher, corroborated value."""
    text_lower = doc.text.lower()
    lemmas = {t.lemma_.lower() for t in doc}

    evidence_count: Dict[str, int] = {}
    for phrase, action_type in _ACTION_PHRASES.items():
        if phrase in text_lower:
            evidence_count[action_type] = evidence_count.get(action_type, 0) + 1
    for lemma, action_type in _ACTION_LEMMAS.items():
        if lemma in lemmas:
            evidence_count[action_type] = evidence_count.get(action_type, 0) + 1

    return [
        LegalAction(action_type=action_type, confidence=_evidence_confidence(count))
        for action_type, count in sorted(evidence_count.items())
    ]


# ── Per-clause and batch entry points ───────────────────────────────────────

_LEADING_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)")


def _leading_number(section_name: str) -> Optional[str]:
    match = _LEADING_NUM_RE.match((section_name or "").strip())
    return match.group(1) if match else None


def extract_legal_features(clause_id: int, text: str) -> LegalFeatureVector:
    doc = _get_nlp()(text or "")
    return LegalFeatureVector(
        clause_id=clause_id,
        entities=extract_entities(doc),
        obligations=extract_obligations(doc),
        deadlines=extract_deadlines(text or ""),
        financial_terms=extract_financial_terms(text or ""),
        legal_actions=extract_legal_actions(doc),
        jurisdiction=extract_jurisdiction(text or ""),
        dependencies=[],  # filled in by extract_legal_features_batch below
    )


def extract_legal_features_batch(clauses: List[Dict[str, Any]]) -> List[LegalFeatureVector]:
    """`clauses` shaped like the orchestrator's db_clauses: each dict needs
    at least 'id' and 'text_content' (and whatever agents.dependency_agent
    itself requires — 'section_name', 'classification'). Explicit
    cross-clause dependencies are resolved via the existing
    agents.dependency_agent rather than reimplemented here (see module
    docstring).

    Every edge dependency_agent returns is already a resolved reference
    (it only creates one when the referenced number matches a real clause,
    dropping dangling references entirely — see extract_clause_dependencies)
    — that resolution is the first piece of evidence. The second, checked
    independently here: is the referenced clause number unique in this
    document? If more than one clause shares the same leading number, the
    resolution could have matched the wrong one, so it doesn't get the
    corroboration bonus (see _evidence_confidence)."""
    from agents.dependency_agent import extract_clause_dependencies

    feature_vectors = [extract_legal_features(c["id"], c.get("text_content", "")) for c in clauses]
    by_id = {fv.clause_id: fv for fv in feature_vectors}

    section_name_by_id = {c["id"]: c.get("section_name", "") for c in clauses}
    number_counts: Dict[str, int] = {}
    for section_name in section_name_by_id.values():
        num = _leading_number(section_name)
        if num:
            number_counts[num] = number_counts.get(num, 0) + 1

    for edge in extract_clause_dependencies(clauses):
        fv = by_id.get(edge.source_clause_id)
        if fv is None:
            continue
        target_number = _leading_number(section_name_by_id.get(edge.target_clause_id, ""))
        unambiguous = target_number is not None and number_counts.get(target_number, 0) == 1
        fv.dependencies.append(Dependency(
            target_clause_id=edge.target_clause_id, relation=edge.dependency_type,
            confidence=_evidence_confidence(2 if unambiguous else 1),
        ))
    return feature_vectors
