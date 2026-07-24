import logging
from typing import Any, List

from pydantic import BaseModel, Field, field_validator, model_validator

from utils.llm_client import invoke_llm_structured

logger = logging.getLogger(__name__)


def _normalize_score(value: Any) -> Any:
    """Normalizes a score onto an integer 0-100 percentage scale, accepting
    either a 0-1 fraction (0.9 -> 90, 0.82 -> 82) or an already-percentage
    number (90 -> 90, 92.4 -> 92) or a "90%"-style string. Small instruct
    models are inconsistent about which scale they answer on; without this,
    a plain `int` field either fails validation on a fractional float or —
    worse — silently truncates it (int(0.9) == 0), which was the root cause
    of trust_score/hallucination_score both previously reading 0%."""
    if value is None:
        return value
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        try:
            value = float(stripped)
        except ValueError:
            return value  # not numeric -- let Pydantic raise its own clear type error
    if isinstance(value, (int, float)):
        if 0 <= value <= 1:
            value = value * 100
        return max(0, min(100, round(value)))
    return value


class HallucinationEvaluation(BaseModel):
    hallucination_score: int = Field(
        description="Integer percentage 0-100. 100 = completely hallucinated, 0 = fully grounded."
    )
    trust_score: int = Field(
        description="Integer percentage 0-100. Always derived as (100 - hallucination_score) for "
                    "internal consistency — see _enforce_consistency below."
    )
    confidence_score: int = Field(
        description="Integer percentage 0-100: how confident this evaluation itself is."
    )
    groundedness_analysis: str = Field(description="One or two sentences on whether the answer is strictly derived from context.")
    citation_quality: str = Field(description="A short rating, e.g. 'Excellent' / 'Good' / 'Fair' / 'Poor' — not a paragraph.")
    unsupported_statements: List[str] = Field(
        default_factory=list,
        description="Exact unsupported claims quoted from the answer (never comments about information the "
                    "answer merely omitted). Empty list if every claim in the answer is supported.",
    )

    @model_validator(mode="before")
    @classmethod
    def _log_raw_output(cls, data: Any) -> Any:
        logger.debug(f"[hallucination_agent] raw LLM output before normalization: {data!r}")
        return data

    @field_validator("hallucination_score", "trust_score", "confidence_score", mode="before")
    @classmethod
    def _normalize_percentage(cls, value: Any) -> Any:
        return _normalize_score(value)

    @field_validator("unsupported_statements", mode="before")
    @classmethod
    def _coerce_unsupported_statements(cls, value: Any) -> Any:
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @model_validator(mode="after")
    def _enforce_consistency(self) -> "HallucinationEvaluation":
        """Derives trust_score deterministically from hallucination_score
        instead of trusting the model's own arithmetic — the two are two
        views of the same judgment and must always complement each other
        (goal C). This is what directly fixes the reported bug where
        trust_score and hallucination_score both independently read 0%."""
        self.trust_score = 100 - self.hallucination_score
        logger.debug(f"[hallucination_agent] normalized HallucinationEvaluation: {self.model_dump()}")
        return self


def evaluate_hallucination(question: str, context: str, answer: str) -> HallucinationEvaluation:
    """Agent 14: Hallucination Detection Agent. Post-processing validation
    only, called after a QA answer has already been generated (see
    agents/qa_agent.py) — never involved in retrieval or generation itself.

    Raises on failure rather than swallowing the error into a fake "100%
    hallucinated" result: agents/qa_agent.py's _run_hallucination_check is
    the single place that decides the user-facing "Trust Score: Unknown /
    Hallucination Check: Failed" state, so a genuine LLM/parsing failure
    here must propagate to it rather than be misreported as an actual
    hallucination finding.
    """
    system_instruction = (
        "You are an expert Hallucination Detection Agent for a Legal AI system. "
        "Your ONLY job is to check whether the ANSWER's claims are supported by the CONTEXT. "
        "You must clearly distinguish two very different problems:\n\n"
        "1) HALLUCINATION (penalize this): the answer states a specific fact, number, date, term, "
        "or obligation that CANNOT be found anywhere in the context, or that contradicts the context. "
        "Example: the answer says \"the agreement lasts 10 years\" but no 10-year duration appears "
        "anywhere in the context.\n\n"
        "2) OMISSION (never penalize this): the answer simply does not repeat something that exists "
        "in the context. A concise summary that leaves out secondary details, related statutes, or "
        "additional clauses is NOT a hallucination — it is normal, acceptable summarization. Example: "
        "the context mentions the Motor Vehicles Act but the answer doesn't repeat it — this is not "
        "an unsupported claim, and must not be listed as one.\n\n"
        "Rules:\n"
        "- Only add an entry to unsupported_statements if the answer ASSERTS a specific fact that "
        "cannot be found in the context. Never add an entry just because something from the context "
        "is missing from the answer.\n"
        "- Each unsupported_statements entry must be the exact unsupported claim, quoted as it appears "
        "in the answer, followed by ' — ' and a one-sentence reason it lacks support. Do not write "
        "generic comments like 'the answer does not mention...'.\n"
        "- If every claim in the answer is supported, unsupported_statements MUST be an empty list.\n\n"
        "Scoring calibration — hallucination_score and trust_score must always be internally "
        "consistent (trust_score = 100 - hallucination_score):\n"
        "  * Perfectly grounded, no unsupported claims -> hallucination_score=0, trust_score=100, groundedness=High\n"
        "  * One minor unsupported detail -> hallucination_score≈10, trust_score≈90, groundedness=High\n"
        "  * A few unsupported claims mixed with grounded ones -> hallucination_score≈35, trust_score≈65, groundedness=Medium\n"
        "  * Mostly fabricated or contradicts the context -> hallucination_score≈80, trust_score≈20, groundedness=Low\n\n"
        "All three scores (hallucination_score, trust_score, confidence_score) must be integer "
        "percentages from 0 to 100 (e.g. 90, not 0.9). citation_quality must be a short rating "
        "(Excellent / Good / Fair / Poor), not a paragraph."
    )
    prompt = (
        f"--- USER QUESTION ---\n{question}\n\n"
        f"--- RETRIEVED CONTEXT (the ONLY source of truth) ---\n{context}\n\n"
        f"--- AI GENERATED ANSWER TO EVALUATE ---\n{answer}"
    )

    evaluation = invoke_llm_structured(system_instruction, prompt, HallucinationEvaluation)
    logger.debug(f"[hallucination_agent] final HallucinationEvaluation returned: {evaluation.model_dump()}")
    return evaluation
