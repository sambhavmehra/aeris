"""
AERIS — Intelligent Diagram Generator (React Flow Version)
Uses LLM to convert any user input into a clean, animated React Flow diagram JSON
rendered as an interactive widget in the AERIS UI.
"""
from __future__ import annotations
import json
import logging
from typing import Dict, Any

logger = logging.getLogger("AerisDiagramGenerator")

# ═══════════════════════════════════════════════════════════════════
#  EXPERT DIAGRAM ARCHITECT SYSTEM PROMPT (REACT FLOW)
# ═══════════════════════════════════════════════════════════════════

DIAGRAM_SYSTEM_INSTRUCTION = r"""You are an expert visual system architect. Convert user input into a fully structured, visually rich, animated React Flow diagram JSON.

The output will be rendered on a live interactive canvas. Focus on clarity, layout, and visual hierarchy.

═══════════════════════════════════════
OUTPUT FORMAT (STRICT)
═══════════════════════════════════════
Return ONLY valid JSON:

{
"title": "Short Title",
"nodes": [],
"edges": []
}

No explanation. No markdown.

═══════════════════════════════════════
NODE STRUCTURE
═══════════════════════════════════════
Each node:

{
"id": "unique_id",
"data": { "label": "Short Label" },
"position": { "x": number, "y": number },
"type": "default",
"style": {
"background": "#color",
"color": "#textColor",
"borderRadius": "10px",
"padding": "10px",
"border": "1px solid rgba(255,255,255,0.2)",
"boxShadow": "0 4px 15px rgba(0,0,0,0.3)"
},
"className": "node-type"
}

═══════════════════════════════════════
EDGE STRUCTURE
═══════════════════════════════════════
Each edge:

{
"id": "e1-2",
"source": "node_id",
"target": "node_id",
"label": "optional",
"animated": true,
"style": { "strokeWidth": 2, "stroke": "#color" }
}

═══════════════════════════════════════
VISUAL SEMANTICS (MANDATORY)
═══════════════════════════════════════

* Start/End → Gray (Bg: #F1EFE8, Text: #444441)
* Process → Purple (Bg: #EEEDFE, Text: #3C3489)
* Decision → Amber (Bg: #FAEEDA, Text: #633806)
* Success → Green (Bg: #E1F5EE, Text: #085041)
* Error → Coral (Bg: #FAECE7, Text: #712B13)

Use max 3–4 colors. Edges should match their source node's border/stroke color (or a nice vibrant color like #8b5cf6).

═══════════════════════════════════════
LAYOUT RULES
═══════════════════════════════════════

* Use clean top-to-bottom or left-to-right structure
* Maintain spacing:
  X gap: 250
  Y gap: 120
* Avoid overlap
* Keep centered and balanced

═══════════════════════════════════════
GROUPING (SIMULATED SUBGRAPHS)
═══════════════════════════════════════

* Cluster related nodes together spatially
* Align them vertically or horizontally
* Maintain visual grouping via proximity

═══════════════════════════════════════
ANIMATION INTENT (IMPORTANT)
═══════════════════════════════════════

* Set "animated": true on important edges
* Flow should appear directional and progressive
* Keep node order logical for step-by-step animation
* Highlight main path clearly

═══════════════════════════════════════
INTELLIGENCE RULES
═══════════════════════════════════════

* Infer missing steps logically
* Add decision nodes where needed
* Label edges (Yes/No, Success/Fail)
* Keep max 8–12 nodes
* Clean vague input
"""

class DiagramGenerator:
    """
    Intelligent diagram generator that:
    1. Takes any user input (natural language)
    2. Sends it to the LLM to get React Flow JSON
    3. Wraps it in an interactive React Flow HTML widget
    """

    def generate_from_prompt(self, user_input: str) -> Dict[str, Any]:
        """Generate a diagram from natural language user input using LLM."""
        try:
            from ai_engine import ai_engine
            import asyncio
            
            def run_sync(coro):
                try:
                    return asyncio.run(coro)
                except RuntimeError:
                    import nest_asyncio
                    nest_asyncio.apply()
                    return asyncio.run(coro)

            messages = [
                {"role": "system", "content": DIAGRAM_SYSTEM_INSTRUCTION},
                {"role": "user", "content": f"Generate a visually structured, animation-ready React Flow diagram JSON for:\n\n{user_input}"},
            ]

            raw = run_sync(ai_engine.chat(messages, temperature=0.1, max_tokens=2048))

            # Parse JSON
            raw = raw.strip()
            if raw.startswith("```json"):
                raw = raw.split("```json")[-1].split("```")[0].strip()
            elif raw.startswith("```"):
                raw = raw.split("```")[-1].split("```")[0].strip()

            diagram_data = json.loads(raw)
            title = diagram_data.get("title", "Interactive Workflow")

            logger.info(f"Generated React Flow diagram: title='{title}', nodes={len(diagram_data.get('nodes', []))}")
            return self._build_widget(title, json.dumps(diagram_data))

        except Exception as e:
            logger.error(f"React Flow Diagram generation failed: {e}")
            fallback_data = {
                "title": "Error",
                "nodes": [
                    {"id": "1", "data": {"label": "Generation Error"}, "position": {"x": 100, "y": 100}, "style": {"background": "#FAECE7", "color": "#712B13"}}
                ],
                "edges": []
            }
            return self._build_widget("Error", json.dumps(fallback_data))


    def _build_widget(self, title: str, react_flow_json_str: str) -> Dict[str, Any]:
        """Build the animated HTML widget using React Flow CDN."""
        html_template = r"""<!DOCTYPE html>
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
    body { 
        margin: 0; padding: 0; height: 100vh; 
        background: transparent; 
        font-family: 'Inter', system-ui, sans-serif; 
    }
    #root { width: 100%; height: 100%; border-radius: 12px; overflow: hidden; }
    .title-overlay {
        position: absolute;
        top: 20px;
        left: 20px;
        z-index: 10;
        font-size: 20px;
        font-weight: 700;
        background: linear-gradient(135deg, #8b5cf6, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        pointer-events: none;
        background-color: rgba(15,15,30,0.8);
        padding: 8px 16px;
        border-radius: 8px;
        border: 1px solid rgba(139,92,246,0.3);
    }
    # .close-btn {
    #     position: absolute;
    #     top: 20px;
    #     right: 20px;
    #     z-index: 100;
    #     background-color: #ff4444;
    #     color: white;
    #     border: none;
    #     border-radius: 8px;
    #     padding: 8px 16px;
    #     font-size: 16px;
    #     font-weight: bold;
    #     cursor: pointer;
    #     box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    #     transition: 0.2s;
    # }
    # .close-btn:hover {
    #     background-color: #ff2222;
    #     transform: scale(1.05);
    # }
    
    /* Dark mode overrides for react flow background */
    .react-flow__background { background-color: rgba(10, 10, 25, 0.95); }
    .react-flow__controls button { background-color: #1a1a2e; border-bottom-color: #333; fill: #eee; }
    .react-flow__controls button:hover { background-color: #2a2a4e; }
  </style>
</head>
<body>
  <div class="title-overlay">__TITLE__</div>
  <button class="close-btn" onclick="window.close()">✖ Close</button>
  <div id="root"></div>
  <script type="text/babel">
    const { useState, useCallback, useEffect } = React;
    const { ReactFlow, Background, Controls, applyNodeChanges, applyEdgeChanges, MarkerType } = window.ReactFlow;

    const initialData = __REACT_FLOW_JSON__;
    
    // Process edges to ensure nice arrows and styling
    const processedEdges = (initialData.edges || []).map((e, index) => ({
      ...e,
      markerEnd: { 
          type: MarkerType.ArrowClosed, 
          color: e.style?.stroke || '#8b5cf6',
          width: 20,
          height: 20
      },
      style: {
          ...e.style,
          stroke: e.style?.stroke || '#8b5cf6',
          strokeWidth: e.style?.strokeWidth || 2
      }
    }));

    // Process nodes to ensure text contrasts well
    const processedNodes = (initialData.nodes || []).map(n => {
        // If node style has background, ensure color is readable
        let style = { ...n.style };
        if (!style.padding) style.padding = '12px 20px';
        if (!style.borderRadius) style.borderRadius = '12px';
        if (!style.fontSize) style.fontSize = '14px';
        if (!style.fontWeight) style.fontWeight = '500';
        if (!style.boxShadow) style.boxShadow = '0 4px 15px rgba(0,0,0,0.2)';
        if (!style.border) style.border = '1px solid rgba(255,255,255,0.1)';
        
        return { ...n, style };
    });

    function Flow() {
      const [nodes, setNodes] = useState(processedNodes);
      const [edges, setEdges] = useState(processedEdges);

      const onNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), []);
      const onEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), []);

      return (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          maxZoom={2}
          defaultEdgeOptions={{ animated: true }}
        >
          <Background color="#333" gap={16} size={1} />
          <Controls />
        </ReactFlow>
      );
    }

    ReactDOM.createRoot(document.getElementById('root')).render(<Flow />);
  </script>
</body>
</html>"""

        html_content = html_template.replace("__TITLE__", title).replace("__REACT_FLOW_JSON__", react_flow_json_str)

        try:
            import os
            import sys
            import subprocess
            from pathlib import Path
            import uuid
            
            output_dir = Path("data/generated_diagrams")
            output_dir.mkdir(parents=True, exist_ok=True)
            file_path = output_dir / f"diagram_{uuid.uuid4().hex[:6]}.html"
            file_path.write_text(html_content, encoding="utf-8")
            
            file_uri = file_path.absolute().as_uri()
            
            # Pop up a sleek UI window using browser app mode
            if sys.platform == "win32":
                subprocess.Popen(["cmd", "/c", "start", "msedge", f"--app={file_uri}"], creationflags=0x08000000)
            else:
                import webbrowser
                webbrowser.open(file_uri)
        except Exception as e:
            logger.warning(f"Failed to pop up diagram UI: {e}")

        return {
            "success": True,
            "site_type": "widget",
            "files": [{"content": html_content}],
            "output": f"Generated interactive React Flow diagram widget: {title} (Opened in UI)"
        }
