from typing import Dict, List
from agent import CodeAgent

class MultiAgentOrchestration:
    """MultiAgentOrchestration class"""
    def __init__(self):
        self.agents: Dict[str, CodeAgent] = {}

    def add_agent(self, agent: CodeAgent) -> None:
        """Add an agent to the orchestration"""
        self.agents[agent.agent.name] = agent

    def execute_agents(self) -> None:
        """Execute all agents in the orchestration"""
        for agent in self.agents.values():
            agent.execute()

def main() -> None:
    """Main function"""
    orchestration = MultiAgentOrchestration()
    agent1 = CodeAgent(
        Agent(
            name="AERIS Code Agent",
            description="AERIS ka Code Agent",
            dependencies=["numpy", "pandas"]
        )
    )
    agent2 = CodeAgent(
        Agent(
            name="Other Agent",
            description="Any other agent",
            dependencies=["scikit-learn", "tensorflow"]
        )
    )
    orchestration.add_agent(agent1)
    orchestration.add_agent(agent2)
    orchestration.execute_agents()

if __name__ == "__main__":
    main()