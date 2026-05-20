import graphviz
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

@dataclass
class Node:
    """Represents a node in the graph."""
    id: str
    label: str

@dataclass
class Edge:
    """Represents an edge in the graph."""
    from_node: str
    to_node: str
    label: str

class CoachingWebsiteGraph:
    """Represents a directed graph for the coaching website project."""
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []

    def add_node(self, node_id: str, label: str) -> None:
        """Adds a node to the graph."""
        self.nodes[node_id] = Node(id=node_id, label=label)

    def add_edge(self, from_node_id: str, to_node_id: str, label: str) -> None:
        """Adds an edge to the graph."""
        if from_node_id not in self.nodes:
            raise ValueError(f"Node {from_node_id} does not exist")
        if to_node_id not in self.nodes:
            raise ValueError(f"Node {to_node_id} does not exist")
        self.edges.append(Edge(from_node=from_node_id, to_node=to_node_id, label=label))

    def visualize(self, output_file: Path) -> None:
        """Visualizes the graph using graphviz."""
        dot = graphviz.Digraph()
        for node in self.nodes.values():
            dot.node(node.id, node.label)
        for edge in self.edges:
            dot.edge(edge.from_node, edge.to_node, label=edge.label)
        dot.render(str(output_file), format="png")

# Example usage:
if __name__ == "__main__":
    graph = CoachingWebsiteGraph()
    graph.add_node("start", "Start")
    graph.add_node("step1", "Step 1")
    graph.add_node("step2", "Step 2")
    graph.add_node("end", "End")
    graph.add_edge("start", "step1", "Begin")
    graph.add_edge("step1", "step2", "Next")
    graph.add_edge("step2", "end", "Finish")
    output_file = Path("coaching_website_flowchart.png")
    graph.visualize(output_file)
    print(f"Flowchart generated: {output_file}")