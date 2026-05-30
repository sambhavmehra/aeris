'use client';
import React, { useState } from 'react';
import { useAgentStore, Agent, AGENT_CATEGORIES, AgentCategory } from '@/store/agentStore';

interface AgentPanelProps {
  selectedAgentId: string | null;
  onSelectAgent: (id: string | null) => void;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ selectedAgentId, onSelectAgent }) => {
  const agents = useAgentStore((state) => state.agents);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Track open/collapsed state of categories
  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({
    core: false,
    control: false,
    swarm: false,
    special: false
  });

  const toggleCategory = (catKey: string) => {
    setCollapsedCategories(prev => ({
      ...prev,
      [catKey]: !prev[catKey]
    }));
  };

  // Filter agents by search input
  const filteredAgents = agents.filter(agent => 
    agent.codename.toLowerCase().includes(searchTerm.toLowerCase()) ||
    agent.role.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getStatusDotColor = (status: string) => {
    switch (status) {
      case 'online': return '#00e676';
      case 'working': return '#00ffff';
      case 'initializing': return '#ffab00';
      case 'error': return '#ff3366';
      default: return '#ff4444';
    }
  };

  return (
    <div style={{
      width: '260px',
      height: '100%',
      background: 'rgba(3, 6, 15, 0.45)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      borderRight: '1px solid rgba(0, 255, 255, 0.06)',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: 'JetBrains Mono, monospace',
      color: '#fff',
      boxSizing: 'border-box',
    }}>
      {/* Search Header */}
      <div style={{ padding: '16px', borderBottom: '1px solid rgba(0, 255, 255, 0.06)' }}>
        <div style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          background: 'rgba(0, 255, 255, 0.01)',
          border: '1px solid rgba(0, 255, 255, 0.15)',
          borderRadius: '4px',
          padding: '2px 10px',
          boxShadow: 'inset 0 0 8px rgba(0, 255, 255, 0.04)',
          transition: 'all 0.3s ease'
        }}>
          <span style={{ color: 'rgba(0, 255, 255, 0.6)', fontSize: '11px', marginRight: '8px' }}>⚡</span>
          <input
            type="text"
            placeholder="FILTER SWARM INTEL..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              background: 'none',
              border: 'none',
              outline: 'none',
              color: '#fff',
              fontSize: '10px',
              fontFamily: 'inherit',
              padding: '6px 0',
              letterSpacing: '1px',
            }}
          />
          {searchTerm && (
            <button 
              onClick={() => setSearchTerm('')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--cyan)',
                cursor: 'pointer',
                fontSize: '10px',
                padding: '0 4px',
                textShadow: '0 0 4px rgba(0,255,255,0.5)'
              }}
            >
              ✗
            </button>
          )}
        </div>
      </div>

      {/* Agents Category List */}
      <div className="agent-list-scrollable" style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 8px',
      }}>
        {AGENT_CATEGORIES.map((category) => {
          const categoryAgents = filteredAgents.filter(a => a.category === category.key);
          const isCollapsed = collapsedCategories[category.key];
          
          if (categoryAgents.length === 0) return null;

          return (
            <div key={category.key} style={{ marginBottom: '16px' }}>
              {/* Category Collapsible Header */}
              <div 
                onClick={() => toggleCategory(category.key)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 10px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '9px',
                  fontWeight: 700,
                  letterSpacing: '1.5px',
                  color: category.color,
                  background: 'rgba(255, 255, 255, 0.01)',
                  borderLeft: `2px solid ${category.color}40`,
                  userSelect: 'none',
                  transition: 'all 0.2s ease',
                  boxShadow: `inset 0 0 8px ${category.color}05`
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)';
                  e.currentTarget.style.borderLeftColor = category.color;
                  e.currentTarget.style.boxShadow = `0 0 10px ${category.color}15`;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.01)';
                  e.currentTarget.style.borderLeftColor = `${category.color}40`;
                  e.currentTarget.style.boxShadow = `inset 0 0 8px ${category.color}05`;
                }}
              >
                <span>{category.label} ({categoryAgents.length})</span>
                <span style={{ fontSize: '7px', transform: isCollapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s ease' }}>
                  ▼
                </span>
              </div>

              {/* Collapsed Items Container */}
              {!isCollapsed && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', marginTop: '6px' }}>
                  {categoryAgents.map((agent) => {
                    const isSelected = selectedAgentId === agent.id;
                    const dotColor = getStatusDotColor(agent.status);

                    return (
                      <div
                        key={agent.id}
                        onClick={() => onSelectAgent(isSelected ? null : agent.id)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          padding: '8px 12px',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          background: isSelected 
                            ? `linear-gradient(90deg, ${agent.color}15 0%, rgba(5,10,25,0.05) 100%)` 
                            : 'transparent',
                          borderLeft: `3px solid ${isSelected ? agent.color : 'transparent'}`,
                          borderRight: isSelected ? `1px solid ${agent.color}15` : '1px solid transparent',
                          boxShadow: isSelected ? `inset 0 0 8px ${agent.color}08` : 'none',
                          transition: 'all 0.2s ease',
                          position: 'relative'
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.background = 'linear-gradient(90deg, rgba(255, 255, 255, 0.02) 0%, transparent 100%)';
                            e.currentTarget.style.borderLeftColor = `${agent.color}40`;
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.borderLeftColor = 'transparent';
                          }
                        }}
                      >
                        {/* Selector indicator */}
                        {isSelected && (
                          <div style={{
                            position: 'absolute',
                            right: '4px',
                            top: '4px',
                            fontSize: '6px',
                            color: agent.color,
                            opacity: 0.5
                          }}>
                            [ACTIVE]
                          </div>
                        )}

                        {/* Agent Icon */}
                        <span style={{ fontSize: '13px', marginRight: '10px' }}>{agent.icon}</span>

                        {/* Agent Details */}
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                          <span style={{ 
                            fontSize: '11px', 
                            fontWeight: 700, 
                            color: isSelected ? '#fff' : '#c8c8c8',
                            letterSpacing: '0.5px',
                            textShadow: isSelected ? `0 0 8px ${agent.color}40` : 'none'
                          }}>
                            {agent.codename}
                          </span>
                          <span style={{ 
                            fontSize: '8px', 
                            color: isSelected ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.3)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            textTransform: 'uppercase'
                          }}>
                            {agent.role}
                          </span>
                        </div>

                        {/* Status Pulse Dot */}
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          <div 
                            style={{
                              width: '5px',
                              height: '5px',
                              borderRadius: '50%',
                              backgroundColor: dotColor,
                              boxShadow: `0 0 6px ${dotColor}`,
                              animation: (agent.status === 'initializing' || agent.status === 'working') 
                                ? 'agent-dot-pulse 0.8s ease-in-out infinite' 
                                : 'agent-dot-pulse-slow 2s ease-in-out infinite'
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <style jsx global>{`
        @keyframes agent-dot-pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.85); box-shadow: 0 0 2px var(--cyan); }
          50% { opacity: 1; transform: scale(1.15); box-shadow: 0 0 8px var(--cyan); }
        }
        @keyframes agent-dot-pulse-slow {
          0%, 100% { opacity: 0.6; transform: scale(0.9); }
          50% { opacity: 1; transform: scale(1.05); }
        }
        .agent-list-scrollable::-webkit-scrollbar {
          width: 2px;
        }
        .agent-list-scrollable::-webkit-scrollbar-track {
          background: transparent;
        }
        .agent-list-scrollable::-webkit-scrollbar-thumb {
          background: rgba(0, 255, 255, 0.08);
          border-radius: 1px;
        }
        .agent-list-scrollable::-webkit-scrollbar-thumb:hover {
          background: rgba(0, 255, 255, 0.25);
        }
      `}</style>
    </div>
  );
};
