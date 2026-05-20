import graphviz
from dataclasses import dataclass
from pathlib import Path
from typing import List

@dataclass
class Node:
    """Represents a node in the flowchart."""
    id: str
    label: str

@dataclass
class Edge:
    """Represents an edge in the flowchart."""
    from_node: str
    to_node: str
    label: str

class Flowchart:
    """Represents a flowchart."""
    def __init__(self, name: str):
        """
        Initializes a new flowchart.

        Args:
            name (str): The name of the flowchart.
        """
        self.name = name
        self.nodes: List[Node] = []
        self.edges: List[Edge] = []

    def add_node(self, node: Node):
        """
        Adds a new node to the flowchart.

        Args:
            node (Node): The node to add.
        """
        self.nodes.append(node)

    def add_edge(self, edge: Edge):
        """
        Adds a new edge to the flowchart.

        Args:
            edge (Edge): The edge to add.
        """
        self.edges.append(edge)

    def visualize(self) -> None:
        """
        Visualizes the flowchart using graphviz.
        """
        dot = graphviz.Digraph(comment=self.name)
        for node in self.nodes:
            dot.node(node.id, node.label)
        for edge in self.edges:
            dot.edge(edge.from_node, edge.to_node, label=edge.label)
        dot.render(f"{self.name}.gv", format="png")

# Example usage:
if __name__ == "__main__":
    flowchart = Flowchart("coaching_website")
    start_node = Node("start", "Start")
    decision_node = Node("decision", "Do you need coaching?")
    yes_node = Node("yes", "Yes")
    no_node = Node("no", "No")
    end_node = Node("end", "End")

    flowchart.add_node(start_node)
    flowchart.add_node(decision_node)
    flowchart.add_node(yes_node)
    flowchart.add_node(no_node)
    flowchart.add_node(end_node)

    flowchart.add_edge(Edge("start", "decision", "Begin"))
    flowchart.add_edge(Edge("decision", "yes", "Yes"))
    flowchart.add_edge(Edge("decision", "no", "No"))
    flowchart.add_edge(Edge("yes", "end", "Get coached"))
    flowchart.add_edge(Edge("no", "end", "Do not get coached"))

    flowchart.visualize()