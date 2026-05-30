'use client';
import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgentStore, Agent } from '@/store/agentStore';
import { soundEngine } from '@/services/SoundEngine';

interface AgentArrivalProps {
  onComplete: () => void;
  onSkip?: () => void;
}

interface LogEntry {
  id: string;
  codename: string;
  color: string;
  text: string;
  timestamp: string;
}

export const AgentArrival: React.FC<AgentArrivalProps> = ({ onComplete, onSkip }) => {
  const agents = useAgentStore((state) => state.agents);
  const [terminalLogs, setTerminalLogs] = useState<LogEntry[]>([]);
  const prevStatusesRef = useRef<Record<string, string>>({});
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const terminalContainerRef = useRef<HTMLDivElement>(null);

  // Find the agent currently presenting (initializing)
  const currentSpeakingAgent = agents.find((a) => a.status === 'initializing');
  const onlineCount = agents.filter((a) => a.status === 'online').length;

  // Track status transitions to play sounds and append terminal logs
  useEffect(() => {
    agents.forEach((agent) => {
      const prevStatus = prevStatusesRef.current[agent.id];
      
      // Play sound and write to terminal when agent goes online
      if (agent.status === 'online' && prevStatus && prevStatus !== 'online') {
        soundEngine.playAgentOnline();
      }

      // Append log entry when an agent starts introducing (goes into initializing)
      if (agent.status === 'initializing' && prevStatus !== 'initializing') {
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const newLog: LogEntry = {
          id: `${agent.id}-${Date.now()}`,
          codename: agent.codename,
          color: agent.color,
          text: agent.introduction,
          timestamp: timeStr
        };
        setTerminalLogs(prev => [...prev, newLog]);
      }

      prevStatusesRef.current[agent.id] = agent.status;
    });
  }, [agents]);

  // Autoscroll terminal
  useEffect(() => {
    const container = terminalContainerRef.current;
    if (container) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [terminalLogs]);

  // Autocomplete checker (all 32 agents online)
  useEffect(() => {
    if (onlineCount === agents.length && agents.length > 0) {
      const timer = setTimeout(() => {
        onComplete();
      }, 1800);
      return () => clearTimeout(timer);
    }
  }, [onlineCount, agents.length, onComplete]);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      height: '100vh',
      background: 'radial-gradient(circle at center, #050b18 0%, #010308 100%)',
      fontFamily: 'JetBrains Mono, monospace',
      color: '#fff',
      padding: '76px 20px 20px 20px',
      boxSizing: 'border-box',
      overflow: 'hidden',
      position: 'relative'
    }}>
      {/* Holographic background scan lines */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.2) 50%)',
        backgroundSize: '100% 4px',
        pointerEvents: 'none',
        zIndex: 2
      }} />

      {/* Central Screen Area (Grid + Active Speaker HUD) */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
        gap: '20px'
      }}>
        
        {/* ── 32 Agent Status Grid ── */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(8, 1fr)',
          gridTemplateRows: 'repeat(4, 1fr)',
          gap: '8px',
          width: '100%',
          flex: 1,
          zIndex: 5,
        }}>
          {agents.map((agent) => {
            const isSpeaking = currentSpeakingAgent?.id === agent.id;
            const isOnline = agent.status === 'online';
            
            return (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{
                  opacity: isOnline ? 1 : 0,
                  scale: isOnline ? 1 : 0.8
                }}
                transition={{ duration: 0.4, ease: 'easeOut' }}
                style={{
                  border: isOnline 
                    ? `1px solid ${agent.color}50` 
                    : '1px solid transparent',
                  background: isOnline 
                    ? 'rgba(5, 12, 28, 0.35)' 
                    : 'transparent',
                  borderRadius: '4px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  alignItems: 'center',
                  padding: '8px',
                  boxSizing: 'border-box',
                  position: 'relative',
                  overflow: 'hidden',
                  pointerEvents: isOnline ? 'auto' : 'none'
                }}
              >
                {isOnline && (
                  <>
                    {/* Colored glowing left accent bar */}
                    <div style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: '3px',
                      backgroundColor: agent.color,
                      boxShadow: `0 0 6px ${agent.color}`
                    }} />

                    <span style={{ fontSize: '16px', marginBottom: '4px' }}>{agent.icon}</span>
                    <span style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      color: agent.color,
                      letterSpacing: '0.5px',
                      textTransform: 'uppercase'
                    }}>
                      {agent.codename}
                    </span>
                    
                    <span style={{
                      fontSize: '7px',
                      color: '#00e676',
                      marginTop: '2px',
                      fontWeight: 600,
                      textTransform: 'uppercase'
                    }}>
                      ONLINE
                    </span>
                  </>
                )}
              </motion.div>
            );
          })}
        </div>

        {/* ── Active Presenting Speaker HUD (Pulsing Center Wave) ── */}
        <AnimatePresence>
          {currentSpeakingAgent && (
            <div style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 20,
              pointerEvents: 'none'
            }}>
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.8, opacity: 0 }}
                transition={{ type: 'spring', damping: 15, stiffness: 120 }}
                style={{
                  pointerEvents: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '360px',
                  height: '240px',
                  background: 'rgba(3, 8, 20, 0.92)',
                  border: `1px solid ${currentSpeakingAgent.color}60`,
                  boxShadow: `0 0 35px ${currentSpeakingAgent.color}25`,
                  borderRadius: '8px',
                  backdropFilter: 'blur(24px)',
                  WebkitBackdropFilter: 'blur(24px)',
                  padding: '20px',
                  boxSizing: 'border-box',
                  position: 'relative'
                }}
              >
                {/* Outer pulsing ring */}
                <motion.div
                  animate={{ scale: [1, 1.15, 1], opacity: [0.15, 0.5, 0.15] }}
                  transition={{ repeat: Infinity, duration: 1.8 }}
                  style={{
                    position: 'absolute',
                    width: '100px',
                    height: '100px',
                    borderRadius: '50%',
                    border: `2px solid ${currentSpeakingAgent.color}`,
                  }}
                />

                {/* Pulsing center orb */}
                <motion.div
                  animate={{ scale: [1, 1.08, 1] }}
                  transition={{ repeat: Infinity, duration: 0.9 }}
                  style={{
                    width: '74px',
                    height: '74px',
                    borderRadius: '50%',
                    background: `radial-gradient(circle, ${currentSpeakingAgent.color}20 0%, ${currentSpeakingAgent.color}45 100%)`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 2,
                    boxShadow: `0 0 20px ${currentSpeakingAgent.color}50`,
                    border: `1.5px solid ${currentSpeakingAgent.color}`
                  }}
                >
                  <span style={{ fontSize: '32px' }}>{currentSpeakingAgent.icon}</span>
                </motion.div>

                {/* Speaker name */}
                <h3 style={{
                  fontSize: '18px',
                  fontWeight: 800,
                  letterSpacing: '3px',
                  color: '#fff',
                  textShadow: `0 0 10px ${currentSpeakingAgent.color}`,
                  margin: '16px 0 4px 0',
                  textTransform: 'uppercase'
                }}>
                  {currentSpeakingAgent.codename}
                </h3>
                
                <span style={{
                  fontSize: '9px',
                  color: 'rgba(255,255,255,0.4)',
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  marginBottom: '12px'
                }}>
                  {currentSpeakingAgent.role}
                </span>

                {/* Audio Waveform Simulator */}
                <div style={{ display: 'flex', gap: '3px', height: '24px', alignItems: 'center' }}>
                  {[0.4, 0.8, 0.55, 0.9, 0.6, 0.75, 0.45].map((delay, i) => (
                    <motion.div
                      key={i}
                      animate={{ height: ['4px', '22px', '4px'] }}
                      transition={{ repeat: Infinity, duration: delay + 0.5, ease: 'easeInOut' }}
                      style={{
                        width: '3px',
                        backgroundColor: currentSpeakingAgent.color,
                        borderRadius: '1.5px',
                        boxShadow: `0 0 4px ${currentSpeakingAgent.color}`
                      }}
                    />
                  ))}
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

      </div>

      {/* ── Bottom Console Log Terminal ── */}
      <div style={{
        height: '140px',
        background: 'rgba(2, 4, 10, 0.85)',
        border: '1px solid rgba(0, 255, 255, 0.08)',
        borderRadius: '4px',
        padding: '12px 16px',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        zIndex: 10,
        marginTop: '16px'
      }}>
        <div style={{
          fontSize: '9px',
          color: 'rgba(255,255,255,0.3)',
          letterSpacing: '1px',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          paddingBottom: '4px',
          marginBottom: '8px',
          fontWeight: 700
        }}>
          SYSTEM INITIALIZATION CONSOLE OUTPUT
        </div>

        <div 
          ref={terminalContainerRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            fontSize: '10px',
            lineHeight: '1.5'
          }}
        >
          {terminalLogs.map((log) => (
            <div key={log.id} style={{ display: 'flex', alignItems: 'flex-start', fontFamily: 'monospace' }}>
              <span style={{ color: 'rgba(255,255,255,0.25)', marginRight: '8px' }}>
                [{log.timestamp}]
              </span>
              <span style={{ color: log.color, fontWeight: 700, marginRight: '6px', textTransform: 'uppercase' }}>
                {log.codename}:
              </span>
              <span style={{ color: 'rgba(255,255,255,0.8)' }}>
                {log.text}
              </span>
            </div>
          ))}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
};
export default AgentArrival;
