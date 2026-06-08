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

export default function WebWeaverHUD() {
  const [nodes, setNodes] = useState<NetworkNode[]>([]);
  const [links, setLinks] = useState<NetworkLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null);
  
  // Custom target node form state
  const [newNodeId, setNewNodeId] = useState('');
  const [newNodeLabel, setNewNodeLabel] = useState('');
  const [newNodeType, setNewNodeType] = useState('host');
  const [newNodeIp, setNewNodeIp] = useState('');
  const [newNodeParentId, setNewNodeParentId] = useState('');
  const [newNodePort, setNewNodePort] = useState('');
  const [formMsg, setFormMsg] = useState('');

  // Search filter
  const [searchQuery, setSearchQuery] = useState('');

  // Drag state
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);

  // SVG ref for sizing
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<number | null>(null);
  const nodesStateRef = useRef<NetworkNode[]>([]);
  const dimensionsRef = useRef({ width: 800, height: 600 });

  // Update dimensions on mount and resize without layout thrashing
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

  // Load initial graph data
  const fetchGraph = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/webweaver/graph');
      const data = await res.json();
      
      // Keep existing node positions if reloading
      const existingMap = new Map(nodesStateRef.current.map(n => [n.id, n]));
      
      const width = dimensionsRef.current.width;
      const height = dimensionsRef.current.height;

      const initializedNodes = data.nodes.map((node: any) => {
        const existing = existingMap.get(node.id);
        return {
          ...node,
          x: existing?.x ?? (width / 2 + (Math.random() - 0.5) * 200),
          y: existing?.y ?? (height / 2 + (Math.random() - 0.5) * 200),
          vx: existing?.vx ?? 0,
          vy: existing?.vy ?? 0,
        };
      });

      setNodes(initializedNodes);
      setLinks(data.links);
      nodesStateRef.current = initializedNodes;
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

  // Force-directed layout algorithm run in requestAnimationFrame
  useEffect(() => {
    if (nodes.length === 0) return;

    const runPhysics = () => {
      const width = dimensionsRef.current.width;
      const height = dimensionsRef.current.height;
      const centerX = width / 2;
      const centerY = height / 2;

      // Make a copy of state to update positions safely
      const currentNodes = [...nodesStateRef.current];
      if (currentNodes.length === 0) return;

      const repulsionStrength = 80000;
      const repulsionRadius = 380;
      const linkStrength = 0.055;
      const desiredLinkDist = 190;
      const gravity = 0.006;
      const friction = 0.85;

      // 1. Repulsion between all nodes
      for (let i = 0; i < currentNodes.length; i++) {
        const u = currentNodes[i];
        if (u.id === draggedNodeId) continue;

        for (let j = 0; j < currentNodes.length; j++) {
          if (i === j) continue;
          const v = currentNodes[j];
          const dx = (u.x || 0) - (v.x || 0);
          const dy = (u.y || 0) - (v.y || 0);
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;

          if (dist < repulsionRadius) {
            const force = repulsionStrength / (dist * dist);
            u.vx = (u.vx || 0) + (dx / dist) * force;
            u.vy = (u.vy || 0) + (dy / dist) * force;
          }
        }
      }

      // 2. Link attraction
      links.forEach(link => {
        const sourceNode = currentNodes.find(n => n.id === link.source);
        const targetNode = currentNodes.find(n => n.id === link.target);

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
      currentNodes.forEach(u => {
        if (u.id === draggedNodeId) return;

        const dx = centerX - (u.x || 0);
        const dy = centerY - (u.y || 0);

        u.vx = ((u.vx || 0) + dx * gravity) * friction;
        u.vy = ((u.vy || 0) + dy * gravity) * friction;

        u.x = (u.x || 0) + u.vx;
        u.y = (u.y || 0) + u.vy;

        // Keep inside boundary bounds
        u.x = Math.max(50, Math.min(width - 50, u.x));
        u.y = Math.max(50, Math.min(height - 50, u.y));
      });

      // Trigger re-render by setting state
      setNodes([...currentNodes]);
      nodesStateRef.current = currentNodes;

      simulationRef.current = requestAnimationFrame(runPhysics);
    };

    simulationRef.current = requestAnimationFrame(runPhysics);
    return () => {
      if (simulationRef.current) cancelAnimationFrame(simulationRef.current);
    };
  }, [links, draggedNodeId]);

  // Handle Drag Events
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!draggedNodeId || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const updated = nodesStateRef.current.map(node => {
      if (node.id === draggedNodeId) {
        return { ...node, x: mouseX, y: mouseY, vx: 0, vy: 0 };
      }
      return node;
    });

    nodesStateRef.current = updated;
    setNodes(updated);
  };

  const handleMouseUp = () => {
    setDraggedNodeId(null);
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

  // Filtered nodes based on search
  const filteredNodes = nodes.filter(n => 
    n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
    n.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (n.ip && n.ip.includes(searchQuery))
  );

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
              {links.map((link, idx) => {
                const sourceNode = nodes.find(n => n.id === link.source);
                const targetNode = nodes.find(n => n.id === link.target);

                if (!sourceNode || !targetNode) return null;

                const x1 = sourceNode.x || 0;
                const y1 = sourceNode.y || 0;
                const x2 = targetNode.x || 0;
                const y2 = targetNode.y || 0;

                return (
                  <g key={`l-${idx}`}>
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
                        style={{ fontFamily: 'inherit', fontWeight: 'bold' }}
                      >
                        :{link.port}
                      </text>
                    )}
                  </g>
                );
              })}

              {/* Render Nodes */}
              {nodes.map(node => {
                const color = getTypeColor(node.type);
                const isSelected = selectedNode?.id === node.id;
                
                return (
                  <g 
                    key={node.id}
                    transform={`translate(${node.x || 0}, ${node.y || 0})`}
                    style={{ cursor: 'pointer' }}
                    onMouseDown={(e) => {
                      e.stopPropagation();
                      setDraggedNodeId(node.id);
                    }}
                    onDoubleClick={() => setSelectedNode(node)}
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

                    {/* Node label text card */}
                    <g transform="translate(0, 24)">
                      <rect 
                        x={-60} y={-9} width={120} height={18} rx={3}
                        fill="rgba(6, 4, 15, 0.85)" stroke="rgba(124, 77, 255, 0.3)" strokeWidth={0.5}
                      />
                      <text 
                        fill="#fff" fontSize="8.5px" textAnchor="middle" y={3}
                        style={{ fontWeight: 'bold', userSelect: 'none' }}
                      >
                        {node.label}
                      </text>
                    </g>

                    {/* Small IP display under card */}
                    {node.ip && (
                      <text 
                        y={43} fill="rgba(255,255,255,0.4)" fontSize="7px" textAnchor="middle"
                        style={{ userSelect: 'none' }}
                      >
                        {node.ip}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          )}

          {/* Quick-action HUD Modal */}
          {selectedNode && (
            <div style={{
              position: 'absolute', top: '20px', right: '20px', width: '320px',
              background: 'rgba(10, 8, 22, 0.85)', border: '1px solid rgba(124, 77, 255, 0.35)',
              borderRadius: '12px', padding: '16px', backdropFilter: 'blur(16px)',
              boxShadow: '0 0 24px rgba(124, 77, 255, 0.15)', zIndex: 20,
              display: 'flex', flexDirection: 'column', gap: '12px',
              animation: 'fade-in 0.25s ease-out'
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
      `}</style>
    </div>
  );
}
