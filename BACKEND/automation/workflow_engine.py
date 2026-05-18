"""
AERIS - Workflow Engine
Define and execute multi-step automation workflows.
"""
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Multi-step workflow automation"""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self.workflows_dir = self.data_dir / "workflows"
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self._install_examples()

    def _install_examples(self):
        """Install example workflows if none exist"""
        examples = {
            "morning_routine": {
                "name": "Morning Routine",
                "description": "Start your day with essential apps and info",
                "steps": [
                    {"action": "automation", "command": "open chrome"},
                    {"action": "chat", "command": "What's today's date and any important events?"},
                    {"action": "automation", "command": "open spotify"},
                ]
            },
            "research_workflow": {
                "name": "Deep Research",
                "description": "Research a topic thoroughly",
                "steps": [
                    {"action": "research", "command": "{topic}"},
                    {"action": "chat", "command": "Summarize the key findings about {topic}"},
                ]
            },
        }
        for name, workflow in examples.items():
            path = self.workflows_dir / f"{name}.json"
            if not path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(workflow, f, indent=2)

    def list_workflows(self):
        """List all available workflows"""
        workflows = []
        for f in self.workflows_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    workflows.append({
                        "id": f.stem,
                        "name": data.get("name", f.stem),
                        "description": data.get("description", ""),
                        "steps": len(data.get("steps", [])),
                    })
            except Exception:
                pass
        return workflows

    def get_workflow(self, workflow_id):
        """Get a specific workflow"""
        path = self.workflows_dir / f"{workflow_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def create_workflow(self, workflow_id, name, description, steps):
        """Create a new workflow"""
        path = self.workflows_dir / f"{workflow_id}.json"
        data = {"name": name, "description": description, "steps": steps}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    def run_workflow(self, workflow_id, params=None):
        """Execute a workflow"""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return {"error": f"Workflow '{workflow_id}' not found"}

        params = params or {}
        results = []

        try:
            import automation
            import asyncio
        except Exception:
            return {"error": "Automation not available"}

        for i, step in enumerate(workflow.get("steps", [])):
            command = step.get("command", "")
            # Replace parameters
            for key, val in params.items():
                command = command.replace(f"{{{key}}}", val)

            logger.info(f"Workflow step {i+1}: {step.get('action')} - {command}")
            try:
                # Use the user's automation.py to execute the command synchronously via loop
                result = asyncio.run(automation.Automation([command]))
                results.append({"step": i+1, "action": step["action"], "command": command, "result": str(result)[:500]})
            except Exception as e:
                results.append({"step": i+1, "action": step["action"], "command": command, "error": str(e)})

            time.sleep(0.5)  # Brief pause between steps

        return {"workflow": workflow["name"], "results": results}

    def delete_workflow(self, workflow_id):
        """Delete a workflow"""
        path = self.workflows_dir / f"{workflow_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False
