# AERIS Feature Report

Generated: 2026-05-18

## Executive Summary

AERIS is an autonomous, multi-agent AI assistant with a FastAPI backend, a Next.js frontend, persistent memory, local neural routing support, a broad tool registry, and specialized agents for chat, security, system automation, research, coding, image generation, auditing, observation, and project-building workflows.

The system is organized around a central Brain orchestrator. User requests enter through the API or WebSocket layer, are classified into intents, routed to the appropriate agent, executed through tools where needed, audited for quality on non-fast paths, saved to memory, and returned to the frontend with metadata such as active agent, intent, task counts, and execution timing.

The implementation includes both mature features and partially integrated capabilities. Mature areas include the chat API, agent routing, tool registry, frontend chat interface, markdown/code rendering, image-result rendering, memory persistence, and many file/system/generation tools. Areas that appear partial or dependent on environment configuration include neural intent labels, security scan execution wiring, external provider access, Chrome extension features, PDF generation dependencies, and some security/recon tool availability.

## Product Identity

Project name: AERIS, expanded in the UI as "Autonomous Enhanced Reasoning Intelligence System."

Primary user experience: a futuristic AI interface with an animated orb, reactive processing state, sliding chat panel, quick action buttons, markdown responses, code blocks, generated image previews, and live backend status checks.

Primary backend role: an autonomous assistant runtime that can converse, search, automate local system actions, generate code and media, perform security analysis, index local knowledge, and orchestrate multi-step tasks through specialized agents and tools.

## High-Level Architecture

### Frontend

The frontend is a Next.js application located in `FRONTEND/`.

Key components:

- `AerisInterface.tsx`: main UI shell, orb state, backend online/offline polling, particle canvas, custom cursor, and chat panel mount.
- `Orb.tsx`: animated central orb and waveform visuals.
- `ChatPanel.tsx`: slide-up chat interface, message sending, chat history loading, quick actions, thinking-stage animation, voice-mode simulation, and full-screen expansion.
- `ChatMessage.tsx`: markdown rendering, GitHub-flavored markdown, syntax highlighting, copyable code blocks, agent/intent badges, streaming typewriter animation, and `[IMAGE:url]` rendering.
- `useParticles.ts`, `useWaveform.ts`, `useCursor.ts`: visual interaction hooks.

Frontend dependencies include Next.js, React, `react-markdown`, `remark-gfm`, and `react-syntax-highlighter`.

### Backend

The backend is a FastAPI application located in `BACKEND/`.

Key modules:

- `api.py`: FastAPI app, REST endpoints, WebSocket endpoints, status API, CORS, static image serving, RAG endpoints, image endpoints, shell endpoints, security intelligence endpoints, overlay/music extension endpoints.
- `brain.py`: central orchestrator for intent classification, task planning, agent dispatch, retries, audit integration, memory persistence, and response aggregation.
- `ai_engine.py`: unified Groq and Gemini interface with Groq key rotation, Gemini fallback, reasoning calls, classification calls, summarization, and vision support.
- `tools/tool_registry.py`: legacy comprehensive tool registry with file, automation, research, RAG, vision, generation, shell, workflow, navigation, and computer-use tools.
- `tools/universal_registry.py`: newer registry that migrates built-in tools and can load dynamic tools.
- `agents/`: core agents, observer/audit agents, project builder, proactive agent, and swarm-style sub-agents.
- `memory/store.py`: persistent conversation and task-result store.
- `neural/core.py`: local PyTorch neural core for TF-IDF intent classification and anomaly detection.
- `services/`: file tools, RAG, shell bridge, security layer, file converter, chat engine, vision engine.
- `generation/`: image, video, website, diagram, and dynamic tool generation.
- `intelligence/`: threat intelligence, zero-day probes, AI triage, threat narrative, safety/system/tool awareness, and feedback modules.

## Request Processing Flow

1. User submits a message through `/api/chat` or `/ws`.
2. `Brain.process()` stores the user message in persistent memory.
3. The Brain builds context from recent chat history.
4. For complex requests, the Brain first tries swarm delegation through `DelegatorAgent`.
5. For simple requests, the Brain classifies intent using:
   - local neural model if ready and extremely confident,
   - LLM classification through `AIEngine.classify()`,
   - keyword fallback if LLM classification fails.
6. The Brain builds a one-task or multi-task plan.
7. Tasks are executed sequentially or in parallel through the selected agent.
8. Non-fast-route results are checked by `AuditAgent`; failed audits can trigger one retry with feedback.
9. Responses are aggregated, saved to memory with metadata, and returned to the API caller.

Supported primary intents in the Brain:

- `chat`
- `security`
- `system`
- `research`
- `code`
- `image`

## Core Agents

### ChatAgent

Purpose: general conversation, Q&A, math, translation, greetings, and capability reporting.

Features:

- Injects agent capability summaries into its system prompt.
- Uses recent chat history from persistent memory.
- Routes general responses through the unified AI engine.
- Presents itself as AERIS and explains system capabilities when asked.

### SecurityAgent

Purpose: security assessment, reconnaissance, VAPT-style analysis, and reporting.

Declared capabilities:

- Port scanning.
- DNS lookup and enumeration.
- Subdomain discovery.
- SSL/TLS certificate analysis.
- HTTP header analysis.
- WHOIS lookup.
- Vulnerability assessment.
- Security report generation.
- AI auto-triage under the VulnSage intelligence modules.
- Threat narrative generation.
- Zero-day detection support.

Execution model:

- Uses an LLM to plan which security tools should run.
- Builds target-specific parameters per tool.
- Runs selected tools through `tool_registry`.
- Generates a markdown security report.
- Attempts to add AI triage and executive threat narrative sections where the intelligence modules are available.

Implementation note:

- SecurityAgent references `recon` and `vapt` tool categories and tool names such as `dns_lookup`, `subdomain_enum`, `port_scan`, `whois_lookup`, `header_analysis`, and `ssl_check`. The report should treat these as intended capabilities unless the registry has successfully loaded those tools in the running environment.

### SystemAgent

Purpose: OS automation, browser actions, command execution, local file operations, and UI automation.

Features:

- Uses a `ToolSelector` where available to rank candidate tools.
- Uses an LLM planner to choose one or more system tools.
- Supports aliases for common tool naming mismatches.
- Executes tools with retry handling.
- Uses `ObserverAgent` to inspect failed tool runs and decide whether to proceed, retry with changed parameters, use an alternative, skip, or abort.
- Can ask the LLM to heal parameters after observer feedback.

Capabilities:

- Open/close apps.
- Browser navigation and searches.
- YouTube/music playback routing.
- Shell command execution.
- File system operations.
- Media/system control.
- Screenshot and screen-related workflows.
- Computer-use style UI automation.

### ResearchAgent

Purpose: web research and synthesis.

Features:

- Extracts optimized search queries via LLM.
- Supports up to three queries per research task.
- Executes web search through tool registry.
- Synthesizes search results into a markdown answer with source links.

Capabilities:

- Web search.
- Current events/news.
- Multi-query research.
- Data synthesis.
- Source citation.

Implementation note:

- Research quality depends on Tavily or equivalent web search configuration used by the backing tool.

### CodingAgent

Purpose: code generation, code analysis, debugging, refactoring, testing, documentation, and security audit.

Features:

- Classifies coding tasks by kind.
- Uses typed request/result structures.
- Supports caching.
- Retries LLM calls with backoff.
- Can validate Python, JavaScript, and shell syntax.
- Can generate unified diffs for refactors.
- Can produce files, code snippets, diffs, tests, security notes, and explanations.

Declared capabilities:

- Code generation across multiple languages.
- Code analysis and review.
- Debugging and error fixing.
- Refactoring with unified diffs.
- Unit test generation.
- Code explanation.
- Documentation generation.
- Security audit and hardening.
- Website scaffolding.
- Mermaid diagram generation.

### ImageAgent

Purpose: text-to-image generation.

Features:

- Cleans common prompt prefixes.
- Uses `ImageGenerator` under `BACKEND/data/generated_images`.
- Returns an `[IMAGE:http://localhost:8000/images/<file>]` marker that the frontend renders as an image preview.

Declared capabilities:

- Text-to-image generation.
- FLUX / Stable Diffusion model support.
- Custom illustrations.
- Photorealistic synthesis.

### AuditAgent

Purpose: quality control for agent outputs.

Features:

- Reviews task results after non-fast-route executions.
- Can cause the Brain to retry with audit feedback.
- Used after swarm delegation as well.

### ObserverAgent

Purpose: execution recovery and outcome assessment.

Features:

- Evaluates tool execution outcomes.
- Suggests recovery strategy after failures.
- Used directly by `SystemAgent`.

### ProjectBuilder and Swarm Sub-Agents

Purpose: complex project generation and multi-agent development workflows.

Registered sub-agent roles include:

- AnalysisAgent: requirements and dependency mapping.
- ArchitectureAgent: file structure and stack selection.
- SwarmCodingAgent: implementation.
- SwarmResearchAgent: technical research.
- DocumentationAgent: README and API docs.
- VulnerabilityAgent: static security hardening.
- RuntimeAgent: sandbox/runtime validation.
- ToolManagerAgent: dynamic tool creation and registry management.
- DelegatorAgent: task routing and orchestration.

The Brain registers these as metadata-backed sub-agents under `ProjectBuilderSystem`, and complex queries may be delegated to the swarm path.

## Tooling Features

The comprehensive tool registry exposes tools with metadata, required parameters, risk levels, and categories. A newer universal registry migrates these tools and adds dynamic tool loading.

### File and Shell Tools

Features:

- Read files.
- Write full file content.
- Edit files by replacement.
- Delete files or directories.
- List directories.
- Grep/search file contents.
- Execute shell commands.
- Read/list/find system files outside the local workspace when allowed by the runtime environment.
- Get file metadata.

Risk handling:

- Tools are tagged from safe to critical risk levels.
- Destructive or shell-execution tools are marked high/critical in metadata.

### System Automation Tools

Features:

- Open folders.
- Open apps or websites.
- Close apps.
- Close all apps with exceptions.
- Google search.
- YouTube search.
- Background YouTube/music playback through extension integration.
- Visible YouTube playback when explicitly requested.
- System controls such as mute, volume, shutdown, restart, and lock.
- Screenshot capture.
- Open local files with default or specified app.
- Write AI-generated content to a file.

### Research and Realtime Tools

Features:

- Web research with synthesis.
- Website scraping.
- Realtime search for news, weather, prices, and current events.
- Chat-with-AI tool for direct conversational fallback.

### RAG Knowledge Tools

Features:

- Index directories into a local knowledge base.
- Semantic search across indexed workspace files.
- RAG process/search/stats/memory endpoints.

### Vision Tools

Features:

- Analyze current screen content.
- OCR screen text.
- Analyze camera feed.
- Detect faces.
- Capture camera photos.
- Analyze arbitrary image files by path.

### Generation Tools

Features:

- Generate websites or apps from prompts.
- Generate diagrams as Mermaid-based widgets.
- Generate images.
- List generated images.
- Generate videos.
- List generated videos.
- Build complete projects through the project-builder swarm.
- Forge dynamic tools on demand when explicitly requested.

### File Conversion and Reporting Tools

Features:

- DOC/DOCX to PDF.
- PDF to DOCX/TXT/JSON.
- TXT to PDF/HTML/JSON.
- Markdown to HTML.
- HTML to PDF.
- CSV to JSON.
- JSON to CSV/TXT.
- XLS/XLSX to CSV/JSON.
- PNG/JPG/WEBP/BMP image conversions.
- Generate PDF reports from markdown content.

Implementation note:

- Some conversion paths depend on optional packages or external software such as LibreOffice, pdf2docx, python-docx, reportlab, pdfplumber, or an HTML-to-PDF backend.

### Workflow, Navigation, and Security-Layer Tools

Features:

- List available workflows.
- Run saved workflows.
- Check local security lock status.
- Open Google Maps.
- Get directions between two locations.

### Computer Use Tool

Purpose: UI automation through vision-guided interaction.

Features:

- Opens apps, clicks UI elements, types, and verifies actions through screen analysis.
- Exposed as `computer_use_task`.
- Marked high risk because it can control the local GUI.

## API Surface

Main endpoints:

- `GET /`: basic health.
- `GET /api/status`: status, agents, tool counts, memory counts, active tasks, neural readiness.
- `POST /api/chat`: primary chat endpoint.
- `GET /api/agents`: available agent descriptions.
- `GET /api/tools`: enabled universal tools.
- `POST /api/tools/execute`: execute a universal tool.
- `GET /api/chat/history`: read chat history.
- `POST /api/chat/clear`: clear chat history.
- `POST /api/os/execute`: compatibility OS engine execution.
- `GET /api/os/status`: task status.
- `GET /api/os/tools`: enabled OS tools.
- `GET /api/os/memory`: chat and task memory.
- `GET /api/execute/capabilities`: unified execution types and categories.
- `POST /api/execute`: unified dispatcher for chat, OS, tool, shell, RAG, and image tasks.
- `GET /api/gateway/health`: configured LLM provider status.
- Shell generation/description/execution endpoints under `/api/shell/*`.
- Cache/session/function endpoints for shell GPT bridge features.
- Image generation/list/model endpoints under `/api/images/*`.
- RAG endpoints under `/api/rag/*`.
- Security intelligence endpoints under `/api/security/*`.
- Music extension endpoints under `/api/music/*`.
- Overlay/extension endpoints under `/api/overlay/*`, `/ws/overlay`, and `/ws/extension-v2`.
- WebSocket chat endpoint at `/ws`.

## Frontend Feature Set

### Visual Interface

Features:

- Full-screen fixed interface.
- Animated particle background.
- Grid and ambient glow background.
- Custom glowing cursor.
- Animated central orb.
- Online/offline indicator based on backend `/api/status`.
- Idle and processing states.

### Chat Experience

Features:

- Slide-up chat panel.
- Backend chat-history loading.
- First-open greeting.
- Expand/minimize panel.
- Multi-stage thinking indicator:
  - analyzing query,
  - classifying intent,
  - routing to agent,
  - processing.
- Quick action buttons:
  - capabilities,
  - generate image,
  - full recon,
  - check SSL,
  - system info,
  - research.
- Textarea with Enter-to-send and Shift+Enter newline.
- Voice-mode simulation with listening pulse.

### Message Rendering

Features:

- Markdown rendering via `react-markdown`.
- GitHub-flavored markdown through `remark-gfm`.
- Styled headings, links, blockquotes, tables, lists, inline code.
- Fenced code blocks rendered with Prism syntax highlighting.
- Copy button on code blocks.
- Typewriter streaming effect for AI messages.
- Agent/intent badge on AI responses.
- Generated image rendering through `[IMAGE:url]` markers.

## AI Provider Layer

The AI engine unifies:

- Groq for fast chat and classification.
- Gemini for deeper reasoning and vision, when configured.
- Groq key rotation across multiple API keys.
- Groq fallback model support.
- Gemini fallback when Groq attempts fail.
- Groq fallback when Gemini reasoning fails.

Provider-dependent features:

- General chat and classification require Groq keys or Gemini fallback.
- Deep security reporting and reasoning are strongest with Gemini configured.
- Vision analysis requires Gemini vision support.

## Neural Engine

The neural core provides local ML support:

- TF-IDF vectorizer with up to 128 features.
- PyTorch `IntentClassifierNet`.
- PyTorch `AnomalyDetectorNet`.
- Startup load-or-train behavior for the intent model.
- Startup load of an anomaly model with default dimensions.
- CPU/CUDA/MPS device selection.

Current intent labels in `neural/core.py`:

- `chat`
- `realtime`
- `os_engine`

Brain-level valid intents:

- `chat`
- `security`
- `system`
- `research`
- `code`
- `image`

Important gap:

- The neural labels do not currently match the Brain's full intent schema. Because the Brain only accepts neural labels that are also valid Brain intents, neural fast-routing will mainly help for `chat` and will reject labels such as `realtime` and `os_engine` unless mapped to `research` and `system`.

## Memory and State

Persistent memory:

- Chat history is stored in `BACKEND/data/memory.json`.
- Task results are stored with generated task IDs.
- History is capped at 100 messages.
- Task results are capped at 50 tasks.
- Recent memory is injected into agent context.

Task state:

- `engine/state_manager.py` is used by tools and API endpoints to expose active/current task state.
- Tool execution updates global action labels such as searching, analyzing, reading, writing, generating, or idle.

## Security and Risk Controls

Implemented controls and metadata:

- Tool risk levels: safe, low, medium, high, critical.
- Permission/security modules exist under `services/security_layer.py`, `services/permission_enforcer.py`, and `tools/tool_permissions.py`.
- Dangerous tools such as shell execution, deletion, project building, computer use, and dynamic tool forging are marked high or critical.
- Audit and observer agents provide output-level verification and recovery support.
- Threat-intelligence modules add CVE/KEV collection, triage, zero-day probes, and narrative generation endpoints.

Residual risk:

- Tool metadata alone does not guarantee user approval enforcement for every path.
- `POST /api/tools/execute` can execute enabled universal tools directly if exposed without authentication.
- CORS is currently wide open in the API.
- GUI automation and shell execution are powerful and should be guarded in deployment.

## Security Intelligence Features

Dedicated endpoints and modules support:

- Threat intelligence collection.
- Threat intelligence summary.
- Critical CVE listing.
- Known exploited vulnerability listing.
- Threat-intel search.
- AI triage of findings.
- Zero-day scan probes:
  - request smuggling,
  - SSTI,
  - prototype pollution,
  - cache poisoning,
  - JWT weaknesses.
- Executive threat narrative generation.

## Workflow and Automation Features

Workflow support:

- Workflows are stored under `data/workflows` and `BACKEND/data/workflows`.
- Tooling can list and run saved workflows.
- Example workflow files include `research_workflow.json` and `morning_routine.json`.

Automation support:

- App launching.
- Browser search.
- YouTube/music controls.
- File operations.
- Command execution.
- UI automation.
- Map/directions opening.

## Content and Media Generation

Supported generation types:

- Images from prompts.
- Videos/animations from prompts.
- Websites and apps.
- Diagrams.
- Dynamic tools.
- PDF reports from markdown.
- AI-written file content.
- Code, tests, docs, and diffs.

Generated artifacts are stored under backend data directories such as:

- `BACKEND/data/generated_images`
- `BACKEND/data/reports`
- converter output directories

## Known Limitations and Gaps

1. Neural intent mismatch:
   The neural core uses `realtime` and `os_engine`, while the Brain expects `research` and `system`. Add a label mapping or retrain with the Brain's six intents.

2. SecurityAgent tool execution likely needs verification:
   `SecurityAgent.execute()` calls `tool_registry.execute(tool_name, params)` instead of expanding parameters as keyword args. The registry expects `execute(name, **kwargs)`. This can break planned security tool execution unless compatibility exists elsewhere.

3. ResearchAgent tool execution likely needs verification:
   `ResearchAgent.execute()` calls `tool_registry.execute("web_search", {"query": query, "max_results": 5})`, but the visible registry includes `web_research` and `realtime_search`; `web_search` may come from another module or may be missing.

4. CORS and direct tool execution are permissive:
   The API currently allows all origins and exposes direct tool execution. This is convenient for local development but not appropriate for a public deployment without authentication and authorization.

5. External dependencies are required:
   Groq, Gemini, Tavily, Hugging Face, Chrome extensions, PDF converters, OCR/camera libraries, and GUI automation dependencies may be required depending on feature path.

6. Frontend voice mode appears simulated:
   The current chat panel toggles a listening animation and inserts a placeholder "Voice input received" message, but no actual speech recognition pipeline is visible in the frontend component.

7. Some files contain mojibake/encoding artifacts:
   Several comments and UI labels show corrupted Unicode sequences. Functionality can still work, but presentation should be cleaned up.

8. Git repository boundary appears misconfigured:
   `git status` from the workspace tried to inspect parent/system-level paths. This suggests the workspace may not be a clean isolated Git repository.

## Feature Maturity Assessment

| Area | Status | Notes |
|---|---|---|
| FastAPI backend | Implemented | Broad endpoint coverage and singleton startup flow. |
| Brain orchestration | Implemented | Multi-agent routing, memory, retries, auditing. |
| Core chat | Implemented | Uses AI engine and memory context. |
| Frontend chat UI | Implemented | Markdown, syntax highlighting, image markers, status polling. |
| Tool registry | Implemented | Large tool surface with risk metadata and universal migration. |
| File conversion | Implemented, dependency-sensitive | Many routes require optional packages. |
| PDF report generation | Implemented in registry | Needs runtime conversion dependencies. |
| Image generation | Implemented, provider-sensitive | Depends on generation backend/API. |
| RAG | Implemented | Index/search endpoints and tools present. |
| Security intelligence | Implemented/partial | Endpoints and modules exist; scan tool wiring needs validation. |
| Neural routing | Partial | Model exists, but labels do not align with Brain intents. |
| Voice input | UI simulation | No clear browser speech-to-text integration in current component. |
| Chrome extension music/overlay | Backend hooks implemented | Requires extension client connection. |
| Dynamic tools/project builder | Implemented/high-risk | Powerful feature; needs permission controls in production. |

## Recommended Next Steps

1. Fix neural intent label alignment:
   Replace `realtime` with `research`, replace `os_engine` with `system`, and add training examples for `security`, `code`, and `image`.

2. Verify and fix tool execution signatures:
   Audit all `tool_registry.execute(...)` callers and ensure they pass keyword arguments.

3. Confirm security/research tool registration:
   Make sure names used by agents match names registered by `tool_registry` and `universal_registry`.

4. Add authentication/authorization before deployment:
   Protect shell, file, computer-use, dynamic-tool, project-builder, and direct tool execution endpoints.

5. Add a capabilities endpoint backed by the agent registry:
   The data exists in `agent_registry`; exposing it cleanly would help the UI and self-reporting.

6. Add runtime health checks for provider-dependent features:
   Report status for Groq, Gemini, Tavily, Hugging Face, OCR/camera, Chrome extension, and PDF conversion.

7. Clean UI encoding artifacts:
   Replace corrupted labels/icons with valid Unicode or ASCII-safe alternatives.

8. Add focused tests:
   Test Brain classification, chat endpoint, registry tool execution, PDF report generation, image marker rendering, and basic frontend build.

## Conclusion

AERIS is already structured as a capable autonomous assistant platform rather than a simple chatbot. Its strongest implemented features are multi-agent orchestration, a large tool registry, persistent memory, rich frontend rendering, AI provider abstraction, file/system automation, image generation integration, RAG support, and security-intelligence modules.

The most important engineering work is not adding more features; it is hardening the current feature surface. The immediate priorities are aligning neural routing with Brain intents, validating tool-name/signature consistency, tightening permissions around high-risk tools, confirming provider health at runtime, and cleaning frontend encoding issues.
