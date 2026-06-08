'use client';
import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgentStore } from '@/store/agentStore';
import { soundEngine } from '@/services/SoundEngine';

interface CoreActivationProps {
  onComplete: () => void;
}

// Cinematic Spinning Reactor SVG Component
const SpinningReactor = () => (
  <div style={{ position: 'relative', width: '130px', height: '130px', marginBottom: '24px' }}>
    {/* Outer dashed ring (clockwise) */}
    <motion.svg
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 12, ease: 'linear' }}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      viewBox="0 0 100 100"
    >
      <circle
        cx="50"
        cy="50"
        r="46"
        fill="none"
        stroke="var(--cyan)"
        strokeWidth="1.2"
        strokeDasharray="6 8"
        style={{ opacity: 0.45, filter: 'drop-shadow(0 0 5px rgba(0, 255, 255, 0.4))' }}
      />
    </motion.svg>

    {/* Inner fast ring (counter-clockwise) */}
    <motion.svg
      animate={{ rotate: -360 }}
      transition={{ repeat: Infinity, duration: 5, ease: 'linear' }}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', padding: '10px', boxSizing: 'border-box' }}
      viewBox="0 0 100 100"
    >
      <circle
        cx="50"
        cy="50"
        r="44"
        fill="none"
        stroke="var(--purple)"
        strokeWidth="2"
        strokeDasharray="16 12 4 12"
        style={{ opacity: 0.6, filter: 'drop-shadow(0 0 8px rgba(170, 0, 255, 0.5))' }}
      />
    </motion.svg>

    {/* Target scope angle sweeps */}
    <motion.svg
      animate={{ rotate: 180 }}
      transition={{ repeat: Infinity, duration: 18, ease: 'linear' }}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', padding: '18px', boxSizing: 'border-box' }}
      viewBox="0 0 100 100"
    >
      <circle
        cx="50"
        cy="50"
        r="40"
        fill="none"
        stroke="var(--cyan)"
        strokeWidth="0.8"
        strokeDasharray="40 80"
        style={{ opacity: 0.75 }}
      />
    </motion.svg>

    {/* Glowing center orb with core pulsing */}
    <motion.div
      animate={{ scale: [1, 1.12, 1], opacity: [0.75, 1, 0.75] }}
      transition={{ repeat: Infinity, duration: 1.8, ease: 'easeInOut' }}
      style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '36px',
        height: '36px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, #ffffff 0%, var(--cyan) 50%, rgba(0, 255, 255, 0) 100%)',
        boxShadow: '0 0 18px var(--cyan), 0 0 35px rgba(0, 255, 255, 0.5)',
      }}
    />
  </div>
);

export const CoreActivation: React.FC<CoreActivationProps> = ({ onComplete }) => {
  const loadingSteps = useAgentStore((state) => state.loadingSteps);
  const titleText = "AERIS CORE INITIALIZING";
  const [fakeMemory, setFakeMemory] = useState<string>('0x00000000');
  const [systemTemperature, setSystemTemperature] = useState<number>(37);
  const [hackerLogs, setHackerLogs] = useState<string[]>([]);
  
  // Track completions to play sounds and trigger final transition
  const prevCompleteRef = useRef<boolean[]>(loadingSteps.map(s => s.complete));

  useEffect(() => {
    // Check for new progress or completions to play audio ticks
    loadingSteps.forEach((step, idx) => {
      const wasComplete = prevCompleteRef.current[idx];
      if (step.complete && !wasComplete) {
        soundEngine.playLoadingComplete();
        // Append log line
        setHackerLogs(prev => [
          ...prev.slice(-8), 
          `[SUCCESS] ${step.label.toUpperCase()} LOADED SUCCESSFULLY.`
        ]);
      } else if (step.progress > 0 && !step.complete) {
        soundEngine.playLoadingTick();
        if (Math.random() > 0.4) {
          const randHex = '0x' + Math.floor(Math.random() * 0xFFFFFFFF).toString(16).toUpperCase().padStart(8, '0');
          setFakeMemory(randHex);
          // Append microscopic process activity
          const operations = [
            `Allocating page block at ${randHex}`,
            `Binding secure registry address ${randHex}`,
            `Decrypting voice matrix profile`,
            `Caching node vector database`,
            `Parsing swarm configurations`
          ];
          const randomOp = operations[Math.floor(Math.random() * operations.length)];
          setHackerLogs(prev => [...prev.slice(-8), `[EXEC] ${randomOp}...`]);
        }
      }
    });
    
    prevCompleteRef.current = loadingSteps.map(s => s.complete);

    // If all steps are complete, proceed to Agent Arrival after a short delay
    const allComplete = loadingSteps.every((s) => s.complete);
    if (allComplete && loadingSteps.length > 0) {
      const timer = setTimeout(() => {
        onComplete();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [loadingSteps, onComplete]);

  // Temp jitter simulator
  useEffect(() => {
    const tempInterval = setInterval(() => {
      setSystemTemperature(prev => {
        const delta = Math.random() > 0.5 ? 0.2 : -0.2;
        return parseFloat(Math.min(52, Math.max(36, prev + delta)).toFixed(1));
      });
    }, 800);
    return () => clearInterval(tempInterval);
  }, []);

  // Title character animation settings
  const containerVariants = {
    before: {},
    after: { transition: { staggerChildren: 0.03 } },
  };

  const charVariants = {
    before: { opacity: 0, y: 10 },
    after: { opacity: 1, y: 0, transition: { type: 'spring' as any, damping: 10, stiffness: 100 } },
  };

  const allComplete = loadingSteps.every((s) => s.complete);

  return (
    <div style={{
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      width: '100%',
      height: '100vh',
      background: 'radial-gradient(circle, rgba(10,20,40,0.85) 0%, rgba(3,5,15,1) 100%)',
      fontFamily: 'JetBrains Mono, monospace',
      overflow: 'hidden',
      padding: '76px 20px 20px 20px',
      boxSizing: 'border-box'
    }}>
      {/* Holographic Scanline Overlay */}
      <div className="holographic-scanline" style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '4px',
        background: 'rgba(0, 255, 255, 0.25)',
        boxShadow: '0 0 12px rgba(0, 255, 255, 0.8)',
        zIndex: 10,
        pointerEvents: 'none',
        animation: 'holographic-scan 4s linear infinite',
      }} />

      {/* Grid Overlay */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06))',
        backgroundSize: '100% 4px, 6px 100%',
        zIndex: 5,
        pointerEvents: 'none',
      }} />

      {/* ── LEFT HUD Diagnostics Overlay ── */}
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
            SYSTEM DIAGNOSTICS
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '16px' }}>
            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>CPU CORE TEMP</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 800, color: systemTemperature > 45 ? '#ff3366' : 'var(--cyan)' }}>{systemTemperature}°C</span>
                <span style={{ fontSize: '8px', color: '#00e676' }}>NORMAL RANGE</span>
              </div>
            </div>
            
            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>MEMORY REGISTRY INDEX</div>
              <div style={{ fontSize: '11px', fontFamily: 'monospace', color: 'rgba(255,255,255,0.9)', letterSpacing: '1px' }}>
                {fakeMemory}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>SWARM NET CAPABILITY</div>
              <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.85)' }}>
                35 ACTIVE THREADS POOLED
              </div>
            </div>
          </div>
        </div>

        {/* Console dump */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', height: '140px', overflow: 'hidden' }}>
          <span style={{ fontSize: '7.5px', color: 'rgba(255,255,255,0.3)', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '3px', marginBottom: '4px' }}>
            STACK VERIFICATION
          </span>
          {hackerLogs.map((log, i) => (
            <div key={i} style={{ fontSize: '7.5px', fontFamily: 'monospace', color: log.startsWith('[SUCCESS]') ? '#00e676' : 'rgba(255,255,255,0.55)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
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
            NEURAL NETWORK ENGINE
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '16px' }}>
            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>NODE SIGNAL INTEGRITY</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 800, color: 'var(--cyan)' }}>99.98%</span>
                <div style={{ display: 'flex', gap: '2px' }}>
                  {[1,2,3,4,5].map(b => (
                    <div key={b} style={{ width: '2px', height: `${b * 2.5}px`, background: '#00e676' }} />
                  ))}
                </div>
              </div>
            </div>

            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>AGENT THREAD SYNC</div>
              <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.85)' }}>
                DESERIALIZING SWARM NODE PROFILES...
              </div>
            </div>

            <div>
              <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '4px' }}>ENCRYPTION PROTOCOL</div>
              <div style={{ fontSize: '9px', color: 'var(--purple)', fontWeight: 700 }}>
                SHA-512 SECURE SHELL LINK
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
            {[0.6, 0.9, 0.45, 0.8, 0.55, 0.75, 0.35, 0.95, 0.6, 0.85, 0.5].map((delay, i) => (
              <motion.div
                key={i}
                animate={{ height: ['4px', '46px', '4px'] }}
                transition={{ repeat: Infinity, duration: delay + 0.6, ease: 'easeInOut' }}
                style={{
                  flex: 1,
                  backgroundColor: 'var(--cyan)',
                  borderRadius: '1px',
                  boxShadow: '0 0 3px rgba(0, 255, 255, 0.8)'
                }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Inner Centered Container */}
      <div style={{ zIndex: 12, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '90%', maxWidth: '480px' }}>
        
        {/* Spinning futuristic reactor */}
        <SpinningReactor />

        {/* Cinematic Title */}
        <motion.div
          variants={containerVariants}
          initial="before"
          animate="after"
          style={{
            display: 'flex',
            fontSize: '18px',
            fontWeight: 800,
            letterSpacing: '5px',
            color: '#ffffff',
            textShadow: '0 0 10px rgba(0, 255, 255, 0.5), 0 0 20px rgba(0, 255, 255, 0.2)',
            marginBottom: '32px',
            textAlign: 'center',
            flexWrap: 'wrap',
            justifyContent: 'center',
          }}
        >
          {titleText.split('').map((char, index) => (
            <motion.span 
              key={index} 
              variants={charVariants}
              style={{ color: char === 'A' || char === 'E' || char === 'R' || char === 'I' || char === 'S' ? 'var(--cyan)' : '#fff' }}
            >
              {char === ' ' ? '\u00A0' : char}
            </motion.span>
          ))}
        </motion.div>

        {/* Glassmorphic Panel containing the Loading Bars */}
        <div style={{
          width: '100%',
          background: 'rgba(3, 8, 24, 0.75)',
          border: '1px solid rgba(0, 255, 255, 0.12)',
          borderRadius: '8px',
          boxShadow: '0 0 30px rgba(0, 255, 255, 0.05), inset 0 0 20px rgba(0, 255, 255, 0.02)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          padding: '24px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px'
        }}>
          {loadingSteps.map((step, idx) => (
            <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '9px' }}>
                <span style={{ color: step.complete ? 'var(--cyan)' : 'rgba(255, 255, 255, 0.65)', letterSpacing: '1.5px', fontWeight: 700 }}>
                  // {step.label.toUpperCase()}
                </span>
                <span style={{ 
                  color: step.complete ? '#00e676' : 'rgba(255,255,255,0.45)', 
                  fontWeight: step.complete ? 700 : 400,
                  letterSpacing: '1px'
                }}>
                  {step.complete ? 'LOADED ✓' : `ALIGNING [${step.progress}%]`}
                </span>
              </div>
              
              {/* Futuristic Progress Bar Container with subtle segment borders */}
              <div style={{
                width: '100%',
                height: '4px',
                background: 'rgba(0, 255, 255, 0.03)',
                border: '1px solid rgba(0, 255, 255, 0.08)',
                borderRadius: '1px',
                overflow: 'hidden',
                position: 'relative'
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

        {/* Post-Completion Glitch Text */}
        {allComplete && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: [1, 0.8, 1] }}
            transition={{ repeat: Infinity, duration: 0.2 }}
            style={{
              marginTop: '28px',
              fontSize: '11px',
              letterSpacing: '4px',
              color: '#00e676',
              textShadow: '0 0 8px rgba(0, 230, 118, 0.5)',
              fontStyle: 'italic',
              fontWeight: 700
            }}
          >
            ASSEMBLING AGENT SWARM SYSTEM...
          </motion.div>
        )}
      </div>

      <style jsx global>{`
        @keyframes holographic-scan {
          0% { top: -10px; }
          100% { top: 100%; }
        }
      `}</style>
    </div>
  );
};
