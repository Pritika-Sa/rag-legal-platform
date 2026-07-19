"""RiskEngine interface — the seam that lets a future supervised model
replace HybridExplainableRiskEngine without touching feature extraction,
the dashboard, or the explainability contract.

Scoring is defined at the *document* level, not per clause: entropy-weighted
dimension fusion (see fusion.entropy_weights) is inherently a statistic over
a batch of clauses, so there is no meaningful per-clause `score(clause)`
call — a lone clause has no distribution to derive weights from. Any future
implementation (e.g. a fine-tuned classifier) must honor the same batch
signature and must still return per-dimension scores + evidence in
DocumentRiskAssessment, not a bare number, to keep every downstream
consumer (dashboard, explainability UI) working unchanged.
"""

from abc import ABC, abstractmethod
from typing import List

from risk_engine.schemas import ClauseInput, DocumentRiskAssessment


class RiskEngine(ABC):
    @abstractmethod
    def score_document(self, clauses: List[ClauseInput]) -> DocumentRiskAssessment:
        ...
