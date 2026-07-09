from pydantic import BaseModel, Field
from utils.llm_client import invoke_llm_structured_chunked


class TranslationResult(BaseModel):
    translated_clause: str = Field(description="The fully translated legal clause")
    confidence_score: int = Field(description="Confidence score of the translation accuracy from 0 to 100")


def translate_clause(clause_text: str, target_language: str) -> TranslationResult:
    """Agent 8: Translation Agent."""
    system_instruction = (
        f"You are an expert, certified legal translator. Translate the following contract clause into {target_language}. "
        "CRITICAL REQUIREMENTS:\n"
        "1. Preserve the exact legal meaning and nuances.\n"
        "2. Preserve any clause numbering (e.g., '1.1', '(a)').\n"
        "3. Preserve all named legal entities and company names without translating them.\n"
        "4. Assign a 'confidence_score' between 0 and 100 for legal accuracy."
    )

    # Tamil/Hindi output tokenizes far less efficiently than English (more
    # tokens per character), so a clause whose full translation would exceed
    # the model's completion budget gets chunked and stitched back together
    # to keep every call's output well under that budget.
    results = invoke_llm_structured_chunked(
        system_instruction, clause_text, TranslationResult, prompt_prefix="Clause to translate:\n\n"
    )

    translated_parts = []
    scores = []
    for result, error in results:
        if result is not None:
            translated_parts.append(result.translated_clause)
            scores.append(result.confidence_score)
        else:
            print(f"Error in translation agent: {error}")
            translated_parts.append(f"[Translation failed for this section: {error}]")
            scores.append(0)

    translated_clause = " ".join(translated_parts)
    confidence_score = int(sum(scores) / len(scores)) if scores else 0
    return TranslationResult(translated_clause=translated_clause, confidence_score=confidence_score)
