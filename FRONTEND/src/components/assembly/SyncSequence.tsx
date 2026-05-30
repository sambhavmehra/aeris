'use client';
import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useAgentStore } from '@/store/agentStore';
import { NetworkGraph } from './NetworkGraph';
import { soundEngine } from '@/services/SoundEngine';

interface SyncSequenceProps {
  onComplete: () => void;
}

export const SyncSequence: React.FC<SyncSequenceProps> = ({ onComplete }) => {
  const syncSteps = useAgentStore((state) => state.syncSteps);
  const prevCompleteRef = useRef<boolean[]>(syncSteps.map(s => s.complete));
  const [syncLogs, setSyncLogs] = useState<string[]>([]);
  const [networkPing, setNetworkPing] = useState<number>(12);

  // Icons mapping for the 6 steps
  const stepIcons = ['🔊', '🧠', '📋', '🔧', '🌐', '🛡️'];

  useEffect(() => {
    // Play sound pulse when a new step begins or finishes
    syncSteps.forEach((step, idx) => {
      const wasComplete = prevCompleteRef.current[idx];
      if (step.complete && !wasComplete) {
        soundEngine.playSyncPulse();
        setSyncLogs(prev => [
          ...prev.slice(-8),
          `[OK] ${step.label.toUpperCase()} INTEGRATED.`
        ]);
      } else if (step.progress > 0 && !step.complete && !wasComplete) {
        soundEngine.playSyncPulse();
        if (Math.random() > 0.4) {
          const syncMsgs = [
            `Syncing packets for ${step.label}`,
            `Establishing handshake with agent cluster`,
            `Caching node indexes for ${step.label}`,
            `Validating thread payload security`
          ];
          const randomMsg = syncMsgs[Math.floor(Math.random() * syncMsgs.length)];
          setSyncLogs(prev => [...prev.slice(-8), `[SYNC] ${randomMsg}...`]);
        }
      }
    });

    prevCompleteRef.current = syncSteps.map(s => s.complete);

    // Transition to final page when all 6 sync steps are complete
    const allComplete = syncSteps.every((s) => s.complete);
    if (allComplete && syncSteps.length > 0) {
      const timer = setTimeout(() => {
        onComplete();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [syncSteps, onComplete]);

  // Ping jitter simulator
  useEffect(() => {
    const pingInterval = setInterval(() => {
      setNetworkPing(prev => {
        const delta = Math.floor(Math.random() * 5) - 2;
        return Math.min(30, Math.max(5, prev + delta));
      });
    }, 1000);
    return () => clearInterval(pingInterval);
  }, []);

  return (
    <div style={{
      position: 'relative',
      width: '100%',
      height: '100vh',
      background: '#010206',
      fontFamily: 'JetBrains Mono, monospace',
      color: '#fff',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden',
      padding: '76px 20px 20px 20px',
      boxSizing: 'border-box'
    }}>
      {/* Background Live Network Graph */}
      <div style={{
        position: 'absolute',
        inset: 0,
        opacity: 0.5,
        zIndex: 1,
        pointerEvents: 'none'
      }}>
        <NetworkGraph />
      </div>

      {/* Radial shade overlay for readability */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'radial-gradient(circle at center, rgba(1,2,6,0.2) 0%, rgba(1,2,6,0.88) 85%)',
        zIndex: 2,
        pointerEvents: 'none'
      }} />

      {/* ── LEFT HUD Cluster Info Overlay ── */}
      <div style={{
        position: 'absolute',
        left: '30px',
        top: '100px',
        bottom: '30px',
        width: '260px',
        background: 'rgba(4, 8, 20, 0.45)',
        border: '1px solid rgba(0, 255, 255, 0.08)',
        borderRadius: '6px',
        backdropFilter: 'blur(10px)',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        zIndex: 12,
        color: '#fff',
        pointerEvents: 'none',
        justifyContent: 'space-between'
      }}>
        <div>
          <div style={{ fontSize: '9px', letterSpacing: '2px', color: 'var(--cyan)', borderBottom: '1px solid rgba(0, 255, 255, 0.15)', paddingBottom: '6px', fontWeight: 800, textTransform: 'uppercase' }}>
            SWARM CONCURRENCY
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '16px' }}>
            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>NETWORK LATENCY</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 800, color: 'var(--cyan)' }}>{networkPing} ms</span>
                <span style={{ fontSize: '8.5px', color: '#00e676' }}>EXCELLENT CONNECTION</span>
              </div>
            </div>
            
            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>CLUSTER ROUTING</div>
              <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.85)' }}>
                32 INDEPENDENT NODE PIPES ESTABLISHED
              </div>
            </div>

            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>PACKET LOSS RATE</div>
              <div style={{ fontSize: '9px', color: '#00e676', fontWeight: 700 }}>
                0.00% LOSS (SECURE)
              </div>
            </div>
          </div>
        </div>

        {/* Real-time sync logs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', height: '140px', overflow: 'hidden' }}>
          <span style={{ fontSize: '7.5px', color: 'rgba(255,255,255,0.3)', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '3px', marginBottom: '4px' }}>
            NODE HANDSHAKE TRACE
          </span>
          {syncLogs.map((log, i) => (
            <div key={i} style={{ fontSize: '7.5px', fontFamily: 'monospace', color: log.startsWith('[OK]') ? '#00e676' : 'rgba(255,255,255,0.55)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
              {log}
            </div>
          ))}
        </div>
      </div>

      {/* ── RIGHT HUD Telemetry Metrics Overlay ── */}
      <div style={{
        position: 'absolute',
        right: '30px',
        top: '100px',
        bottom: '30px',
        width: '260px',
        background: 'rgba(4, 8, 20, 0.45)',
        border: '1px solid rgba(0, 255, 255, 0.08)',
        borderRadius: '6px',
        backdropFilter: 'blur(10px)',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        zIndex: 12,
        color: '#fff',
        pointerEvents: 'none',
        justifyContent: 'space-between'
      }}>
        <div>
          <div style={{ fontSize: '9px', letterSpacing: '2px', color: 'var(--cyan)', borderBottom: '1px solid rgba(0, 255, 255, 0.15)', paddingBottom: '6px', fontWeight: 800, textTransform: 'uppercase' }}>
            GRID INTERPOLATION
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '16px' }}>
            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>NODE CAPABILITY SYNC</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 800, color: 'var(--cyan)' }}>100% ALIGNED</span>
              </div>
            </div>

            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>SHARED MEMORY POOL</div>
              <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.85)' }}>
                4.2 TB NEURAL STORAGE MOUNTED
              </div>
            </div>

            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>SWARM NETWORK HASH</div>
              <div style={{ fontSize: '9px', color: 'var(--purple)', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                SHA256::C488F7824...
              </div>
            </div>
          </div>
        </div>

        {/* Small live wave visualizer block */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', height: '110px' }}>
          <span style={{ fontSize: '7.5px', color: 'rgba(255,255,255,0.3)', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '3px', marginBottom: '8px' }}>
            NODE FREQUENCY STREAM
          </span>
          <div style={{ display: 'flex', gap: '3px', height: '50px', alignItems: 'flex-end', justifyContent: 'center', padding: '0 10px' }}>
            {[0.5, 0.75, 0.9, 0.4, 0.8, 0.6, 0.95, 0.35, 0.85, 0.55, 0.7].map((delay, i) => (
              <motion.div
                key={i}
                animate={{ height: ['4px', '46px', '4px'] }}
                transition={{ repeat: Infinity, duration: delay + 0.6, ease: 'easeInOut' }}
                style={{
                  flex: 1,
                  backgroundColor: 'var(--purple)',
                  borderRadius: '1px',
                  boxShadow: '0 0 3px rgba(170, 0, 255, 0.8)'
                }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Centered Panel */}
      <div style={{
        zIndex: 10,
        width: '90%',
        maxWidth: '500px',
        background: 'rgba(3, 8, 24, 0.75)',
        border: '1px solid rgba(0, 255, 255, 0.12)',
        borderRadius: '8px',
        boxShadow: '0 0 30px rgba(0, 255, 255, 0.05), inset 0 0 20px rgba(0, 255, 255, 0.02)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        padding: '24px',
        boxSizing: 'border-box',
      }}>
        {/* Title */}
        <h2 style={{
          fontSize: '14px',
          fontWeight: 800,
          letterSpacing: '3px',
          color: 'var(--cyan)',
          textShadow: '0 0 10px rgba(0,255,255,0.4)',
          textAlign: 'center',
          margin: '0 0 24px 0',
          animation: 'sync-header-pulse 2s ease-in-out infinite'
        }}>
          SYNCHRONIZING AGENT NETWORK
        </h2>

        {/* Steps List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {syncSteps.map((step, idx) => (
            <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '9px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '12px' }}>{stepIcons[idx]}</span>
                  <span style={{ 
                    color: step.complete ? 'var(--cyan)' : 'rgba(255,255,255,0.65)', 
                    fontWeight: step.complete ? 700 : 400,
                    letterSpacing: '1px'
                  }}>
                    // {step.label.toUpperCase()}
                  </span>
                </div>
                <span style={{ 
                  color: step.complete ? '#00e676' : 'rgba(255,255,255,0.45)',
                  fontWeight: step.complete ? 700 : 400,
                  letterSpacing: '1px'
                }}>
                  {step.complete ? 'SYNCED ✓' : `ALIGNING [${step.progress}%]`}
                </span>
              </div>

              {/* Progress Bar container */}
              <div style={{
                width: '100%',
                height: '4px',
                background: 'rgba(0, 255, 255, 0.03)',
                border: '1px solid rgba(0, 255, 255, 0.08)',
                borderRadius: '1px',
                overflow: 'hidden'
              }}>
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${step.progress}%` }}
                  transition={{ duration: 0.1 }}
                  style={{
                    height: '100%',
                    background: 'linear-gradient(90deg, var(--cyan) 0%, #00e5ff 100%)',
                    boxShadow: '0 0 8px rgba(0, 255, 255, 0.8)',
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <style jsx global>{`
        @keyframes sync-header-pulse {
          0%, 100% { opacity: 0.7; }
          50% { opacity: 1; filter: drop-shadow(0 0 5px rgba(0,255,255,0.5)); }
        }
      `}</style>
    </div>
  );
};
