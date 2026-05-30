'use client';
import React from 'react';
import { motion } from 'framer-motion';
import { Agent } from '@/store/agentStore';

interface AgentCardProps {
  agent: Agent;
  index?: number;
  onClick?: () => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, index = 0, onClick }) => {
  const isSpecial = agent.category === 'special';
  
  // Status dot color mapping
  const statusColors = {
    offline: '#ff4444',
    initializing: '#ffab00',
    online: '#00e676',
    working: '#00ffff',
    error: '#ff3366',
  };

  const statusColor = statusColors[agent.status] || statusColors.offline;

  return (
    <motion.div
      initial={{ opacity: 0, x: 60 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ 
        type: 'spring', 
        stiffness: 100, 
        damping: 15,
        delay: index * 0.05 
      }}
      whileHover={{ 
        scale: 1.02,
        boxShadow: `0 0 15px rgba(${isSpecial ? '255,51,102' : '0,255,255'}, 0.25)`,
        borderColor: agent.color
      }}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        height: '60px',
        padding: '12px 16px',
        background: isSpecial ? 'rgba(30,10,20,0.6)' : 'rgba(10,15,30,0.6)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid rgba(0,255,255,0.1)',
        borderLeft: `4px solid ${agent.color}`,
        borderRadius: '4px',
        marginBottom: '8px',
        cursor: onClick ? 'pointer' : 'default',
        color: '#fff',
        fontFamily: 'JetBrains Mono, monospace',
        transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
        boxShadow: isSpecial ? '0 0 10px rgba(255,51,102,0.1)' : 'none',
      }}
    >
      {/* Icon/Emoji */}
      <span style={{ fontSize: '20px', marginRight: '12px' }}>{agent.icon}</span>

      {/* Details */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <span style={{ 
          fontSize: '13px', 
          fontWeight: 700, 
          letterSpacing: '1px',
          textShadow: `0 0 5px ${agent.color}50`
        }}>
          {agent.codename}
        </span>
        <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {agent.role}
        </span>
      </div>

      {/* Status Badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <motion.div
          animate={agent.status === 'initializing' ? { opacity: [0.3, 1, 0.3] } : {}}
          transition={{ repeat: Infinity, duration: 1 }}
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: statusColor,
            boxShadow: `0 0 8px ${statusColor}`,
          }}
        />
        <span style={{ fontSize: '8px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.6)' }}>
          {agent.status}
        </span>
      </div>
    </motion.div>
  );
};
