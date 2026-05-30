'use client';
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgentStore } from '@/store/agentStore';

export interface AgentTaskInfo {
  agentId: string;
  task: string;
  progress: number;
  status: 'waiting' | 'working' | 'completed';
}

interface CollaborationViewProps {
  taskDescription: string;
  agentTasks: AgentTaskInfo[];
}

export const CollaborationView: React.FC<CollaborationViewProps> = ({
  taskDescription,
  agentTasks
}) => {
  const getAgentById = useAgentStore((state) => state.getAgentById);

  const activeCount = agentTasks.filter(t => t.status === 'working').length;
  const completedCount = agentTasks.filter(t => t.status === 'completed').length;

  return (
    <div style={{
      background: 'rgba(5, 10, 25, 0.85)',
      backdropFilter: 'blur(16px)',
      WebkitBackdropFilter: 'blur(16px)',
      border: '1px solid rgba(0, 255, 255, 0.15)',
      borderRadius: '8px',
      padding: '20px',
      margin: '16px 0',
      color: '#fff',
      fontFamily: 'JetBrains Mono, monospace',
      boxShadow: '0 0 25px rgba(0, 255, 255, 0.08)',
    }}>
      {/* Header section */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottom: '1px solid rgba(0, 255, 255, 0.12)',
        paddingBottom: '10px',
        marginBottom: '16px'
      }}>
        <div>
          <span style={{ 
            fontSize: '9px', 
            color: 'var(--cyan)', 
            letterSpacing: '2px',
            textShadow: '0 0 8px rgba(0,255,255,0.4)',
            fontWeight: 700
          }}>
            MULTI-AGENT COLLABORATION ORCHESTRATION
          </span>
          <h3 style={{ fontSize: '13px', margin: '4px 0 0 0', fontWeight: 500 }}>
            {taskDescription.toUpperCase()}
          </h3>
        </div>
        <div style={{
          fontSize: '9px',
          padding: '2px 8px',
          background: 'rgba(0, 255, 255, 0.05)',
          border: '1px solid rgba(0, 255, 255, 0.2)',
          borderRadius: '4px',
          color: 'var(--cyan)'
        }}>
          {completedCount} / {agentTasks.length} COMPLETED
        </div>
      </div>

      {/* Tasks List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <AnimatePresence>
          {agentTasks.map((taskInfo) => {
            const agent = getAgentById(taskInfo.agentId) || {
              codename: taskInfo.agentId.toUpperCase(),
              icon: '🤖',
              color: '#00ffff'
            };

            const isWorking = taskInfo.status === 'working';
            const isCompleted = taskInfo.status === 'completed';
            
            let statusText = 'WAITING';
            let statusColor = 'rgba(255,255,255,0.3)';
            if (isWorking) {
              statusText = 'WORKING';
              statusColor = 'var(--cyan)';
            } else if (isCompleted) {
              statusText = 'COMPLETED';
              statusColor = '#00e676';
            }

            return (
              <motion.div
                key={taskInfo.agentId}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '8px 12px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.04)',
                  borderRadius: '4px',
                  gap: '12px',
                }}
              >
                {/* Agent Icon */}
                <span style={{ fontSize: '18px' }}>{agent.icon}</span>

                {/* Agent Identity & Task Info */}
                <div style={{ width: '130px', display: 'flex', flexDirection: 'column' }}>
                  <span style={{ 
                    fontSize: '11px', 
                    fontWeight: 700, 
                    color: agent.color,
                    letterSpacing: '0.5px'
                  }}>
                    {agent.codename}
                  </span>
                  <span style={{ 
                    fontSize: '8px', 
                    color: 'rgba(255,255,255,0.4)',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden' 
                  }}>
                    {taskInfo.task.toUpperCase()}
                  </span>
                </div>

                {/* Progress bar */}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'rgba(255,255,255,0.4)' }}>
                    <span>PROGRESS</span>
                    <span>{taskInfo.progress}%</span>
                  </div>
                  <div style={{
                    width: '100%',
                    height: '3px',
                    background: 'rgba(255, 255, 255, 0.05)',
                    borderRadius: '1.5px',
                    overflow: 'hidden'
                  }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${taskInfo.progress}%` }}
                      transition={{ duration: 0.2 }}
                      style={{
                        height: '100%',
                        background: agent.color,
                        boxShadow: `0 0 6px ${agent.color}`,
                      }}
                    />
                  </div>
                </div>

                {/* Status indicator */}
                <div style={{ 
                  width: '90px', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'flex-end', 
                  gap: '6px',
                  fontSize: '9px',
                  fontWeight: 700,
                  color: statusColor
                }}>
                  {isWorking && (
                    <motion.div
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ repeat: Infinity, duration: 1 }}
                      style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: '50%',
                        backgroundColor: 'var(--cyan)',
                        boxShadow: '0 0 6px var(--cyan)',
                      }}
                    />
                  )}
                  {isCompleted && <span style={{ fontSize: '10px' }}>✓</span>}
                  <span>{statusText}</span>
                </div>

              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Footer stats */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '9px',
        color: 'rgba(255,255,255,0.4)',
        marginTop: '14px',
        borderTop: '1px solid rgba(255,255,255,0.05)',
        paddingTop: '10px'
      }}>
        <span>SWARM AGENTS ACTIVE: {activeCount}</span>
        <span>OPERATION STATUS: {activeCount > 0 ? 'PROCESSING' : 'IDLE'}</span>
      </div>
    </div>
  );
};
