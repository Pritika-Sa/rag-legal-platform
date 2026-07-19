# Hybrid Explainable Risk Engine — weight-free replacement for
# agents/rule_engine.score_risk_points() / RISK_PHRASE_POINTS.
#
#   Data contracts               -> risk_engine/schemas.py
#   RiskEngine interface         -> risk_engine/base.py (swap seam for a
#                                    future supervised model)
#   Per-dimension F_d/E_d        -> risk_engine/dimensions.py
#   Dimension prototypes         -> risk_engine/prototypes.json
#                                    (natural-language descriptions —
#                                    replaces the deleted keyword-point
#                                    tables in rules/*.json)
#   Prototype embedding + lookup -> risk_engine/prototype_store.py
#   Entropy weighting + LRSI     -> risk_engine/fusion.py
#   Evidence + confidence        -> risk_engine/explain.py
#   Default RiskEngine impl      -> risk_engine/hybrid_engine.py

from risk_engine.base import RiskEngine
from risk_engine.hybrid_engine import HybridExplainableRiskEngine

__all__ = ["RiskEngine", "HybridExplainableRiskEngine"]
