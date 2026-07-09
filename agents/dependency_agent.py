import re
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from agents.rule_engine import DEPENDENCY_RULES, extract_section_refs

_LEADING_NUM_RE = re.compile(r'^(\d+(?:\.\d+)*)')
_REF_NUM_RE = re.compile(r'(\d+(?:\.\d+)*)')


class DependencyEdge(BaseModel):
    source_clause_id: int = Field(description="The integer ID of the source clause")
    target_clause_id: int = Field(description="The integer ID of the target clause it depends on")
    dependency_type: str = Field(description="Nature of the dependency (e.g., 'triggers', 'references', 'limits')")
    explanation: str = Field(description="Brief explanation of why this dependency exists")


def extract_clause_dependencies(clauses: List[Dict[str, Any]]) -> List[DependencyEdge]:
    """Rule-based clause dependency detection (Stage 2, no LLM). Combines
    (a) explicit numbered cross-references found in clause text (e.g. 'as
    set out in Section 5.2') matched against other clauses' leading section
    numbers, and (b) a static domain table of clause-type relationships
    (e.g. Termination triggers Liability)."""
    if len(clauses) < 2:
        return []

    edges: List[DependencyEdge] = []
    seen_pairs = set()

    numbered = {}
    for c in clauses:
        match = _LEADING_NUM_RE.match(c.get("section_name", "").strip())
        if match:
            numbered[match.group(1)] = c

    for c in clauses:
        for ref in extract_section_refs(c.get("text_content", "")):
            ref_match = _REF_NUM_RE.search(ref)
            if not ref_match:
                continue
            target = numbered.get(ref_match.group(1))
            if not target or target["id"] == c["id"]:
                continue
            pair = (c["id"], target["id"])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edges.append(DependencyEdge(
                source_clause_id=c["id"], target_clause_id=target["id"],
                dependency_type="references",
                explanation=f"'{c.get('section_name', 'Clause')}' explicitly references {ref}, "
                            f"matching '{target.get('section_name', 'Clause')}'.",
            ))

    by_type = {}
    for c in clauses:
        by_type.setdefault(c.get("classification", "General"), c)

    for source_type, target_type, relation in DEPENDENCY_RULES:
        source, target = by_type.get(source_type), by_type.get(target_type)
        if not source or not target or source["id"] == target["id"]:
            continue
        pair = (source["id"], target["id"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edges.append(DependencyEdge(
            source_clause_id=source["id"], target_clause_id=target["id"],
            dependency_type=relation,
            explanation=f"'{source.get('section_name', 'Clause')}' ({source_type}) {relation.replace('_', ' ')} "
                        f"'{target.get('section_name', 'Clause')}' ({target_type}) by domain convention.",
        ))

    return edges
