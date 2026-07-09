from pydantic import BaseModel, Field
from utils.llm_client import invoke_llm_structured_chunked


class SimplificationResult(BaseModel):
    original_clause: str = Field(description="The original legal text")
    simplified_clause: str = Field(description="The clause rewritten in plain, accessible English")
    explanation: str = Field(description="A brief explanation of what the clause means in practical terms")
    real_world_example: str = Field(description="A concrete real-world example illustrating how this clause applies")


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
        "numbers) showing how this clause would actually play out."
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

    simplified_parts = []
    explanation_parts = []
    example_parts = []
    for result, error in results:
        if result is not None:
            simplified_parts.append(result.simplified_clause)
            explanation_parts.append(result.explanation)
            example_parts.append(result.real_world_example)
        else:
            print(f"Error in simplification agent: {error}")
            simplified_parts.append(f"[Simplification failed for this section: {error}]")

    return SimplificationResult(
        original_clause=clause_text,
        simplified_clause="\n\n".join(simplified_parts),
        explanation="\n\n".join(explanation_parts) if explanation_parts else "N/A",
        real_world_example="\n\n".join(example_parts) if example_parts else "N/A",
    )
