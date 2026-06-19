"""
AERIS — Critic Agent (Accuracy & Quality Optimizer)
===================================================
Specialized management agent dedicated to checking agent response quality,
verifying neural routing confidence, appending new training examples,
and retraining the local intent classifier.
"""

from __future__ import annotations

import json
import os
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from neural.core import neural_core

logger = logging.getLogger("aeris.agent.critic")

PLAN_PROMPT = """You are AERIS's Critic Agent (Accuracy & Quality Optimizer).
Your job is to audit output quality, verify routing correctness, append missing query patterns, and trigger local classifier retraining.

Available actions:
- append_training_example(query: str, correct_intent: str): Add a new correct pattern to the neural model training json file.
- trigger_model_retraining: Retrain the local intent classification neural network from the training data json.
- audit_agent_response(agent_name: str, query: str, response: str): Query an evaluation audit on an agent's response to check quality and guidelines compliance.

User request/input: {message}

Rules:
- If the user wants to add a training sample (e.g. "iske liye label system hona chahiye") -> use append_training_example.
- If the user wants to retrain, calibrate, or optimize model weights -> use trigger_model_retraining.
- If the user wants to audit/evaluate a response for style guidelines -> use audit_agent_response.

Respond with ONLY valid JSON:
{{
  "actions": [
    {{"name": "action_name", "params": {{"param": "value"}}}}
  ],
  "explanation": "Brief explanation of calibration actions"
}}
"""

REPORT_PROMPT = """You are AERIS's Quality Critic & Optimizer.
You have executed evaluations, dataset additions, or retraining.
Summarize the actions taken, report validation loss (if retrained), and provide recommendations on how to improve the accuracy of the system.

User query/concern: {message}
Raw metrics:
{results}
"""

class CriticAgent(BaseAgent):
    """Quality assurance and classifier optimization agent."""

    def __init__(self):
        super().__init__(
            name="CriticAgent",
            description="Evaluates agent responses, audits intent routing classifications, appends new training samples, and calibrates local neural models.",
            task_domain="critic",
            version="1.0.0",
            capabilities=[
                "Model Calibration Trigger",
                "Dataset Pattern Expansion",
                "Quality Compliance Auditing",
                "Inference Drift Mitigation"
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        prompt = PLAN_PROMPT.format(message=message)
        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"): raw = raw[:-3]
                raw = raw.strip()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Critic plan parsing failed: {e}. Falling back to default audit.")
            return {"actions": [], "explanation": "Failed plan"}

    async def execute(self, plan: Any) -> Any:
        results = []
        for step in plan.get("actions", []):
            name = step.get("name")
            params = step.get("params", {})
            try:
                self.log(f"Critic running optimization action: {name}")
                if name == "append_training_example":
                    query = params.get("query", "")
                    intent = params.get("correct_intent", "")
                    if not query or not intent:
                        raise ValueError("Missing query or correct_intent parameters")
                    
                    # Read existing JSON dataset
                    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "neural", "training_data.json")
                    data = []
                    if os.path.exists(json_path):
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                    # Check for duplicate
                    exists = any(item.get("text", "").lower() == query.lower() for item in data)
                    if not exists:
                        data.append({"text": query, "label": intent})
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        msg = f"Appended new training pair: '{query}' -> '{intent}'"
                    else:
                        msg = f"Pattern already exists in dataset."
                        
                    results.append({
                        "action": name,
                        "success": True,
                        "message": msg,
                        "total_dataset_size": len(data)
                    })
                elif name == "trigger_model_retraining":
                    self.log("Triggering IntentClassifierNet calibration retraining...")
                    neural_core.train_initial_intent_model(epochs=300, lr=0.005)
                    results.append({
                        "action": name,
                        "success": True,
                        "is_ready": neural_core.is_intent_ready,
                        "input_dim": neural_core._input_dim
                    })
                elif name == "audit_agent_response":
                    agent = params.get("agent_name", "")
                    q = params.get("query", "")
                    resp = params.get("response", "")
                    
                    audit_prompt = (
                        f"You are the AERIS Quality Auditor.\n"
                        f"Audit the following transaction:\n"
                        f"Agent: {agent}\n"
                        f"Query: '{q}'\n"
                        f"Response: '{resp}'\n\n"
                        f"Evaluate if the response is technically accurate, clear, and follows style guidelines (e.g. respectful tone, proper markdown, helpful structure). "
                        f"Provide a quality score (1-10) and specific improvement notes."
                    )
                    audit_output = await ai_engine.chat([
                        {"role": "system", "content": "You are a software quality auditor. Provide structured evaluation feedback."},
                        {"role": "user", "content": audit_prompt}
                    ], max_tokens=1000)
                    results.append({
                        "action": name,
                        "success": True,
                        "agent": agent,
                        "evaluation": audit_output
                    })
            except Exception as e:
                self.log(f"Error running action {name}: {e}", "ERROR")
                results.append({"action": name, "success": False, "error": str(e)})
        return results

    async def report(self, results: Any) -> str:
        prompt = REPORT_PROMPT.format(message="", results=json.dumps(results, indent=2))
        try:
            return await ai_engine.chat([
                {"role": "system", "content": "You are AERIS's Quality Critic. Respond in clean, optimized markdown detailing quality audit results."},
                {"role": "user", "content": prompt}
            ], max_tokens=1500)
        except Exception as e:
            return f"## Critic Quality Status Report\n\n```json\n{json.dumps(results, indent=2)}\n```"
