import os
import re
import json
import logging
from typing import Type, TypeVar
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import BaseModel

load_dotenv()
logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# The account's Groq tier enforces a hard tokens-per-minute cap (currently 6000),
# and the reserved completion budget (max_tokens) counts against it alongside the
# prompt. Keep a safety margin below the real limit since the estimate below is
# approximate.
GROQ_TPM_LIMIT = 6000
MAX_COMPLETION_TOKENS = 2048
_CHARS_PER_TOKEN = 3.5  # conservative estimate for dense legal/English text

_embeddings_instance = None


def get_llm(temperature: float = 0.0) -> ChatGroq:
    """Returns a ChatGroq instance."""
    return ChatGroq(
        model=GROQ_MODEL,
        api_key=GROQ_API_KEY,
        temperature=temperature,
        max_tokens=MAX_COMPLETION_TOKENS,
        request_timeout=120,
    )


def _estimate_tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN)


def get_prompt_budget_chars(system_prompt: str) -> int:
    """Returns the max user_prompt length (chars) that keeps (system + user +
    max_tokens) within the account's tokens-per-minute limit."""
    safety_margin = 500
    budget_tokens = GROQ_TPM_LIMIT - MAX_COMPLETION_TOKENS - _estimate_tokens(system_prompt) - safety_margin
    return max(int(budget_tokens * _CHARS_PER_TOKEN), 500)


def _fit_prompt_to_budget(system_prompt: str, user_prompt: str) -> str:
    """Truncates user_prompt so (system + user + max_tokens) stays within the
    account's tokens-per-minute limit, regardless of which agent is calling.
    An oversized clause (e.g. a whole document stored as a single "clause" by
    an older, unfixed pipeline run, or any unusually long section) would
    otherwise make the request fail with a 413 rate_limit_exceeded error no
    matter how small max_tokens is."""
    budget_chars = get_prompt_budget_chars(system_prompt)
    if len(user_prompt) <= budget_chars:
        return user_prompt
    logger.warning(
        f"Prompt is {len(user_prompt)} chars, truncating to {budget_chars} chars "
        f"to stay within the model's tokens-per-minute budget."
    )
    return user_prompt[:budget_chars] + "\n\n[...input truncated: exceeded the model's per-minute token budget...]"


def get_embeddings() -> HuggingFaceEmbeddings:
    """Returns cached embeddings singleton — loads model once."""
    global _embeddings_instance
    if _embeddings_instance is None:
        model_kwargs = {"device": "cpu"}
        encode_kwargs = {"normalize_embeddings": True}
        _embeddings_instance = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs,
        )
    return _embeddings_instance


def _extract_json_from_text(text: str) -> str:
    """Extracts the first JSON object or array from raw LLM text."""
    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


_JSON_TYPE_PLACEHOLDERS = {"string": "...", "number": 0.0, "integer": 0, "boolean": False}


def _resolve_schema_node(node: dict, defs: dict) -> dict:
    if "$ref" in node:
        return defs.get(node["$ref"].split("/")[-1], {})
    return node


def _schema_to_example(node: dict, defs: dict):
    node = _resolve_schema_node(node, defs)
    node_type = node.get("type")
    if node_type == "object" or "properties" in node:
        return {
            field: _schema_to_example(info, defs)
            for field, info in node.get("properties", {}).items()
        }
    if node_type == "array":
        return [_schema_to_example(node.get("items", {}), defs)]
    return _JSON_TYPE_PLACEHOLDERS.get(node_type, "...")


def _build_example_json(output_schema: Type[BaseModel]) -> str:
    """Builds an example JSON object (field -> placeholder value, with nested
    object/array shapes fully expanded) instead of dumping the raw JSON Schema.
    The small instruct model we use tends to echo JSON-Schema vocabulary
    ("properties", "type", "required") back verbatim, and for nested object
    fields (e.g. a list of EntityRelation) it invents its own ad-hoc shape
    instead of the real one. Showing a concrete example with every nested
    field spelled out avoids both failure modes."""
    schema = output_schema.model_json_schema()
    example = _schema_to_example(schema, schema.get("$defs", {}))
    return json.dumps(example, indent=2)


def invoke_llm_structured(
    system_prompt: str,
    user_prompt: str,
    output_schema: Type[T],
    temperature: float = 0.0,
) -> T:
    """Invokes Groq LLM and parses the response into a Pydantic model."""
    example_json = _build_example_json(output_schema)

    full_system = (
        f"{system_prompt}\n\n"
        f"CRITICAL: Respond with ONLY a single flat JSON object containing exactly these keys, "
        f"filled in with your real analysis (not type names, not schema metadata). "
        f"Do not wrap the values inside a \"properties\" or \"value\" key — put them directly "
        f"at the top level as shown. No markdown, no text before or after the JSON.\n\n"
        f"Required JSON shape (values below are placeholders to be replaced):\n{example_json}"
    )
    user_prompt = _fit_prompt_to_budget(full_system, user_prompt)

    llm = get_llm(temperature=temperature)
    response = llm.invoke([
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_prompt},
    ])

    raw_text = response.content.strip()
    json_str = _extract_json_from_text(raw_text)

    try:
        # strict=False tolerates literal control characters (e.g. raw newlines)
        # inside string values, which small instruct models routinely emit
        # despite being told to produce valid JSON.
        parsed = json.loads(json_str, strict=False)
        return output_schema.model_validate(parsed)
    except Exception as e:
        logger.warning(f"First parse failed ({e}), retrying with correction prompt...")

        correction_prompt = (
            f"Your previous response was not a valid flat JSON object. The raw output was:\n"
            f"---\n{raw_text[:2000]}\n---\n\n"
            f"Output ONLY a flat JSON object with exactly this shape (no nesting under "
            f"'properties' or 'value'):\n{example_json}\n\n"
            f"No explanation. No markdown. Just the JSON."
        )
        response2 = llm.invoke([
            {"role": "system", "content": full_system},
            {"role": "user", "content": correction_prompt},
        ])
        raw_text2 = response2.content.strip()
        json_str2 = _extract_json_from_text(raw_text2)
        try:
            parsed2 = json.loads(json_str2, strict=False)
            return output_schema.model_validate(parsed2)
        except Exception as e2:
            raise ValueError(
                f"LLM failed to produce valid JSON for {output_schema.__name__} after retry: "
                f"{e2}. Raw response: {raw_text2[:500]}"
            ) from e2


def split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Splits text into <= max_chars chunks on sentence boundaries where possible."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current += " " + sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)

    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            final_chunks.extend(chunk[i:i + max_chars] for i in range(0, len(chunk), max_chars))
    return final_chunks


def _split_chunk_in_half(chunk: str) -> tuple[str, str]:
    """Splits a chunk near its midpoint, preferring a sentence boundary."""
    mid = len(chunk) // 2
    split_at = chunk.rfind(". ", 0, mid + 1)
    if split_at == -1 or split_at < len(chunk) * 0.2:
        split_at = mid
    else:
        split_at += 1
    left, right = chunk[:split_at].strip(), chunk[split_at:].strip()
    if not left or not right:
        left, right = chunk[:mid].strip(), chunk[mid:].strip()
    return left, right


def invoke_llm_structured_chunked(
    system_prompt: str,
    text: str,
    output_schema: Type[T],
    prompt_prefix: str = "Text to process:\n\n",
    max_chunk_chars: int = 1200,
    min_chunk_chars: int = 150,
    max_split_depth: int = 4,
    temperature: float = 0.0,
) -> list[tuple[T | None, str | None]]:
    """Runs invoke_llm_structured over `text` split into chunks sized to fit
    the completion budget. Long input risks the model either exceeding
    MAX_COMPLETION_TOKENS mid-JSON or spiraling into a repetition loop that
    burns the budget before closing the JSON; when a chunk's call fails, it
    is recursively halved and retried until it succeeds or hits the size/depth
    floor. Returns one (result, error) pair per leaf chunk, in text order —
    callers decide how to combine results and how to represent failures for
    their own schema."""

    def _run(chunk: str, depth: int) -> list[tuple[T | None, str | None]]:
        try:
            result = invoke_llm_structured(
                system_prompt, f"{prompt_prefix}{chunk}", output_schema, temperature=temperature
            )
            return [(result, None)]
        except Exception as e:
            if len(chunk) <= min_chunk_chars or depth >= max_split_depth:
                return [(None, str(e))]
            left, right = _split_chunk_in_half(chunk)
            return _run(left, depth + 1) + _run(right, depth + 1)

    results: list[tuple[T | None, str | None]] = []
    for chunk in split_into_chunks(text, max_chunk_chars):
        results.extend(_run(chunk, 0))
    return results


def invoke_llm_text(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> str:
    """Invokes Groq LLM and returns plain text."""
    user_prompt = _fit_prompt_to_budget(system_prompt, user_prompt)
    llm = get_llm(temperature=temperature)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])
    return response.content.strip()
