# Phase 7 Implementation Plan: Neural Network Integration

Based on your current AERIS system architecture and the completion of Phases 1-6, the next logical step is to fully integrate the **Neural Engine (Phase 7)**. We have the foundational PyTorch models (`IntentClassifierNet`, `AnomalyDetectorNet`) and `neural_core` built, but they are not yet actively driving the system.

Here is the proposed plan to bring the local Neural Engine online.

## User Review Required

> [!IMPORTANT]
> The Brain needs a way to convert text into numbers (tensors) before passing it to `IntentClassifierNet`. I propose adding a fast `TfidfVectorizer` (via `scikit-learn`) that trains on a small set of predefined intents on startup, allowing lightning-fast local intent classification. Does this approach work for you, or would you prefer a different embedding strategy?

## Proposed Changes

---

### Neural Text Preprocessing & Training
We need to provide the models with actual data and weights rather than random initialization.

#### [MODIFY] [core.py](file:///d:/Sambhav%20Projects/AERIS/BACKEND/neural/core.py)
- Integrate a `scikit-learn` `TfidfVectorizer` to convert text messages into feature vectors (`input_dim=128` or similar) for the intent model.
- Add a lightweight `train_initial_intent_model()` method to quickly train on 50-100 sample phrases (e.g., "scan port 80", "hello") at startup.

---

### Brain Orchestrator Integration
The Brain is currently using a hard-coded keyword fallback and then asking the LLM. 

#### [MODIFY] [brain.py](file:///d:/Sambhav%20Projects/AERIS/BACKEND/brain.py)
- Import `neural_core` and initialize the intent models at startup.
- Update `classify_intent` to pass the user message through `neural_core.predict_intent()`.
- If the neural confidence is high (> 80%), use the local neural prediction immediately (0 latency).
- If confidence is low, fall back to the AI Engine (Groq).

---

### Security Agent Anomaly Detection
The Security agent currently relies purely on LLM analysis for VAPT.

#### [MODIFY] [security_agent.py](file:///d:/Sambhav%20Projects/AERIS/BACKEND/agents/security_agent.py)
- Import `neural_core`.
- Pass numeric outputs from security tools (like response times, packet sizes, or header counts) to `neural_core.detect_anomaly()`.
- If the reconstruction MSE error is extremely high, flag it as a WAF anomaly or weird server behavior and include it in the final report.

---

### Neural Sub-Agent
We need an agent to handle explicit AI/ML requests from the user.

#### [NEW] [neural_agent.py](file:///d:/Sambhav%20Projects/AERIS/BACKEND/agents/neural_agent.py)
- Create `NeuralAgent` inheriting from `BaseAgent`.
- Will handle tasks like "Train a basic neural net on this data" or "Analyze this dataset for anomalies."
- Uses `ai_engine` to write dynamic PyTorch/Scikit-learn code for local execution.

#### [MODIFY] [\_\_init\_\_.py](file:///d:/Sambhav%20Projects/AERIS/BACKEND/agents/__init__.py)
- Export `NeuralAgent` and add it to the Brain's agent registry.

## Verification Plan

### Automated Tests
- Run `python test_neural.py` to ensure local PyTorch inference works without crashing.
- Boot up the API server (`python api.py`) and verify that it trains the initial intent weights without stalling.

### Manual Verification
- Send a chat message via the UI: "hello" -> verify `brain.py` routes it via local neural inference instead of an LLM call.
- Send an ML request: "Create a simple ML model" -> verify it routes to `NeuralAgent`.
