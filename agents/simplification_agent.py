from pydantic import BaseModel, Field
from utils.llm_client import invoke_llm_structured_chunked


class SimplificationResult(BaseModel):
    original_clause: str = Field(description="The original legal text")
    simplified_clause: str = Field(description="The clause rewritten in plain, accessible English")
    explanation: str = Field(description="A brief explanation of what the clause means in practical terms")
    real_world_example: str = Field(description="A concrete real-world example illustrating how this clause applies")
    easy_summary: str = Field(description="A one or two sentence plain-English summary of the clause")
    rights: str = Field(description="What rights this clause grants, as a short bullet-style list")
    obligations: str = Field(description="What obligations/duties this clause imposes, as a short bullet-style list")
    hidden_risks: str = Field(description="Risks or downsides in this clause that aren't obvious from a casual read")
    ai_recommendation: str = Field(description="A concrete recommendation for how to respond to or negotiate this clause")


def simplify_clause(clause_text: str) -> SimplificationResult:
    """Agent 7: Legal Simplification Agent."""
    system_instruction = (
        "You are an expert Legal Simplification Agent. Your job is to EXPLAIN what a legal clause "
        "means in plain, everyday English — not to lightly reword it or just add line breaks.\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. Do NOT copy the original sentences or make only cosmetic changes. Rewrite each idea "
        "in your own words, as if explaining it out loud to a friend with no legal background.\n"
        "2. Use short sentences and everyday vocabulary. Replace defined terms and legal jargon "
        "with a plain-language description of what they actually mean.\n"
        "3. Preserve the legal substance exactly — all numbers, dates, deadlines, and obligations — "
        "even though the wording changes completely.\n"
        "4. In 'explanation', spell out in practical terms who has to do what, who benefits, and "
        "what the risk or consequence is if the clause applies.\n"
        "5. In 'real_world_example', give a concrete, specific scenario (with example names or "
        "numbers) showing how this clause would actually play out.\n"
        "6. In 'easy_summary', give a one or two sentence plain-English summary.\n"
        "7. In 'rights', list what this clause entitles the reader to (or 'None identified' if none).\n"
        "8. In 'obligations', list what this clause requires the reader to do (or 'None identified' if none).\n"
        "9. In 'hidden_risks', call out non-obvious downsides, traps, or one-sided terms.\n"
        "10. In 'ai_recommendation', give one concrete, actionable recommendation."
    )

    # A long clause needs a genuinely longer, restructured explanation as
    # output, which risks exceeding the model's completion budget in one call.
    # Chunking keeps each call's output well within that budget so nothing
    # gets silently truncated or left as a verbatim copy of the input.
    results = invoke_llm_structured_chunked(
        system_instruction,
        clause_text,
        SimplificationResult,
        prompt_prefix="Please explain this legal clause in plain English:\n\n",
        max_chunk_chars=900,
    )

    parts = {
        "simplified_clause": [], "explanation": [], "real_world_example": [],
        "easy_summary": [], "rights": [], "obligations": [], "hidden_risks": [], "ai_recommendation": [],
    }
    for result, error in results:
        if result is not None:
            for key in parts:
                parts[key].append(getattr(result, key))
        else:
            print(f"Error in simplification agent: {error}")
            parts["simplified_clause"].append(f"[Simplification failed for this section: {error}]")

    return SimplificationResult(
        original_clause=clause_text,
        **{key: ("\n\n".join(values) if values else "N/A") for key, values in parts.items()},
    )
