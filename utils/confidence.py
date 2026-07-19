"""Shared confidence-scoring primitives used across Stage-2 rule/NLP
extractors — kept in utils/, below both agents/ and services/ in the
dependency graph, so either layer can import it without creating a
services -> agents (or agents -> services) coupling in either direction.
"""


def evidence_confidence(count: int) -> float:
    """count/(count+1) — the standard Laplace/add-one smoothing curve. One
    independent piece of evidence alone gives 0.5 (an honest baseline for
    a single, uncorroborated signal); each additional independent
    corroborating signal pushes it up (2 -> 0.67, 3 -> 0.75, ...),
    asymptotically toward but never reaching 1.0.

    Originally written for agents/feature_extraction_agent.py's per-feature
    extraction confidence (obligation/entity/legal-action detection);
    reused as-is by services/document_classifier.py's document-type
    classification confidence — same underlying question ("how much
    independent evidence backs this call"), same answer, not a second
    formula invented to ask it twice.
    """
    return count / (count + 1.0)
