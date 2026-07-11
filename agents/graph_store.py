"""Unifies knowledge_graph_agent's entity/relationship output and
dependency_agent's clause-dependency output into a single NetworkX graph
per document, with traversal helpers neither agent offers on its own
(transitive dependencies, shortest path between any two nodes, etc).

knowledge_graph_agent.py and dependency_agent.py keep their exact existing
signatures/return shapes — this module is a pure additive integration layer
consumed by agents/orchestrator.py, not a replacement for either agent or
their pages.
"""

from typing import Any, Dict, List, Optional

import networkx as nx

NODE_TYPES = {"clause", "party", "date", "money", "jurisdiction", "penalty", "obligation"}

NODE_COLORS = {
    "clause": "#636EFA",
    "party": "#636EFA",
    "date": "#FECB52",
    "money": "#FECB52",
    "jurisdiction": "#00CC96",
    "penalty": "#EF553B",
    "obligation": "#FECB52",
}


def new_graph() -> nx.MultiDiGraph:
    """MultiDiGraph because a clause pair can have more than one relation
    simultaneously (e.g. both an explicit 'references' edge and a domain
    'triggers' edge from dependency_agent)."""
    return nx.MultiDiGraph()


def add_node(g: nx.MultiDiGraph, node_id: str, node_type: str, label: str, color: Optional[str] = None) -> None:
    if node_id in g:
        return
    g.add_node(node_id, node_type=node_type, label=label, color=color or NODE_COLORS.get(node_type, "#888888"))


def add_edge(g: nx.MultiDiGraph, source_id: str, target_id: str, relation: str,
             explanation: str = "", color: str = "#888888") -> None:
    if source_id not in g or target_id not in g:
        return
    g.add_edge(source_id, target_id, relation=relation, explanation=explanation, color=color)


def build_document_graph(doc_id: int, db_clauses: List[Dict[str, Any]],
                          kg_data: Dict[str, Any], dependency_edges: List[Any]) -> nx.MultiDiGraph:
    """Merges one clause-node per db_clause, knowledge_graph_agent's entity
    nodes/edges (kg_data == extract_knowledge_graph's unchanged return dict),
    and dependency_agent's DependencyEdge list into one graph instance."""
    g = new_graph()

    for c in db_clauses:
        add_node(g, str(c["id"]), "clause", c.get("section_name", "Clause"), color=NODE_COLORS["clause"])

    # kg_data node ids are already namespaced ("n0", "n1", ...) by
    # knowledge_graph_agent, so they can't collide with clause ids (plain
    # integers as strings).
    for node in kg_data.get("nodes", []):
        node_type = _infer_node_type(node.get("color"))
        add_node(g, node["id"], node_type, node.get("label", ""), color=node.get("color"))

    for edge in kg_data.get("edges", []):
        add_edge(g, edge["source"], edge["target"], edge.get("label", ""), color=edge.get("color", "#888888"))

    for dep in dependency_edges:
        add_edge(
            g, str(dep.source_clause_id), str(dep.target_clause_id),
            dep.dependency_type, explanation=dep.explanation,
        )

    return g


def _infer_node_type(color: Optional[str]) -> str:
    """knowledge_graph_agent doesn't tag node_type explicitly, only color —
    reverse-map it so graph_store's nodes still carry a node_type attribute."""
    for node_type, node_color in NODE_COLORS.items():
        if node_type != "clause" and node_color == color:
            return node_type
    return "entity"


def get_dependents(g: nx.MultiDiGraph, clause_id: str) -> List[str]:
    """Nodes with an edge pointing TO clause_id (i.e. depend on it)."""
    return list(g.predecessors(clause_id)) if clause_id in g else []


def get_transitive_dependencies(g: nx.MultiDiGraph, clause_id: str, max_depth: int = 3) -> List[str]:
    """All nodes reachable by following outgoing edges from clause_id, up to
    max_depth hops, excluding clause_id itself."""
    if clause_id not in g:
        return []
    visited = set()
    frontier = {clause_id}
    for _ in range(max_depth):
        next_frontier = set()
        for node in frontier:
            next_frontier |= set(g.successors(node))
        next_frontier -= visited
        next_frontier.discard(clause_id)
        if not next_frontier:
            break
        visited |= next_frontier
        frontier = next_frontier
    return list(visited)


def shortest_path(g: nx.MultiDiGraph, source_id: str, target_id: str) -> Optional[List[str]]:
    if source_id not in g or target_id not in g:
        return None
    try:
        return nx.shortest_path(g, source_id, target_id)
    except nx.NetworkXNoPath:
        return None


def subgraph_for_clause(g: nx.MultiDiGraph, clause_id: str, radius: int = 1) -> nx.MultiDiGraph:
    if clause_id not in g:
        return new_graph()
    nodes = nx.ego_graph(g.to_undirected(as_view=True), clause_id, radius=radius).nodes
    return g.subgraph(nodes).copy()


def flatten_entities(doc_id: int, kg_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flattens knowledge_graph_agent's nodes into entities-collection rows
    (crud.add_entities_bulk's expected shape). Clause nodes are excluded —
    those already live in the clauses collection."""
    return [
        {"clause_id": None, "entity_text": node.get("label", ""), "entity_type": _infer_node_type(node.get("color"))}
        for node in kg_data.get("nodes", [])
    ]


def flatten_relationships(kg_data: Dict[str, Any], dependency_edges: List[Any]) -> List[Dict[str, Any]]:
    """Flattens both knowledge_graph_agent's edges and dependency_agent's
    edges into relationships-collection rows (crud.add_relationships_bulk's
    expected shape)."""
    rows = [
        {
            "source_type": "entity", "source_id": edge["source"],
            "target_type": "entity", "target_id": edge["target"],
            "relation": edge.get("label", ""), "explanation": None,
        }
        for edge in kg_data.get("edges", [])
    ]
    rows += [
        {
            "source_type": "clause", "source_id": str(dep.source_clause_id),
            "target_type": "clause", "target_id": str(dep.target_clause_id),
            "relation": dep.dependency_type, "explanation": dep.explanation,
        }
        for dep in dependency_edges
    ]
    return rows
