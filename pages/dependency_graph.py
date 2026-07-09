import streamlit as st
from database import crud
from utils.visualizer import render_pyvis_graph
from agents.dependency_agent import extract_clause_dependencies
from utils.theme import render_header

render_header(
    "🔗",
    "Clause Dependency Network",
    "Visualizes AI-detected semantic relationships and legal dependencies between clauses (e.g., Termination → Liability).",
    badge="Agent 12"
)

doc_id = st.session_state.active_doc_id
doc_name = st.session_state.active_doc_name

if not doc_id:
    st.warning("⚠️ Please select an active document in the sidebar to view dependencies.")
else:
    st.info(f"Mapping Dependencies for: **{doc_name}**")
    
    clauses = crud.get_clauses_for_document(doc_id)
    
    if len(clauses) < 2:
        st.info("Not enough clauses to map dependencies.")
    else:
        if st.button("Generate Dependency Graph (Agent 12)"):
            with st.spinner("Agent 12 is analyzing semantic relationships between all clauses..."):
                try:
                    # 1. Build Nodes
                    nodes = []
                    clause_lookup = {}
                    for c in clauses:
                        clause_lookup[c['id']] = c['section_name']
                        
                        # Color node based on risk
                        color = "#00CC96"  # None/Low
                        if c['risk_level'] == "High":
                            color = "#EF553B"
                        elif c['risk_level'] == "Medium":
                            color = "#FECB52"
                            
                        nodes.append({
                            "id": str(c['id']), # PyVis prefers string IDs
                            "label": c['section_name'][:25] + "..." if len(c['section_name']) > 25 else c['section_name'],
                            "color": color,
                            "title": f"Section: {c['section_name']}\nRisk: {c['risk_level']}",
                            "size": 18 if c['risk_level'] in ("High", "Medium") else 12
                        })
                    
                    # 2. Get Edges from Agent 12
                    detected_edges = extract_clause_dependencies(clauses)
                    
                    edges = []
                    for e in detected_edges:
                        # Ensure IDs are valid and convert to string
                        if e.source_clause_id in clause_lookup and e.target_clause_id in clause_lookup:
                            edges.append({
                                "source": str(e.source_clause_id),
                                "target": str(e.target_clause_id),
                                "label": e.dependency_type,
                                "color": "#888888",
                                "width": 1.5,
                                "title": e.explanation # tooltip on hover
                            })
                            
                    st.markdown("### 🕸️ Directed Reference Graph")
                    st.caption("Arrows point from the referencing clause to the clause being referenced.")
                    
                    if edges:
                        render_pyvis_graph(nodes, edges, directed=True)
                    else:
                        st.info("No semantic dependencies detected between sections.")
                        
                    st.markdown(
                        """
                        **How to read this chart:**
                        - A directed arrow from **Clause A** to **Clause B** means Clause A semantically depends on or references Clause B (e.g., Liability limits apply to Termination).
                        - Hover over the edges to read Agent 12's explanation of the relationship.
                        - Node sizes and colors reflect risk categories, with **Red** indicating High Risk exposure.
                        """
                    )

                    # Plain-language list of every edge's explanation —
                    # dependency_agent already computes this per edge, but it
                    # was previously only visible as a hover tooltip, which is
                    # easy to miss when the diagram gets busy.
                    if detected_edges:
                        st.markdown("### 📝 Relationship Explanations")
                        st.caption("Plain-language reading of every arrow shown in the diagram above.")
                        for e in detected_edges:
                            source_label = clause_lookup.get(e.source_clause_id, f"Clause {e.source_clause_id}")
                            target_label = clause_lookup.get(e.target_clause_id, f"Clause {e.target_clause_id}")
                            st.markdown(f"- **{source_label}** — *{e.dependency_type}* → **{target_label}**: {e.explanation}")

                    crud.add_audit_log("dependency_graph", f"Agent 12 generated dependency graph for document '{doc_name}'")
                except Exception as e:
                    st.error(f"Failed to generate dependency graph: {e}")
