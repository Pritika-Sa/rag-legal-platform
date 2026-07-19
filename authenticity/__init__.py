# Authenticity Verification Engine — 7-factor, entropy-weighted replacement
# for agents/authenticity_agent.py's old fixed-deduction scorer. See the
# "Authenticity Verification Engine" design proposal for the full
# architecture; this package implements it one factor at a time:
#
#   Stage 0 (document type + confidence) -> services/document_classifier.py
#                                            ::classify_document_type_ranked
#   Factor 1 (structure validation)       -> authenticity/structure.py
#   Factor 2 (clause completeness)        -> not yet built
#   Factor 3 (cross-field consistency)    -> not yet built
#   Factor 4 (entity verification)        -> not yet built
#   Factor 5 (digital verification)       -> not yet built
#   Factor 6 (metadata validation)        -> not yet built
#   Factor 7 (semantic consistency)       -> not yet built
#   Fusion (Document Authenticity Index)  -> not yet built
#
# Deliberately not wired into agents/authenticity_agent.py or
# agents/orchestrator.py until every factor exists and is tested — the
# live pipeline keeps using the current (flawed but working) authenticity
# checker until this package is a complete, verified replacement, the same
# staging discipline used for risk_engine/ before it replaced
# agents/rule_engine.score_risk_points().
