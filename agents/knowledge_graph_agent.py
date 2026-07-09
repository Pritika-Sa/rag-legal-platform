import re
from agents.rule_engine import extract_dates, extract_money, extract_obligations

MAX_NODES = 25
MAX_EDGES = 40

PARTY_RE = re.compile(r'([A-Z][A-Za-z0-9&.,\- ]{2,60}?)\s*\(\s*["“]([^"”]{2,40})["”]\s*\)')
JURISDICTION_RE = re.compile(
    r'(?:governing law|governed by the laws of|state of|courts of)\s+(?:the\s+)?([A-Z][A-Za-z ]{2,30})',
    re.IGNORECASE,
)
PENALTY_RE = re.compile(r'\b(penalty|liquidated damages|late fee)\b[^.\n]{0,60}', re.IGNORECASE)

PARTY_COLOR = "#636EFA"
JURISDICTION_COLOR = "#00CC96"
PENALTY_COLOR = "#EF553B"
OBLIGATION_COLOR = "#FECB52"
EDGE_COLOR = "#888888"


def extract_knowledge_graph(doc_name: str, doc_text: str) -> dict:
    """Regex-only entity/relationship extraction (Stage 2, no LLM). Builds a
    bounded graph (<= MAX_NODES nodes, <= MAX_EDGES edges) of parties, dates,
    payments, penalties, jurisdictions, and shall/must obligations."""
    nodes = []
    edges = []
    node_ids = {}

    def add_node(label: str, color: str, key: str):
        if key in node_ids:
            return node_ids[key]
        if len(nodes) >= MAX_NODES:
            return None
        node_id = f"n{len(nodes)}"
        nodes.append({"id": node_id, "label": label[:60], "color": color, "size": 15})
        node_ids[key] = node_id
        return node_id

    parties = []
    for full_name, short_name in PARTY_RE.findall(doc_text):
        node_id = add_node(short_name, PARTY_COLOR, key=f"party:{short_name.lower()}")
        if node_id:
            parties.append(node_id)

    date_nodes = [n for d in extract_dates(doc_text)[:5]
                  if (n := add_node(d, OBLIGATION_COLOR, key=f"date:{d}"))]
    money_nodes = [n for m in extract_money(doc_text)[:5]
                   if (n := add_node(m, OBLIGATION_COLOR, key=f"money:{m}"))]
    penalty_nodes = [n for p in {m.group(0).strip() for m in PENALTY_RE.finditer(doc_text)}
                      if (n := add_node(p, PENALTY_COLOR, key=f"penalty:{p.lower()}"))][:5]
    jurisdiction_nodes = [n for j in {j.strip() for j in JURISDICTION_RE.findall(doc_text)}
                           if (n := add_node(j, JURISDICTION_COLOR, key=f"jurisdiction:{j.lower()}"))][:3]

    for source, relation, target in extract_obligations(doc_text)[:15]:
        if len(edges) >= MAX_EDGES:
            break
        source_id = add_node(source, PARTY_COLOR, key=f"party:{source.lower()}")
        target_id = add_node(target[:40], OBLIGATION_COLOR, key=f"obligation:{target[:40].lower()}")
        if source_id and target_id:
            edges.append({"source": source_id, "target": target_id, "label": relation, "color": EDGE_COLOR})

    anchor = parties[0] if parties else None
    if anchor:
        for extra_nodes, label in [
            (jurisdiction_nodes, "governed by"),
            (date_nodes, "dated"),
            (money_nodes, "involves payment"),
            (penalty_nodes, "subject to"),
        ]:
            for node_id in extra_nodes:
                if len(edges) >= MAX_EDGES:
                    break
                edges.append({"source": anchor, "target": node_id, "label": label, "color": EDGE_COLOR})

    return {"nodes": nodes[:MAX_NODES], "edges": edges[:MAX_EDGES]}
