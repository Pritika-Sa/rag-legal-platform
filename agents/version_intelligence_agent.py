import re
import difflib
from pydantic import BaseModel, Field
from agents.rule_engine import extract_obligations, fired_modifiers

NO_CHANGE = "No material change."
COMPLIANCE_WORDS = ["comply", "compliance", "regulation", "statute", "sanction"]
_JURISDICTION_RE = re.compile(r'state of ([a-z ]+)|governing law', re.IGNORECASE)


class VersionIntelligenceResult(BaseModel):
    clause_changes: str = Field(description="Summary of the core legal language changes made")
    risk_changes: str = Field(description="Analysis of how these changes impact legal and financial risk")
    compliance_changes: str = Field(description="Impact on regulatory or compliance requirements")
    jurisdiction_changes: str = Field(description="Shifts in governing law or venue from the edit")
    obligation_changes: str = Field(description="Changes to duties, timelines, or deliverables")


def analyze_version_diff(old_text: str, new_text: str) -> VersionIntelligenceResult:
    """Rule-based version diff analysis (Stage 2, no LLM) via difflib and
    the same escalator/mitigator vocabulary used for risk scoring. This
    agent is invoked unconditionally for every modified-clause version
    every time pages/version_history.py reruns, so keeping it LLM-free
    matters even more than a typical Stage-2 agent."""
    if old_text.strip() == new_text.strip():
        return VersionIntelligenceResult(
            clause_changes=NO_CHANGE, risk_changes=NO_CHANGE, compliance_changes=NO_CHANGE,
            jurisdiction_changes=NO_CHANGE, obligation_changes=NO_CHANGE,
        )

    diff_lines = list(difflib.unified_diff(
        old_text.splitlines(), new_text.splitlines(), fromfile="previous", tofile="current", lineterm="",
    ))
    clause_changes = "\n".join(diff_lines[:20]) if diff_lines else NO_CHANGE

    old_esc, old_mit = fired_modifiers(old_text)
    new_esc, new_mit = fired_modifiers(new_text)
    added_esc, removed_esc = set(new_esc) - set(old_esc), set(old_esc) - set(new_esc)
    added_mit, removed_mit = set(new_mit) - set(old_mit), set(old_mit) - set(new_mit)

    if added_esc or removed_mit:
        risk_changes = (
            f"Risk appears to have increased: added escalating language {sorted(added_esc)} "
            f"and/or removed mitigating language {sorted(removed_mit)}."
        )
    elif added_mit or removed_esc:
        risk_changes = (
            f"Risk appears to have decreased: added mitigating language {sorted(added_mit)} "
            f"and/or removed escalating language {sorted(removed_esc)}."
        )
    else:
        risk_changes = NO_CHANGE

    old_compliance_hits = sum(1 for w in COMPLIANCE_WORDS if w in old_text.lower())
    new_compliance_hits = sum(1 for w in COMPLIANCE_WORDS if w in new_text.lower())
    compliance_changes = (
        f"Compliance-related term frequency changed from {old_compliance_hits} to {new_compliance_hits} mentions."
        if new_compliance_hits != old_compliance_hits else NO_CHANGE
    )

    old_jur = set(m for m in _JURISDICTION_RE.findall(old_text.lower()) if m)
    new_jur = set(m for m in _JURISDICTION_RE.findall(new_text.lower()) if m)
    jurisdiction_changes = (
        f"Jurisdiction references changed from {sorted(old_jur)} to {sorted(new_jur)}."
        if old_jur != new_jur else NO_CHANGE
    )

    old_obl, new_obl = extract_obligations(old_text), extract_obligations(new_text)
    if len(old_obl) != len(new_obl):
        obligation_changes = f"Number of detected obligation statements changed from {len(old_obl)} to {len(new_obl)}."
    elif old_obl != new_obl:
        obligation_changes = "Obligation phrasing changed without altering the count of obligations detected."
    else:
        obligation_changes = NO_CHANGE

    return VersionIntelligenceResult(
        clause_changes=clause_changes,
        risk_changes=risk_changes,
        compliance_changes=compliance_changes,
        jurisdiction_changes=jurisdiction_changes,
        obligation_changes=obligation_changes,
    )
