# Authenticity Verification Engine — 7-factor, entropy-weighted replacement
# for agents/authenticity_agent.py's old fixed-deduction scorer. See the
# "Authenticity Verification Engine" design proposal for the full
# architecture; this package implements it one factor at a time:
#
#   Stage 0 (document type + confidence) -> services/document_classifier.py
#                                            ::classify_document_type_ranked
#   Factor 1 (structure validation)       -> authenticity/structure.py
#   Factor 2 (clause completeness)        -> authenticity/clauses.py
#   Factor 3 (cross-field consistency)    -> authenticity/cross_field.py
#   Factor 4 (entity verification)        -> authenticity/entities.py
#   Factor 5 (digital verification)       -> authenticity/digital.py
#   Factor 6 (metadata validation)        -> authenticity/metadata.py
#   Factor 7 (semantic consistency)       -> authenticity/semantic.py
#   Fusion (Document Authenticity Index)  -> authenticity/dai.py
#
# All 7 factors + fusion are built and tested. Deliberately not yet wired
# into agents/authenticity_agent.py or agents/orchestrator.py — the live
# pipeline keeps using the current (flawed but working) deduction-based
# authenticity checker until this package has been wired in and verified
# end-to-end against the live pipeline, the same staging discipline used
# for risk_engine/ before it replaced agents/rule_engine.score_risk_points().
