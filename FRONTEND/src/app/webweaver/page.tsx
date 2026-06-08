"use client";

import React, { useState, useEffect, useRef } from 'react';

interface NetworkNode {
  id: string;
  label: string;
  type: string;
  ip?: string;
  status: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

interface NetworkLink {
  source: string;
  target: string;
  type: string;
  port?: number;
}

interface NodeChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}



// Graph styling configuration based on node type
const getTypeColor = (type: string) => {
  switch (type.toLowerCase()) {
    case 'host': return '#7c4dff'; // Purple
    case 'service': return '#00e5ff'; // Cyan
    case 'subdomain': return '#2979ff'; // Blue
    case 'port': return '#ff9100'; // Orange
    case 'vulnerability': return '#ff1744'; // Red
    case 'credential': return '#ffd600'; // Yellow
    default: return '#00e676'; // Green
  }
};

const getTypeIcon = (type: string) => {
  switch (type.toLowerCase()) {
    case 'host': return '🖥️';
    case 'service': return '⚙️';
    case 'subdomain': return '🌐';
    case 'port': return '🔌';
    case 'vulnerability': return '🚨';
    case 'credential': return '🔑';
    default: return '📦';
  }
};

interface NetworkGraphViewProps {
  nodes: NetworkNode[];
  links: NetworkLink[];
  selectedNode: NetworkNode | null;
  setSelectedNode: (node: NetworkNode | null) => void;
  showSystemNodes: boolean;
}

const NetworkGraphView = React.memo(function NetworkGraphView({
  nodes,
  links,
  selectedNode,
  setSelectedNode,
  showSystemNodes
}: NetworkGraphViewProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<number | null>(null);
  const nodesStateRef = useRef<NetworkNode[]>([]);
  const dimensionsRef = useRef({ width: 800, height: 600 });
  const dragStartRef = useRef<{ x: number, y: number } | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);

  // Update dimensions on mount and resize
  useEffect(() => {
    const updateDimensions = () => {
      if (svgRef.current) {
        dimensionsRef.current = {
          width: svgRef.current.clientWidth || 800,
          height: svgRef.current.clientHeight || 600
        };
      }
    };
    updateDimensions();
    const timer = setTimeout(updateDimensions, 150);
    window.addEventListener('resize', updateDimensions);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateDimensions);
    };
  }, []);

  // Sync prop nodes to ref, keeping old coordinates
  useEffect(() => {
    const width = dimensionsRef.current.width;
    const height = dimensionsRef.current.height;
    const existingMap = new Map(nodesStateRef.current.map(n => [n.id, n]));

    const initializedNodes = nodes.map(node => {
      const existing = existingMap.get(node.id);
      return {
        ...node,
        x: existing?.x ?? (width / 2 + (Math.random() - 0.5) * 200),
        y: existing?.y ?? (height / 2 + (Math.random() - 0.5) * 200),
        vx: existing?.vx ?? 0,
        vy: existing?.vy ?? 0,
      };
    });

    nodesStateRef.current = initializedNodes;
  }, [nodes]);

  // Run force-directed layout simulation locally, updating DOM elements directly
  useEffect(() => {
    const runPhysics = () => {
      const width = dimensionsRef.current.width;
      const height = dimensionsRef.current.height;
      const centerX = width / 2;
      const centerY = height / 2;

      const currentNodes = nodesStateRef.current;
      if (currentNodes.length === 0) {
        simulationRef.current = requestAnimationFrame(runPhysics);
        return;
      }

      const repulsionStrength = 120000;
      const repulsionRadius = 450;
      const linkStrength = 0.04;
      const desiredLinkDist = 220;
      const gravity = 0.003;
      const friction = 0.82;

      const visibleNodes = currentNodes.filter(n => 
        showSystemNodes || (n.id !== 'aeris_brain' && n.id !== 'api_gateway')
      );

      // 1. Repulsion
      for (let i = 0; i < visibleNodes.length; i++) {
        const u = visibleNodes[i];
        if (u.id === draggedNodeId) continue;

        for (let j = 0; j < visibleNodes.length; j++) {
          if (i === j) continue;
          const v = visibleNodes[j];
          let dx = (u.x || 0) - (v.x || 0);
          let dy = (u.y || 0) - (v.y || 0);
          
          if (dx === 0 && dy === 0) {
            dx = (Math.random() - 0.5) * 2;
            dy = (Math.random() - 0.5) * 2;
          }
          
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;

          if (dist < repulsionRadius) {
            const force = repulsionStrength / (dist * dist);
            u.vx = (u.vx || 0) + (dx / dist) * force;
            u.vy = (u.vy || 0) + (dy / dist) * force;
          }

          if (dist < 120) {
            const extraPush = (120 - dist) * 2.0;
            u.vx = (u.vx || 0) + (dx / dist) * extraPush;
            u.vy = (u.vy || 0) + (dy / dist) * extraPush;
          }
        }
      }

      // 2. Link attraction
      const visibleLinks = links.filter(l => {
        const sourceVisible = showSystemNodes || (l.source !== 'aeris_brain' && l.source !== 'api_gateway');
        const targetVisible = showSystemNodes || (l.target !== 'aeris_brain' && l.target !== 'api_gateway');
        return sourceVisible && targetVisible;
      });

      visibleLinks.forEach(link => {
        const sourceNode = visibleNodes.find(n => n.id === link.source);
        const targetNode = visibleNodes.find(n => n.id === link.target);

        if (sourceNode && targetNode) {
          const dx = (targetNode.x || 0) - (sourceNode.x || 0);
          const dy = (targetNode.y || 0) - (sourceNode.y || 0);
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - desiredLinkDist) * linkStrength;

          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          if (sourceNode.id !== draggedNodeId) {
            sourceNode.vx = (sourceNode.vx || 0) + fx;
            sourceNode.vy = (sourceNode.vy || 0) + fy;
          }
          if (targetNode.id !== draggedNodeId) {
            targetNode.vx = (targetNode.vx || 0) - fx;
            targetNode.vy = (targetNode.vy || 0) - fy;
          }
        }
      });

      // 3. Gravity center pull + boundaries + apply velocity
      visibleNodes.forEach(u => {
        if (u.id === draggedNodeId) return;

        const dx = centerX - (u.x || 0);
        const dy = centerY - (u.y || 0);

        u.vx = ((u.vx || 0) + dx * gravity) * friction;
        u.vy = ((u.vy || 0) + dy * gravity) * friction;

        u.x = (u.x || 0) + u.vx;
        u.y = (u.y || 0) + u.vy;

        u.x = Math.max(60, Math.min(width - 60, u.x));
        u.y = Math.max(60, Math.min(height - 60, u.y));
      });

      // 4. Directly update DOM nodes and links
      visibleNodes.forEach(u => {
        const nodeEl = document.getElementById(`node-group-${u.id}`);
        if (nodeEl) {
          nodeEl.setAttribute('transform', `translate(${u.x || 0}, ${u.y || 0})`);
        }
      });

      visibleLinks.forEach(link => {
        const sourceNode = visibleNodes.find(n => n.id === link.source);
        const targetNode = visibleNodes.find(n => n.id === link.target);

        if (sourceNode && targetNode) {
          const x1 = sourceNode.x || 0;
          const y1 = sourceNode.y || 0;
          const x2 = targetNode.x || 0;
          const y2 = targetNode.y || 0;

          const linkGroup = document.getElementById(`link-group-${link.source}-${link.target}`);
          if (linkGroup) {
            const lines = linkGroup.getElementsByTagName('line');
            for (let i = 0; i < lines.length; i++) {
              lines[i].setAttribute('x1', String(x1));
              lines[i].setAttribute('y1', String(y1));
              lines[i].setAttribute('x2', String(x2));
              lines[i].setAttribute('y2', String(y2));
            }
            const text = linkGroup.querySelector('.link-text');
            if (text) {
              text.setAttribute('x', String((x1 + x2) / 2));
              text.setAttribute('y', String((y1 + y2) / 2 - 4));
            }
          }
        }
      });

      simulationRef.current = requestAnimationFrame(runPhysics);
    };

    simulationRef.current = requestAnimationFrame(runPhysics);
    return () => {
      if (simulationRef.current) cancelAnimationFrame(simulationRef.current);
    };
  }, [links, draggedNodeId, showSystemNodes]);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!draggedNodeId || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const node = nodesStateRef.current.find(n => n.id === draggedNodeId);
    if (node) {
      node.x = mouseX;
      node.y = mouseY;
      node.vx = 0;
      node.vy = 0;

      const nodeEl = document.getElementById(`node-group-${draggedNodeId}`);
      if (nodeEl) {
        nodeEl.setAttribute('transform', `translate(${mouseX}, ${mouseY})`);
      }
    }
  };

  const handleMouseUp = () => {
    setDraggedNodeId(null);
  };

  const visibleNodes = nodes.filter(node => 
    showSystemNodes || (node.id !== 'aeris_brain' && node.id !== 'api_gateway')
  );

  const visibleLinks = links.filter(link => {
    const sourceVisible = showSystemNodes || (link.source !== 'aeris_brain' && link.source !== 'api_gateway');
    const targetVisible = showSystemNodes || (link.target !== 'aeris_brain' && link.target !== 'api_gateway');
    return sourceVisible && targetVisible;
  });

  return (
    <svg 
      ref={svgRef}
      style={{ width: '100%', height: '100%', cursor: 'grab' }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <defs>
        {/* Neon glowing filters */}
        <filter id="glow-purple" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur1" />
          <feMerge>
            <feMergeNode in="blur1" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        
        {/* Connection line glow */}
        <linearGradient id="edge-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#7c4dff" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#00e5ff" stopOpacity="0.4" />
        </linearGradient>
      </defs>

      {/* Render Links */}
      {visibleLinks.map((link, idx) => {
        const sourceNode = nodes.find(n => n.id === link.source);
        const targetNode = nodes.find(n => n.id === link.target);

        if (!sourceNode || !targetNode) return null;

        const x1 = sourceNode.x || (dimensionsRef.current.width / 2);
        const y1 = sourceNode.y || (dimensionsRef.current.height / 2);
        const x2 = targetNode.x || (dimensionsRef.current.width / 2);
        const y2 = targetNode.y || (dimensionsRef.current.height / 2);

        return (
          <g key={`l-${idx}`} id={`link-group-${link.source}-${link.target}`}>
            {/* Shadow wider connector line */}
            <line 
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="#7c4dff" strokeWidth={3} strokeOpacity={0.12}
            />
            {/* Glowing link */}
            <line 
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="url(#edge-gradient)" strokeWidth={1.5}
            />
            {/* Port speed text (if applicable) */}
            {link.port && (
              <text 
                x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 4}
                fill="#ff9100" fontSize="8px" textAnchor="middle"
                className="link-text"
                style={{ fontFamily: 'inherit', fontWeight: 'bold' }}
              >
                :{link.port}
              </text>
            )}
          </g>
        );
      })}

      {/* Render Nodes */}
      {visibleNodes.map(node => {
        const color = getTypeColor(node.type);
        const isSelected = selectedNode?.id === node.id;
        const initialX = node.x || (dimensionsRef.current.width / 2);
        const initialY = node.y || (dimensionsRef.current.height / 2);
        
        return (
          <g 
            key={node.id}
            id={`node-group-${node.id}`}
            transform={`translate(${initialX}, ${initialY})`}
            style={{ cursor: 'pointer' }}
            onMouseDown={(e) => {
              e.stopPropagation();
              setDraggedNodeId(node.id);
              dragStartRef.current = { x: e.clientX, y: e.clientY };
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (dragStartRef.current) {
                const dx = e.clientX - dragStartRef.current.x;
                const dy = e.clientY - dragStartRef.current.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                if (distance > 5) return;
              }
              setSelectedNode(node);
            }}
          >
            {/* Node Selection Glow */}
            {isSelected && (
              <circle r={24} fill="none" stroke="#00e5ff" strokeWidth={1} strokeDasharray="3 3">
                <animateTransform 
                  attributeName="transform" type="rotate"
                  from="0" to="360" dur="8s" repeatCount="indefinite"
                />
              </circle>
            )}

            {/* Outer ambient glow circle */}
            <circle 
              r={15} fill={color} fillOpacity={0.15}
              stroke={color} strokeWidth={1} strokeOpacity={0.4}
              filter="url(#glow-purple)"
            />

            {/* Core node circle */}
            <circle 
              r={10} fill="#0d0a1b" stroke={color} strokeWidth={2}
            />

            {/* Type icon symbol */}
            <text 
              y={3.5} textAnchor="middle" fontSize="9px"
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {getTypeIcon(node.type)}
            </text>

            {/* Dynamic-sized Node label and IP card */}
            {(() => {
              const labelLength = node.label.length;
              const ipLength = node.ip ? node.ip.length : 0;
              const maxTextLength = Math.max(labelLength, ipLength);
              // Calculate dynamic width based on text length (approx 6.5px per character + padding)
              const cardWidth = Math.max(120, maxTextLength * 6.5 + 16);
              const hasIp = !!node.ip;
              const cardHeight = hasIp ? 30 : 18;
              const rectY = hasIp ? -10 : -9;

              return (
                <g transform="translate(0, 24)">
                  <rect 
                    x={-cardWidth / 2} y={rectY} width={cardWidth} height={cardHeight} rx={4}
                    fill="rgba(6, 4, 15, 0.94)" 
                    stroke={color} 
                    strokeWidth={1} 
                    strokeOpacity={0.6}
                  />
                  {hasIp ? (
                    <>
                      <text 
                        fill="#fff" fontSize="8.5px" textAnchor="middle" y={2}
                        style={{ fontWeight: 'bold', userSelect: 'none' }}
                      >
                        {node.label}
                      </text>
                      <text 
                        fill="rgba(255, 255, 255, 0.5)" fontSize="7.5px" textAnchor="middle" y={13}
                        style={{ userSelect: 'none', fontFamily: 'monospace' }}
                      >
                        {node.ip}
                      </text>
                    </>
                  ) : (
                    <text 
                      fill="#fff" fontSize="8.5px" textAnchor="middle" y={3}
                      style={{ fontWeight: 'bold', userSelect: 'none' }}
                    >
                      {node.label}
                    </text>
                  )}
                </g>
              );
            })()}
          </g>
        );
      })}
    </svg>
  );
});

export default function WebWeaverHUD() {
  const [nodes, setNodes] = useState<NetworkNode[]>([]);
  const [links, setLinks] = useState<NetworkLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null);
  const [showSystemNodes, setShowSystemNodes] = useState(true);
  const [nodeChats, setNodeChats] = useState<Record<string, NodeChatMessage[]>>({});
  const [nodeChatInput, setNodeChatInput] = useState('');
  const [isNodeChatSending, setIsNodeChatSending] = useState(false);
  const [hasInitializedSystemNodesVisibility, setHasInitializedSystemNodesVisibility] = useState(false);
  
  // Custom target node form state
  const [newNodeId, setNewNodeId] = useState('');
  const [newNodeLabel, setNewNodeLabel] = useState('');
  const [newNodeType, setNewNodeType] = useState('host');
  const [newNodeIp, setNewNodeIp] = useState('');
  const [newNodeParentId, setNewNodeParentId] = useState('');
  const [newNodePort, setNewNodePort] = useState('');
  const [formMsg, setFormMsg] = useState('');

  // Recon Scan launcher form state
  const [reconDomain, setReconDomain] = useState('');
  const [reconLimit, setReconLimit] = useState(50);
  const [isReconScanning, setIsReconScanning] = useState(false);
  const [reconStatus, setReconStatus] = useState('');

  // Search filter
  const [searchQuery, setSearchQuery] = useState('');

  const nodeChatEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll chat history inside node inspector
  useEffect(() => {
    if (nodeChatEndRef.current) {
      nodeChatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [nodeChats, selectedNode]);

  // Load initial graph data
  const fetchGraph = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/webweaver/graph');
      const data = await res.json();
      
      // Dynamically initialize system nodes visibility on first load
      if (!hasInitializedSystemNodesVisibility && data.nodes.length > 0) {
        const hasExternalNodes = data.nodes.some(
          (n: any) => n.id !== 'aeris_brain' && n.id !== 'api_gateway'
        );
        if (hasExternalNodes) {
          setShowSystemNodes(false);
        } else {
          setShowSystemNodes(true);
        }
        setHasInitializedSystemNodesVisibility(true);
      }

      setNodes(data.nodes);
      setLinks(data.links);
      setLoading(false);
    } catch (e) {
      console.error("Failed to load WebWeaver graph data", e);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph();
    // Poll updates every 6s
    const interval = setInterval(fetchGraph, 6000);
    return () => clearInterval(interval);
  }, []);

  const handleClearGraph = async () => {
    if (!confirm("Are you sure you want to clear the scan map? This resets the HUD to default system nodes.")) return;
    try {
      const res = await fetch('http://localhost:8000/api/webweaver/clear', {
        method: 'POST'
      });
      const data = await res.json();
      if (data.success) {
        setNodes([]);
        setLinks([]);
        fetchGraph();
      } else {
        alert("Failed to clear graph: " + (data.error || "Unknown error"));
      }
    } catch (err: any) {
      alert("Error clearing graph: " + err.message);
    }
  };

  const handleLaunchRecon = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reconDomain.trim()) {
      setReconStatus('Error: Target domain required');
      return;
    }
    setIsReconScanning(true);
    setReconStatus('Initializing scan pipeline...');
    try {
      const res = await fetch('http://localhost:8000/api/tools/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: 'subdomain_enum',
          args: {
            domain: reconDomain.trim(),
            limit: reconLimit
          }
        })
      });
      const data = await res.json();
      if (data.success) {
        setReconStatus('Scan completed successfully!');
        setReconDomain('');
        fetchGraph();
      } else {
        setReconStatus(`Scan failed: ${data.error || 'Unknown error'}`);
      }
    } catch (err: any) {
      setReconStatus(`Scan error: ${err.message}`);
    } finally {
      setIsReconScanning(false);
    }
  };

  const handleSendNodeChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedNode || !nodeChatInput.trim() || isNodeChatSending) return;

    const msgText = nodeChatInput.trim();
    setNodeChatInput('');
    setIsNodeChatSending(true);

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const userMsg: NodeChatMessage = { role: 'user', content: msgText, timestamp };

    setNodeChats(prev => ({
      ...prev,
      [selectedNode.id]: [...(prev[selectedNode.id] || []), userMsg]
    }));

    try {
      const contextualMessage = `${msgText} (Context: node "${selectedNode.id}" with IP "${selectedNode.ip || 'N/A'}")`;
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: contextualMessage }),
      });

      if (!res.ok) throw new Error('Failed to communicate with neural core.');

      const data = await res.json();
      const assistantTimestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const assistantMsg: NodeChatMessage = {
        role: 'assistant',
        content: data.response || 'No response received from neural core.',
        timestamp: assistantTimestamp
      };

      setNodeChats(prev => ({
        ...prev,
        [selectedNode.id]: [...(prev[selectedNode.id] || []), assistantMsg]
      }));

      // Automatically reload the graph database after commands finish in case new nodes/links were mapped
      fetchGraph();
    } catch (err: any) {
      const errorTimestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const errorMsg: NodeChatMessage = {
        role: 'assistant',
        content: `Error: ${err.message || 'Could not connect to AERIS neural core.'}`,
        timestamp: errorTimestamp
      };
      setNodeChats(prev => ({
        ...prev,
        [selectedNode.id]: [...(prev[selectedNode.id] || []), errorMsg]
      }));
    } finally {
      setIsNodeChatSending(false);
    }
  };

  // Submit form to add node
  const handleAddNode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNodeId || !newNodeLabel) {
      setFormMsg('Error: ID and Label are required');
      return;
    }
    
    setFormMsg('Registering node...');
    try {
      const payload: any = {
        id: newNodeId.trim().toLowerCase(),
        label: newNodeLabel.trim(),
        type: newNodeType,
        status: 'online'
      };

      if (newNodeIp) payload.ip = newNodeIp.trim();
      if (newNodeParentId) payload.parent_id = newNodeParentId.trim().toLowerCase();
      if (newNodePort) payload.port = parseInt(newNodePort);

      const res = await fetch('http://localhost:8000/api/webweaver/node', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        setFormMsg('Node successfully mapped!');
        setNewNodeId('');
        setNewNodeLabel('');
        setNewNodeIp('');
        setNewNodeParentId('');
        setNewNodePort('');
        fetchGraph();
      } else {
        setFormMsg(`Failed: ${data.error || 'Unknown error'}`);
      }
    } catch (err: any) {
      setFormMsg(`Error: ${err.message}`);
    }
  };

  // Copy node value and notify
  const copyToClipboard = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    alert(`Copied ${type} to clipboard: "${text}"`);
  };

  // Filtered nodes based on search and system nodes visibility
  const filteredNodes = nodes.filter(n => {
    const matchesSearch = n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          n.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          (n.ip && n.ip.includes(searchQuery));
    const isSystem = n.id === 'aeris_brain' || n.id === 'api_gateway';
    return matchesSearch && (showSystemNodes || !isSystem);
  });

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'radial-gradient(circle at center, #080614 0%, #030206 100%)',
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      color: '#fff', overflow: 'hidden', display: 'flex', flexDirection: 'column'
    }}>
      {/* HUD Scanner lines effect */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 1,
        background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%)',
        backgroundSize: '100% 4px'
      }} />

      {/* Grid overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: 'linear-gradient(rgba(124, 77, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(124, 77, 255, 0.03) 1px, transparent 1px)',
        backgroundSize: '40px 40px', backgroundPosition: 'center'
      }} />

      {/* Top Header bar */}
      <header style={{
        height: '56px', borderBottom: '1px solid rgba(124, 77, 255, 0.15)',
        backdropFilter: 'blur(12px)', background: 'rgba(6, 4, 15, 0.8)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 20px', zIndex: 10, position: 'relative'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <a href="/" style={{
            textDecoration: 'none', color: 'rgba(255,255,255,0.6)',
            fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px',
            border: '1px solid rgba(255,255,255,0.1)', padding: '4px 10px',
            borderRadius: '4px', background: 'rgba(255,255,255,0.02)',
            transition: '0.2s', cursor: 'pointer'
          }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = 'rgba(124, 77, 255, 0.5)'}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'}
          >
            ← BACK
          </a>
          <h1 style={{
            fontSize: '13px', fontWeight: 900, letterSpacing: '3px',
            background: 'linear-gradient(90deg, #7c4dff 0%, #00e5ff 100%)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            textTransform: 'uppercase', margin: 0
          }}>
            AERIS WEBWEAVER HUD
          </h1>
          <span style={{
            background: 'rgba(124, 77, 255, 0.15)', border: '1px solid rgba(124, 77, 255, 0.4)',
            color: '#7c4dff', fontSize: '9px', fontWeight: 800, padding: '2px 8px',
            borderRadius: '10px', letterSpacing: '1px'
          }}>
            HUD ONLINE
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '20px', fontSize: '10px', color: 'rgba(255,255,255,0.6)' }}>
          <div>NODES: <span style={{ color: '#00e5ff', fontWeight: 'bold' }}>{nodes.length}</span></div>
          <div>LINKS: <span style={{ color: '#7c4dff', fontWeight: 'bold' }}>{links.length}</span></div>
        </div>
      </header>

      {/* Main Area */}
      <main style={{ display: 'flex', flex: 1, position: 'relative', zIndex: 5 }}>
        
        {/* Left Control Sidebar */}
        <section style={{
          width: '300px', borderRight: '1px solid rgba(124, 77, 255, 0.15)',
          background: 'rgba(6, 4, 15, 0.82)', backdropFilter: 'blur(16px)',
          display: 'flex', flexDirection: 'column', padding: '16px', gap: '16px',
          overflowY: 'auto'
        }}>
          {/* Search bar */}
          <div>
            <label style={{ fontSize: '9px', letterSpacing: '1.5px', color: '#7c4dff', display: 'block', marginBottom: '6px', fontWeight: 700 }}>FILTER TARGETS</label>
            <input 
              type="text"
              placeholder="Search label, ID, or IP..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%', background: 'rgba(124, 77, 255, 0.05)',
                border: '1px solid rgba(124, 77, 255, 0.2)', borderRadius: '4px',
                color: '#fff', fontSize: '11px', padding: '8px',
                fontFamily: 'inherit', outline: 'none'
              }}
            />
          </div>

          {/* Toggle System Nodes & Clear Controls */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderBottom: '1px solid rgba(124, 77, 255, 0.15)', paddingBottom: '12px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'rgba(255, 255, 255, 0.8)', cursor: 'pointer', userSelect: 'none' }}>
              <input 
                type="checkbox" 
                checked={showSystemNodes} 
                onChange={(e) => setShowSystemNodes(e.target.checked)}
                style={{ cursor: 'pointer', accentColor: '#7c4dff' }}
              />
              Show System Nodes
            </label>
            <button
              onClick={handleClearGraph}
              style={{
                width: '100%', background: 'rgba(255, 23, 68, 0.08)', border: '1px solid rgba(255, 23, 68, 0.3)',
                borderRadius: '4px', color: '#ff1744', fontSize: '9.5px', fontWeight: 800,
                padding: '6px', cursor: 'pointer', transition: 'all 0.2s', letterSpacing: '0.5px'
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(255, 23, 68, 0.2)'}
              onMouseLeave={e => e.currentTarget.style.background = 'rgba(255, 23, 68, 0.08)'}
            >
              🗑️ CLEAR SCAN MAP
            </button>
          </div>

          {/* Launch Recon Scan Form */}
          <div style={{ borderBottom: '1px solid rgba(124, 77, 255, 0.15)', paddingBottom: '12px' }}>
            <label style={{ fontSize: '9px', letterSpacing: '1.5px', color: '#00e5ff', display: 'block', marginBottom: '8px', fontWeight: 700 }}>LAUNCH RECON SCAN</label>
            <form onSubmit={handleLaunchRecon} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <input 
                type="text" 
                placeholder="Target Domain (e.g. google.com)"
                value={reconDomain}
                onChange={e => setReconDomain(e.target.value)}
                style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(124, 77, 255, 0.15)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', padding: '6px 8px', fontFamily: 'inherit'
                }}
              />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'rgba(255,255,255,0.6)' }}>
                  <span>Max Subdomains:</span>
                  <span style={{ color: '#00e5ff', fontWeight: 'bold' }}>{reconLimit}</span>
                </div>
                <input 
                  type="range" 
                  min="5" 
                  max="300" 
                  step="5"
                  value={reconLimit}
                  onChange={e => setReconLimit(parseInt(e.target.value))}
                  style={{ width: '100%', accentColor: '#00e5ff', cursor: 'pointer' }}
                />
              </div>
              <button 
                type="submit"
                disabled={isReconScanning}
                style={{
                  background: isReconScanning ? 'rgba(0, 229, 255, 0.05)' : 'rgba(0, 229, 255, 0.12)', 
                  border: '1px solid rgba(0, 229, 255, 0.35)',
                  borderRadius: '4px', color: '#00e5ff', fontSize: '9.5px', fontWeight: 800,
                  padding: '7px', cursor: isReconScanning ? 'not-allowed' : 'pointer', transition: 'all 0.2s', letterSpacing: '0.5px'
                }}
                onMouseEnter={e => { if (!isReconScanning) e.currentTarget.style.background = 'rgba(0, 229, 255, 0.25)' }}
                onMouseLeave={e => { if (!isReconScanning) e.currentTarget.style.background = 'rgba(0, 229, 255, 0.12)' }}
              >
                {isReconScanning ? '📡 SCANNING...' : '📡 LAUNCH SCAN'}
              </button>
              {reconStatus && (
                <div style={{
                  fontSize: '9px', color: reconStatus.includes('Error') || reconStatus.includes('failed') ? '#ff1744' : '#00e5ff',
                  textAlign: 'center', marginTop: '2px', wordBreak: 'break-all'
                }}>
                  {reconStatus}
                </div>
              )}
            </form>
          </div>

          {/* Targets List */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '9px', letterSpacing: '1.5px', color: '#7c4dff', display: 'block', fontWeight: 700 }}>INTELLIGENCE NODES ({filteredNodes.length})</label>
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '200px', paddingRight: '4px' }}>
              {filteredNodes.map(node => (
                <div 
                  key={node.id}
                  onClick={() => setSelectedNode(node)}
                  style={{
                    background: 'rgba(124, 77, 255, 0.03)', border: '1px solid rgba(124, 77, 255, 0.1)',
                    borderRadius: '4px', padding: '6px 10px', fontSize: '11px', display: 'flex',
                    alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(124, 77, 255, 0.08)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(124, 77, 255, 0.03)'}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span>{getTypeIcon(node.type)}</span>
                    <span style={{ fontWeight: 'bold' }}>{node.label}</span>
                  </span>
                  <span style={{ fontSize: '9px', color: getTypeColor(node.type) }}>{node.type.toUpperCase()}</span>
                </div>
              ))}
              {filteredNodes.length === 0 && (
                <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)', textAlign: 'center', padding: '10px 0' }}>
                  No matching targets.
                </div>
              )}
            </div>
          </div>

          {/* Add custom node mapping form */}
          <div style={{ borderTop: '1px solid rgba(124, 77, 255, 0.15)', paddingTop: '16px' }}>
            <label style={{ fontSize: '9px', letterSpacing: '1.5px', color: '#7c4dff', display: 'block', marginBottom: '8px', fontWeight: 700 }}>MAP NEW TARGET NODE</label>
            <form onSubmit={handleAddNode} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <input 
                type="text" 
                placeholder="ID (e.g. host_db)"
                value={newNodeId}
                onChange={e => setNewNodeId(e.target.value)}
                style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(124, 77, 255, 0.15)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', padding: '6px 8px', fontFamily: 'inherit'
                }}
              />
              <input 
                type="text" 
                placeholder="Label (e.g. Database Server)"
                value={newNodeLabel}
                onChange={e => setNewNodeLabel(e.target.value)}
                style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(124, 77, 255, 0.15)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', padding: '6px 8px', fontFamily: 'inherit'
                }}
              />
              <select 
                value={newNodeType}
                onChange={e => setNewNodeType(e.target.value)}
                style={{
                  background: 'rgba(6, 4, 15, 0.9)', border: '1px solid rgba(124, 77, 255, 0.15)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', padding: '6px 8px', fontFamily: 'inherit'
                }}
              >
                <option value="host">Host 🖥️</option>
                <option value="subdomain">Subdomain 🌐</option>
                <option value="service">Service ⚙️</option>
                <option value="port">Port 🔌</option>
                <option value="vulnerability">Vulnerability 🚨</option>
                <option value="credential">Credential 🔑</option>
              </select>
              <input 
                type="text" 
                placeholder="IP / Subdomain URL (Optional)"
                value={newNodeIp}
                onChange={e => setNewNodeIp(e.target.value)}
                style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(124, 77, 255, 0.15)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', padding: '6px 8px', fontFamily: 'inherit'
                }}
              />
              <input 
                type="text" 
                placeholder="Parent ID to link to (Optional)"
                value={newNodeParentId}
                onChange={e => setNewNodeParentId(e.target.value)}
                style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(124, 77, 255, 0.15)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', padding: '6px 8px', fontFamily: 'inherit'
                }}
              />
              <input 
                type="text" 
                placeholder="Connection Port (Optional)"
                value={newNodePort}
                onChange={e => setNewNodePort(e.target.value)}
                style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(124, 77, 255, 0.15)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', padding: '6px 8px', fontFamily: 'inherit'
                }}
              />
              <button 
                type="submit"
                style={{
                  background: 'rgba(124, 77, 255, 0.15)', border: '1px solid rgba(124, 77, 255, 0.4)',
                  borderRadius: '4px', color: '#fff', fontSize: '10px', fontWeight: 800,
                  padding: '8px', cursor: 'pointer', transition: 'all 0.2s', letterSpacing: '1px'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(124, 77, 255, 0.3)'}
                onMouseLeave={e => e.currentTarget.style.background = 'rgba(124, 77, 255, 0.15)'}
              >
                MAP NODE
              </button>
              {formMsg && (
                <div style={{
                  fontSize: '9px', color: formMsg.includes('Error') || formMsg.includes('Failed') ? '#ff1744' : '#00e5ff',
                  textAlign: 'center', marginTop: '4px'
                }}>
                  {formMsg}
                </div>
              )}
            </form>
          </div>
        </section>

        {/* Central Visualization Area */}
        <section style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          {loading ? (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: '10px'
            }}>
              <div style={{
                width: '32px', height: '32px', borderRadius: '50%',
                border: '2px solid rgba(124, 77, 255, 0.1)', borderTopColor: '#7c4dff',
                animation: 'spin 1s linear infinite'
              }} />
              <div style={{ fontSize: '10px', letterSpacing: '2px', color: '#7c4dff' }}>LOADING WEBWEAVER HUD...</div>
            </div>
          ) : (
            <NetworkGraphView 
              nodes={nodes}
              links={links}
              selectedNode={selectedNode}
              setSelectedNode={setSelectedNode}
              showSystemNodes={showSystemNodes}
            />
          )}

          {/* Quick-action HUD Modal */}
          {selectedNode && (
            <div style={{
              position: 'absolute', top: '20px', right: '20px', width: '360px',
              background: 'rgba(10, 8, 22, 0.85)', border: '1px solid rgba(124, 77, 255, 0.35)',
              borderRadius: '12px', padding: '16px', backdropFilter: 'blur(16px)',
              boxShadow: '0 0 24px rgba(124, 77, 255, 0.15)', zIndex: 20,
              display: 'flex', flexDirection: 'column', gap: '12px',
              animation: 'fade-in 0.25s ease-out', maxHeight: 'calc(100vh - 40px)',
              overflowY: 'auto'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '9px', letterSpacing: '1.5px', color: '#7c4dff', fontWeight: 700 }}>NODE INSPECTOR</span>
                <button 
                  onClick={() => setSelectedNode(null)}
                  style={{
                    background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)',
                    fontSize: '12px', cursor: 'pointer', padding: 0
                  }}
                >
                  ✕
                </button>
              </div>

              {/* Details card */}
              <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '10px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <span style={{ fontSize: '20px' }}>{getTypeIcon(selectedNode.type)}</span>
                  <div>
                    <h3 style={{ margin: 0, fontSize: '12px', fontWeight: 'bold' }}>{selectedNode.label}</h3>
                    <span style={{ fontSize: '8px', color: getTypeColor(selectedNode.type), fontWeight: 'bold' }}>{selectedNode.type.toUpperCase()}</span>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '9.5px', color: 'rgba(255,255,255,0.6)' }}>
                  <div>ID: <span style={{ color: '#fff' }}>{selectedNode.id}</span></div>
                  {selectedNode.ip && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span>IP/ENDPOINT: <span style={{ color: '#00e5ff' }}>{selectedNode.ip}</span></span>
                      <button 
                        onClick={() => copyToClipboard(selectedNode.ip || '', 'IP')}
                        style={{
                          fontSize: '8px', background: 'none', border: '1px solid rgba(0, 229, 255, 0.3)',
                          borderRadius: '3px', color: '#00e5ff', padding: '1px 4px', cursor: 'pointer'
                        }}
                      >
                        COPY
                      </button>
                    </div>
                  )}
                  <div>STATUS: <span style={{ color: selectedNode.status === 'online' ? '#00e676' : '#ff1744' }}>{selectedNode.status.toUpperCase()}</span></div>
                </div>
              </div>

              {/* Action buttons */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <span style={{ fontSize: '8.5px', letterSpacing: '1px', color: 'rgba(255,255,255,0.4)', fontWeight: 700 }}>QUICK TRIGGERS</span>
                
                <button 
                  onClick={() => copyToClipboard(`/security check ssl ${selectedNode.ip || selectedNode.label}`, 'Command')}
                  style={{
                    background: 'rgba(0, 229, 255, 0.05)', border: '1px solid rgba(0, 229, 255, 0.25)',
                    borderRadius: '4px', color: '#00e5ff', fontSize: '9.5px', fontWeight: 800,
                    padding: '8px', cursor: 'pointer', textAlign: 'left', transition: '0.2s'
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(0, 229, 255, 0.15)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(0, 229, 255, 0.05)'}
                >
                  🔍 Run SSL/Port Scan
                </button>

                <button 
                  onClick={() => copyToClipboard(`/osint stalk ${selectedNode.ip || selectedNode.label}`, 'Command')}
                  style={{
                    background: 'rgba(124, 77, 255, 0.05)', border: '1px solid rgba(124, 77, 255, 0.25)',
                    borderRadius: '4px', color: '#7c4dff', fontSize: '9.5px', fontWeight: 800,
                    padding: '8px', cursor: 'pointer', textAlign: 'left', transition: '0.2s'
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(124, 77, 255, 0.15)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(124, 77, 255, 0.05)'}
                >
                  🌐 Gather Open Source Intel (OSINT)
                </button>

                <button 
                  onClick={() => copyToClipboard(`/repair fix ${selectedNode.id}`, 'Command')}
                  style={{
                    background: 'rgba(255, 145, 0, 0.05)', border: '1px solid rgba(255, 145, 0, 0.25)',
                    borderRadius: '4px', color: '#ff9100', fontSize: '9.5px', fontWeight: 800,
                    padding: '8px', cursor: 'pointer', textAlign: 'left', transition: '0.2s'
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255, 145, 0, 0.15)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(255, 145, 0, 0.05)'}
                >
                  🔧 Run Diagnostic Repair
                </button>
              </div>

              {/* Direct Node Terminal Chat */}
              <div style={{
                display: 'flex', flexDirection: 'column', gap: '8px',
                borderTop: '1px solid rgba(124, 77, 255, 0.2)', paddingTop: '12px'
              }}>
                <span style={{ fontSize: '8.5px', letterSpacing: '1px', color: '#00e5ff', fontWeight: 700 }}>DIRECT NODE TERMINAL</span>
                
                {/* Chat History */}
                <div style={{
                  overflowY: 'auto', background: 'rgba(0, 0, 0, 0.3)',
                  border: '1px solid rgba(124, 77, 255, 0.15)', borderRadius: '6px',
                  padding: '8px', display: 'flex', flexDirection: 'column', gap: '8px',
                  fontSize: '9.5px', fontFamily: 'monospace', height: '180px'
                }}>
                  {(!nodeChats[selectedNode.id] || nodeChats[selectedNode.id].length === 0) ? (
                    <div style={{ color: 'rgba(255,255,255,0.35)', textAlign: 'center', margin: 'auto 0', fontSize: '9px' }}>
                      AERIS terminal online.<br />Send commands to this node.
                    </div>
                  ) : (
                    nodeChats[selectedNode.id].map((msg, idx) => (
                      <div key={idx} style={{
                        display: 'flex', flexDirection: 'column', gap: '2px',
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '90%'
                      }}>
                        <div style={{
                          display: 'flex', justifyContent: 'space-between', 
                          gap: '8px', fontSize: '7.5px', color: msg.role === 'user' ? '#00e676' : '#7c4dff'
                        }}>
                          <span>{msg.role === 'user' ? 'OPERATOR' : 'AERIS'}</span>
                          <span style={{ color: 'rgba(255,255,255,0.3)' }}>{msg.timestamp}</span>
                        </div>
                        <div style={{
                          background: msg.role === 'user' ? 'rgba(0, 230, 118, 0.08)' : 'rgba(124, 77, 255, 0.08)',
                          border: msg.role === 'user' ? '1px solid rgba(0, 230, 118, 0.2)' : '1px solid rgba(124, 77, 255, 0.2)',
                          borderRadius: '4px', padding: '6px 8px', color: '#fff',
                          wordBreak: 'break-word', whiteSpace: 'pre-wrap'
                        }}>
                          {msg.content}
                        </div>
                      </div>
                    ))
                  )}
                  {isNodeChatSending && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#00e5ff', fontSize: '9px', fontStyle: 'italic' }}>
                      <span className="terminal-cursor" style={{
                        width: '6px', height: '10px', background: '#00e5ff',
                        display: 'inline-block', animation: 'blink 1.2s infinite'
                      }}></span>
                      AERIS is thinking...
                    </div>
                  )}
                  <div ref={nodeChatEndRef} />
                </div>

                {/* Input Form */}
                <form onSubmit={handleSendNodeChat} style={{ display: 'flex', gap: '6px' }}>
                  <input
                    type="text"
                    value={nodeChatInput}
                    onChange={(e) => setNodeChatInput(e.target.value)}
                    placeholder="Type command (e.g. scan ports)..."
                    disabled={isNodeChatSending}
                    style={{
                      flexGrow: 1, background: 'rgba(255,255,255,0.03)',
                      border: '1px solid rgba(124, 77, 255, 0.25)', borderRadius: '4px',
                      color: '#fff', fontSize: '10px', padding: '6px 8px',
                      outline: 'none', transition: '0.2s'
                    }}
                    onFocus={e => e.currentTarget.style.borderColor = '#00e5ff'}
                    onBlur={e => e.currentTarget.style.borderColor = 'rgba(124, 77, 255, 0.25)'}
                  />
                  <button
                    type="submit"
                    disabled={isNodeChatSending || !nodeChatInput.trim()}
                    style={{
                      background: 'rgba(124, 77, 255, 0.15)', border: '1px solid rgba(124, 77, 255, 0.35)',
                      borderRadius: '4px', color: '#7c4dff', fontSize: '10px', fontWeight: 'bold',
                      padding: '0 12px', cursor: 'pointer', display: 'flex', alignItems: 'center',
                      justifyContent: 'center', transition: '0.2s'
                    }}
                    onMouseEnter={e => { if (!e.currentTarget.disabled) e.currentTarget.style.background = 'rgba(124, 77, 255, 0.25)' }}
                    onMouseLeave={e => { if (!e.currentTarget.disabled) e.currentTarget.style.background = 'rgba(124, 77, 255, 0.15)' }}
                  >
                    SEND
                  </button>
                </form>
              </div>
            </div>
          )}
        </section>
      </main>

      {/* Global animations */}
      <style jsx global>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes fade-in {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
