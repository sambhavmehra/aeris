"""
AERIS — Diagram Agent
=====================
Converts any natural language request (flowcharts, system diagrams,
architecture charts, mind maps) into an interactive React Flow widget
rendered inline in the AERIS chat panel as an HTML iframe.

Adapted from Sharva OS diagram_generator.py, re-built for AERIS architecture.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from ai_engine import ai_engine

logger = logging.getLogger("aeris.diagram_agent")

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — same expert approach as Sharva's diagram generator
# ─────────────────────────────────────────────────────────────────────────────

DIAGRAM_SYSTEM_PROMPT = r"""You are an expert visual system architect embedded inside AERIS AI.
Convert any user request into a fully structured, visually rich, animated React Flow diagram JSON.

OUTPUT FORMAT (STRICT) — Return ONLY valid JSON, no markdown fences, no explanation:

{
  "title": "Short Title",
  "nodes": [],
  "edges": []
}

NODE STRUCTURE — each node:
{
  "id": "unique_id",
  "data": { "label": "Short Label" },
  "position": { "x": number, "y": number },
  "type": "default",
  "style": {
    "background": "#hex",
    "color": "#hex",
    "borderRadius": "10px",
    "padding": "12px 20px",
    "border": "1px solid rgba(255,255,255,0.15)",
    "boxShadow": "0 4px 15px rgba(0,0,0,0.3)",
    "fontSize": "13px",
    "fontWeight": "500"
  }
}

EDGE STRUCTURE — each edge:
{
  "id": "e1-2",
  "source": "node_id",
  "target": "node_id",
  "label": "optional",
  "animated": true,
  "style": { "strokeWidth": 2, "stroke": "#hex" }
}

VISUAL COLOUR SEMANTICS (mandatory):
  Start/End   → Background #F1EFE8, Text #444441
  Process     → Background #0d1117, Text #00d4ff, Border rgba(0,212,255,0.3)
  Decision    → Background #1a0f2e, Text #c084fc, Border rgba(192,132,252,0.4)
  Success     → Background #0a1f12, Text #34d399, Border rgba(52,211,153,0.4)
  Error       → Background #1f0a0a, Text #f87171, Border rgba(248,113,113,0.4)
  Use AERIS cyber/dark theme colours — deep blues, cyans, purples

LAYOUT RULES:
  * Top-to-bottom OR left-to-right flow
  * X gap: 260, Y gap: 130
  * No overlapping nodes
  * Keep balanced and centered

ANIMATION: set "animated": true on key edges

INTELLIGENCE: Infer missing steps, add decision diamonds, label edges Yes/No or Success/Fail.
Keep 5-14 nodes. Clean up vague requests.
"""

# ─────────────────────────────────────────────────────────────────────────────
# HTML widget template (React Flow via CDN, no build step needed)
# ─────────────────────────────────────────────────────────────────────────────

_WIDGET_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>__TITLE__</title>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/reactflow@11.10.3/dist/umd/index.js"></script>
  <link rel="stylesheet" href="https://unpkg.com/reactflow@11.10.3/dist/style.css" />
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 0; height: 100vh; background: rgba(3,9,25,0.97); font-family: 'Inter', system-ui, sans-serif; }
    #root { width: 100%; height: 100%; }
    .title-overlay {
      position: absolute; top: 14px; left: 14px; z-index: 10;
      font-size: 13px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
      background: linear-gradient(135deg, #00d4ff, #8b5cf6);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      padding: 6px 14px;
      background-color: rgba(3,9,25,0.85);
      border-radius: 8px; border: 1px solid rgba(0,212,255,0.2);
      pointer-events: none;
    }
    .react-flow__background { background-color: rgba(3,9,25,0.97) !important; }
    .react-flow__controls button { background: #070f2b; border-bottom-color: rgba(0,212,255,0.15); fill: #00d4ff; }
    .react-flow__controls button:hover { background: #0d1a3a; }
    .react-flow__edge-text { fill: rgba(200,240,255,0.7); font-size: 11px; }
  </style>
</head>
<body>
  <div class="title-overlay">__TITLE__</div>
  <div id="root"></div>
  <script type="text/babel">
    const { useState, useCallback } = React;
    const { ReactFlow, Background, Controls, MiniMap, applyNodeChanges, applyEdgeChanges, MarkerType } = window.ReactFlow;

    const raw = __REACT_FLOW_JSON__;

    const processedEdges = (raw.edges || []).map(e => ({
      ...e,
      markerEnd: { type: MarkerType.ArrowClosed, color: e.style?.stroke || '#00d4ff', width: 18, height: 18 },
      style: { stroke: '#00d4ff', strokeWidth: 2, ...e.style },
    }));

    const processedNodes = (raw.nodes || []).map(n => ({
      ...n,
      style: {
        background: 'rgba(0,212,255,0.06)',
        color: 'rgba(200,240,255,0.9)',
        borderRadius: '10px',
        padding: '10px 18px',
        border: '1px solid rgba(0,212,255,0.2)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
        fontSize: '12.5px',
        fontWeight: '500',
        minWidth: '120px',
        textAlign: 'center',
        ...n.style,
      }
    }));

    function Flow() {
      const [nodes, setNodes] = useState(processedNodes);
      const [edges, setEdges] = useState(processedEdges);
      const onNodesChange = useCallback(c => setNodes(ns => applyNodeChanges(c, ns)), []);
      const onEdgesChange = useCallback(c => setEdges(es => applyEdgeChanges(c, es)), []);
      return (
        <ReactFlow
          nodes={nodes} edges={edges}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          fitView fitViewOptions={{ padding: 0.25 }}
          minZoom={0.15} maxZoom={2.5}
          defaultEdgeOptions={{ animated: true }}
          style={{ background: 'transparent' }}
        >
          <Background color="rgba(0,212,255,0.06)" gap={24} size={1} />
          <Controls />
          <MiniMap nodeColor={() => '#00d4ff'} maskColor="rgba(3,9,25,0.8)" style={{ background: 'rgba(7,15,43,0.9)', border: '1px solid rgba(0,212,255,0.15)' }} />
        </ReactFlow>
      );
    }

    ReactDOM.createRoot(document.getElementById('root')).render(<Flow />);
  </script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class DiagramAgent:
    """
    Generates interactive React Flow diagram widgets from natural language.
    Returns a special [WIDGET:...] marker in the response text that the
    AERIS frontend renders as an inline iframe.
    """

    async def generate(self, user_input: str) -> str:
        """
        Main entry — call this from brain.py codepipeline or a new 'diagram' intent.
        Returns a response string containing a [WIDGET:<escaped_html>] marker.
        """
        logger.info(f"[DiagramAgent] Generating diagram for: {user_input[:100]}")
        try:
            raw = await ai_engine.chat(
                messages=[
                    {"role": "system", "content": DIAGRAM_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Generate a visually structured React Flow diagram JSON for:\n\n{user_input}"},
                ],
                temperature=0.1,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )

            data = json.loads(raw.strip())
            title = data.get("title", "Interactive Diagram")
            nodes_count = len(data.get("nodes", []))
            logger.info(f"[DiagramAgent] Parsed diagram: title='{title}', nodes={nodes_count}")

            html = self._build_html(title, json.dumps(data))
            import urllib.parse
            encoded = urllib.parse.quote(html, safe='')
            return (
                f"📊 **{title}**\n\n"
                f"Here's your interactive diagram — you can drag nodes, zoom, and pan!\n\n"
                f"[WIDGET:{encoded}]"
            )

        except Exception as e:
            logger.error(f"[DiagramAgent] Failed: {e}")
            return f"❌ Could not generate diagram: {e}"

    def _build_html(self, title: str, react_flow_json_str: str) -> str:
        return (
            _WIDGET_HTML
            .replace("__TITLE__", title)
            .replace("__REACT_FLOW_JSON__", react_flow_json_str)
        )


# Singleton
_diagram_agent: DiagramAgent | None = None

def get_diagram_agent() -> DiagramAgent:
    global _diagram_agent
    if _diagram_agent is None:
        _diagram_agent = DiagramAgent()
    return _diagram_agent
