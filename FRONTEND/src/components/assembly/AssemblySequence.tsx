'use client';
import React, { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgentStore, AssemblyPhase } from '@/store/agentStore';
import { soundEngine } from '@/services/SoundEngine';
import { CoreActivation } from './CoreActivation';
import { AgentArrival } from './AgentArrival';
import { SyncSequence } from './SyncSequence';
import { FinalScreen } from './FinalScreen';

interface AssemblySequenceProps {
  onComplete: () => void;
}

type SubPhase = 'core-init' | 'agent-arrival' | 'network-sync' | 'final';

export const AssemblySequence: React.FC<AssemblySequenceProps> = ({ onComplete }) => {
  const phase = useAgentStore((state) => state.phase);
  const isDisassembling = phase === 'disassembling';
  const agents = useAgentStore((state) => state.agents);
  const onlineCount = agents.filter((a) => a.status === 'online').length;

  const [subPhase, setSubPhase] = useState<SubPhase>(
    isDisassembling ? 'agent-arrival' : 'core-init'
  );
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);
  
  // Zustand store actions
  const setAgentStatus = useAgentStore((state) => state.setAgentStatus);
  const setLoadingStepProgress = useAgentStore((state) => state.setLoadingStepProgress);
  const completeLoadingStep = useAgentStore((state) => state.completeLoadingStep);
  const setSyncStepProgress = useAgentStore((state) => state.setSyncStepProgress);
  const completeSyncStep = useAgentStore((state) => state.completeSyncStep);
  const setAllOffline = useAgentStore((state) => state.setAllOffline);
  const restoreAssembled = useAgentStore((state) => state.restoreAssembled);

  const handleSkip = async () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    try {
      await fetch('http://localhost:8000/api/voice/stop', { method: 'POST' });
    } catch (e) {
      console.warn("Failed to stop voice:", e);
    }
    restoreAssembled();
    onComplete();
  };

  const handleCancelAssembly = async () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    try {
      await fetch('http://localhost:8000/api/voice/stop', { method: 'POST' });
    } catch (e) {
      console.warn("Failed to stop voice:", e);
    }
    setAllOffline();
    onComplete();
  };

  // Lock window scroll to prevent layout shifts
  useEffect(() => {
    const lockScroll = () => {
      if (window.scrollY !== 0 || window.scrollX !== 0) {
        window.scrollTo(0, 0);
      }
      if (document.body && document.body.scrollTop !== 0) {
        document.body.scrollTop = 0;
      }
      if (document.documentElement && document.documentElement.scrollTop !== 0) {
        document.documentElement.scrollTop = 0;
      }
    };
    lockScroll();
    window.addEventListener('scroll', lockScroll);
    window.addEventListener('resize', lockScroll);
    return () => {
      window.removeEventListener('scroll', lockScroll);
      window.removeEventListener('resize', lockScroll);
    };
  }, []);

  useEffect(() => {
    // 1. Play boot sequence sound if assembling
    if (!isDisassembling) {
      soundEngine.playBootSequence();
      soundEngine.startAmbientHum();
    } else {
      soundEngine.stopAmbientHum();
    }

    // 2. Connect to backend Server-Sent Events stream
    let eventSource: EventSource | null = null;
    let fallbackTimer: NodeJS.Timeout | null = null;
    let didConnect = false;

    const streamUrl = isDisassembling
      ? 'http://localhost:8000/api/disassembly/stream'
      : 'http://localhost:8000/api/assembly/stream';

    try {
      eventSource = new EventSource(streamUrl);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        didConnect = true;
        console.log(`AERIS ${isDisassembling ? 'Disassembly' : 'Assembly'} Stream connected.`);
        if (fallbackTimer) clearTimeout(fallbackTimer);
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'phase_change') {
            if (data.phase === 'idle') {
              onCompleteRef.current();
            } else {
              setSubPhase(data.phase as SubPhase);
            }
          } 
          else if (data.type === 'loading_step') {
            setLoadingStepProgress(data.index, data.progress);
            if (data.complete) {
              completeLoadingStep(data.index);
            }
          } 
          else if (data.type === 'agent_status') {
            setAgentStatus(data.agent_id, data.status);
          } 
          else if (data.type === 'sync_step') {
            setSyncStepProgress(data.index, data.progress);
            if (data.complete) {
              completeSyncStep(data.index);
            }
          } 
          else if (data.type === 'complete') {
            console.log("Assembly stream completed.");
            if (isDisassembling) {
              onCompleteRef.current();
            }
          }
          else if (data.type === 'error') {
            console.error("Assembly stream error event:", data.message);
            triggerFallbackSimulation();
          }
        } catch (e) {
          console.error("Error parsing SSE data:", e);
        }
      };

      eventSource.onerror = (err) => {
        console.warn("SSE connection failed, checking for fallback...", err);
        if (eventSource) eventSource.close();
        if (!didConnect) {
          triggerFallbackSimulation();
        }
      };
    } catch (err) {
      console.error("EventSource creation error, falling back:", err);
      triggerFallbackSimulation();
    }

    // Fallback simulation triggers if backend is not responsive within 2 seconds
    fallbackTimer = setTimeout(() => {
      if (!didConnect) {
        console.log("Backend not responding. Triggering client-side simulation.");
        if (eventSource) eventSource.close();
        triggerFallbackSimulation();
      }
    }, 2000);

    // Client-side simulation logic in case backend is offline
    function triggerFallbackSimulation() {
      if (fallbackTimer) clearTimeout(fallbackTimer);
      
      const agentsList = useAgentStore.getState().agents;
      
      if (isDisassembling) {
        let agentIdx = agentsList.length - 1;
        const disassemblyInterval = setInterval(() => {
          if (agentIdx >= 0) {
            setAgentStatus(agentsList[agentIdx].id, 'offline');
            agentIdx--;
          } else {
            clearInterval(disassemblyInterval);
            setAllOffline();
            onCompleteRef.current();
          }
        }, 100);
        return;
      }

      // Simulating Core Activation (Phase 1)
      let currentStep = 0;
      const loadingInterval = setInterval(() => {
        if (currentStep < 7) {
          setLoadingStepProgress(currentStep, 100);
          completeLoadingStep(currentStep);
          currentStep++;
        } else {
          clearInterval(loadingInterval);
          setSubPhase('agent-arrival');
          simulateAgentArrival();
        }
      }, 500);

      // Simulating Agent Arrival (Phase 2)
      function simulateAgentArrival() {
        let agentIdx = 0;
        
        function arriveNextAgent() {
          if (agentIdx < agentsList.length) {
            const agent = agentsList[agentIdx];
            setAgentStatus(agent.id, 'initializing');
            
            setTimeout(() => {
              setAgentStatus(agent.id, 'online');
              agentIdx++;
              
              // Custom stagger depending on agent category
              const nextDelay = agent.category === 'swarm' ? 120 : agent.category === 'special' ? 220 : 280;
              setTimeout(arriveNextAgent, nextDelay);
            }, 180);
          } else {
            setSubPhase('network-sync');
            simulateNetworkSync();
          }
        }
        arriveNextAgent();
      }

      // Simulating Network Sync (Phase 3)
      function simulateNetworkSync() {
        let syncIdx = 0;
        const syncInterval = setInterval(() => {
          if (syncIdx < 6) {
            setSyncStepProgress(syncIdx, 100);
            completeSyncStep(syncIdx);
            syncIdx++;
          } else {
            clearInterval(syncInterval);
            setSubPhase('final');
          }
        }, 800);
      }
    }

    return () => {
      if (eventSource) eventSource.close();
      if (fallbackTimer) clearTimeout(fallbackTimer);
    };
  }, [
    isDisassembling,
    setAgentStatus,
    setLoadingStepProgress,
    completeLoadingStep,
    setSyncStepProgress,
    completeSyncStep,
    setAllOffline
  ]);

  const handleSubPhaseComplete = () => {
    if (isDisassembling) {
      onComplete();
      return;
    }
    // Manual/component driven phase progression triggers
    if (subPhase === 'core-init') {
      setSubPhase('agent-arrival');
    } else if (subPhase === 'agent-arrival') {
      setSubPhase('network-sync');
    } else if (subPhase === 'network-sync') {
      setSubPhase('final');
    } else if (subPhase === 'final') {
      onComplete();
    }
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      width: '100vw',
      height: '100vh',
      zIndex: 5000,
      background: '#000',
      overflow: 'hidden',
    }}>
      <AnimatePresence mode="wait">
        {subPhase === 'core-init' && (
          <motion.div
            key="core-init"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            style={{ width: '100%', height: '100%' }}
          >
            <CoreActivation onComplete={handleSubPhaseComplete} />
          </motion.div>
        )}

        {subPhase === 'agent-arrival' && (
          <motion.div
            key="agent-arrival"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            style={{ width: '100%', height: '100%' }}
          >
            <AgentArrival onComplete={handleSubPhaseComplete} onSkip={handleSkip} />
          </motion.div>
        )}

        {subPhase === 'network-sync' && (
          <motion.div
            key="network-sync"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            style={{ width: '100%', height: '100%' }}
          >
            <SyncSequence onComplete={handleSubPhaseComplete} />
          </motion.div>
        )}

        {subPhase === 'final' && (
          <motion.div
            key="final"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            style={{ width: '100%', height: '100%' }}
          >
            <FinalScreen onComplete={handleSubPhaseComplete} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Assembly Phase Top Bar ── */}
      {subPhase !== 'final' && !isDisassembling && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '56px',
          background: 'rgba(4, 7, 18, 0.75)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid rgba(0, 255, 255, 0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          zIndex: 10000,
          fontFamily: 'JetBrains Mono, monospace'
        }}>
          <div>
            <h2 style={{
              fontSize: '13px',
              fontWeight: 800,
              letterSpacing: '2px',
              color: 'var(--cyan)',
              textShadow: '0 0 8px rgba(0, 255, 255, 0.5)',
              margin: 0,
              textTransform: 'uppercase'
            }}>
              {subPhase === 'core-init' ? 'AERIS CORE INITIALIZING' : 'AERIS AGENTS ASSEMBLING'}
            </h2>
            <span style={{ fontSize: '8px', color: 'rgba(255, 255, 255, 0.35)', letterSpacing: '1px', textTransform: 'uppercase' }}>
              {subPhase === 'core-init' 
                ? 'STATUS: ANALYZING NETWORK PORT AND FILE REGISTRIES...' 
                : `STATUS: SYNCHRONIZING SECURE NODE INSTANCES (${onlineCount} / ${agents.length})`}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Skip Button (visible during agent arrival) */}
            {subPhase === 'agent-arrival' && (
              <motion.button
                onClick={handleSkip}
                whileHover={{ scale: 1.05, boxShadow: '0 0 10px rgba(0, 255, 255, 0.25)' }}
                whileTap={{ scale: 0.95 }}
                style={{
                  padding: '6px 14px',
                  background: 'rgba(0, 255, 255, 0.04)',
                  border: '1px solid rgba(0, 255, 255, 0.25)',
                  borderRadius: '4px',
                  color: 'var(--cyan)',
                  fontSize: '9px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  letterSpacing: '1px',
                  outline: 'none',
                }}
              >
                SKIP INTRO
              </motion.button>
            )}

            {/* Disassemble / Cancel Button */}
            <motion.button
              onClick={handleCancelAssembly}
              whileHover={{ scale: 1.05, boxShadow: '0 0 12px rgba(255, 51, 102, 0.4)' }}
              whileTap={{ scale: 0.95 }}
              style={{
                padding: '6px 14px',
                background: 'rgba(255, 51, 102, 0.08)',
                border: '1px solid rgba(255, 51, 102, 0.35)',
                borderRadius: '4px',
                color: '#ff3366',
                fontSize: '9px',
                fontWeight: 700,
                cursor: 'pointer',
                fontFamily: 'inherit',
                letterSpacing: '1px',
                outline: 'none',
              }}
            >
              DISASSEMBLE
            </motion.button>
          </div>
        </div>
      )}
    </div>
  );
};
