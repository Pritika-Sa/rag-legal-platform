from pydantic import BaseModel, Field
from typing import List, Dict, Any
from services.prompt_builder import build_summary_prompt
from utils.llm_client import invoke_llm_structured


class AuditResult(BaseModel):
    audit_score: int = Field(description="Overall Audit Score 0-100 representing quality, clarity, and safety.")
    trust_score: int = Field(description="Trust Score evaluating reliability of AI extraction and risk assignments (0-100).")
    confidence_score: int = Field(description="Confidence Score in the audit results (0-100).")
    audit_summary: str = Field(description="Executive summary of the audit findings.")
    hallucination_risks: str = Field(description="Evaluation of potential hallucination or over-reach in risk analysis.")
    citation_accuracy: str = Field(description="Assessment of whether clauses are properly structured and referenceable.")


def perform_macro_audit(doc_name: str, clauses: List[Dict[str, Any]], contradictions: List[Dict[str, Any]]) -> AuditResult:
    """Agent 16: Audit Agent — final macro-evaluator."""
    high_risks = sum(1 for c in clauses if c.get('risk_level') == 'High')
    med_risks = sum(1 for c in clauses if c.get('risk_level') == 'Medium')

    stats = {
        "Total Clauses": len(clauses),
        "High Risks, Medium Risks": f"{high_risks}, {med_risks}",
        "Contradictions Found": len(contradictions),
    }
    sample_lines = [
        f"{c['section_name']}: {c['text_content'][:200]}..."
        for c in [c for c in clauses if c.get('risk_level') == 'High'][:3]
    ]
    context = build_summary_prompt(doc_name, stats, sample_lines)

    system_instruction = (
        "You are the Master Audit Agent. Review the summary of document parsing, "
        "risk analysis, and contradictions. Evaluate the overall quality of the contract and "
        "the reliability of the AI's risk assignments. Generate Audit, Trust, and Confidence scores. "
        "Highlight any hallucination risks where the AI might have over-classified a risk."
    )
    prompt = f"Audit this document profile:\n\n{context}"

    try:
        return invoke_llm_structured(system_instruction, prompt, AuditResult)
    except Exception as e:
        print(f"Error in audit agent: {e}")
        return AuditResult(
            audit_score=0, trust_score=0, confidence_score=0,
            audit_summary="Audit failed to execute.",
            hallucination_risks="Unknown", citation_accuracy="Unknown",
        )
