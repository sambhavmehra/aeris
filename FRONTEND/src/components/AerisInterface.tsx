'use client';
import { useRef, useState, useEffect, useCallback } from 'react';
import Orb from './Orb';
import ChatPanel from './ChatPanel';
import { useParticles } from '@/hooks/useParticles';
import { useCursor } from '@/hooks/useCursor';
import { useAgentStore } from '@/store/agentStore';
import { AssemblySequence } from './assembly/AssemblySequence';
import { CommandCenter } from './command/CommandCenter';

const BRAND = 'AERIS';

export default function AerisInterface() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [isOnline, setIsOnline] = useState(false);
  const [dynamicGreeting, setDynamicGreeting] = useState<string>('Sir, ready when you are.');
  const particleRef = useRef<HTMLCanvasElement>(null);

  // Zustand multi-agent state
  const phase = useAgentStore((state) => state.phase);
  const setPhase = useAgentStore((state) => state.setPhase);
  const restoreAssembled = useAgentStore((state) => state.restoreAssembled);

  useParticles(particleRef, isSpeaking);
  useCursor();

  // Restore command center session if active
  useEffect(() => {
    const saved = sessionStorage.getItem('aeris-assembly-state');
    if (saved === 'assembled') {
      restoreAssembled();
    }
  }, [restoreAssembled]);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/status');
        if (res.ok) {
          setIsOnline(true);
          const data = await res.json();
          if (data && typeof data.hacker_mode === 'boolean') {
            if (data.hacker_mode) {
              document.body.classList.add('hacker');
            } else {
              document.body.classList.remove('hacker');
            }
          }
        } else {
          setIsOnline(false);
        }
      } catch (e) {
        setIsOnline(false);
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const fetchGreeting = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/greeting');
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && typeof data?.line === 'string' && data.line.trim()) {
          setDynamicGreeting(data.line.trim());
        }
      } catch (e) {
        // ignore
      }
    };

    fetchGreeting();
    const interval = setInterval(fetchGreeting, 10 * 60 * 1000); // 10 mins
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const openChat = () => setChatOpen(true);
  const closeChat = () => { setChatOpen(false); setIsSpeaking(false); };

  const greetingAccent = {
    primary: 'var(--cyan)',
    secondary: 'var(--purple)',
    glow1: 'rgba(var(--cyan-rgb),0.8)',
    glow2: 'rgba(var(--cyan-rgb),0.4)',
    glow3: 'rgba(var(--purple-rgb),0.2)',
  };

  const greetingTextShadow = `0 0 20px ${greetingAccent.glow1}, 0 0 40px ${greetingAccent.glow2}, 0 0 60px ${greetingAccent.glow3}`;

  const handleAssemblyComplete = useCallback(() => {
    if (phase === 'assembling') {
      setPhase('assembled');
    } else {
      setPhase('idle');
    }
  }, [phase, setPhase]);

  if (phase === 'assembling' || phase === 'disassembling') {
    return (
      <AssemblySequence
        onComplete={handleAssemblyComplete}
      />
    );
  }

  if (phase === 'assembled') {
    return (
      <CommandCenter
        onDisassemble={() => setPhase('idle')}
        onSpeakingChange={setIsSpeaking}
      />
    );
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'var(--navy)', overflow: 'hidden', cursor: 'none' }}>

      {/* Custom cursor */}
      <div
        id="aeris-cursor-glow"
        style={{
          position: 'fixed', width: '220px', height: '220px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(var(--cyan-rgb),0.065) 0%, transparent 70%)',
          pointerEvents: 'none', transform: 'translate(-50%, -50%)',
          zIndex: 9999, transition: 'opacity 0.3s',
        }}
      />
      <div
        id="aeris-cursor-dot"
        style={{
          position: 'fixed', width: '6px', height: '6px', borderRadius: '50%',
          background: 'rgba(var(--cyan-rgb),0.85)', pointerEvents: 'none',
          transform: 'translate(-50%, -50%)', zIndex: 10000,
          boxShadow: '0 0 12px rgba(var(--cyan-rgb),0.9)',
        }}
      />

      {/* Particle background */}
      <canvas ref={particleRef} style={{ position: 'fixed', inset: 0, zIndex: 1 }} />

      {/* Background grid */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        backgroundImage: `
          linear-gradient(rgba(var(--cyan-rgb),0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(var(--cyan-rgb),0.03) 1px, transparent 1px)
        `,
        backgroundSize: '30px 30px',
      }} />

      {/* Ambient background glow */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        background: `
          radial-gradient(ellipse 60% 55% at 50% 50%, rgba(0,20,40,0.55) 0%, transparent 70%),
          radial-gradient(ellipse 35% 35% at 20% 80%, rgba(var(--purple-rgb),0.04) 0%, transparent 60%),
          radial-gradient(ellipse 35% 35% at 80% 20%, rgba(var(--cyan-rgb),0.05) 0%, transparent 60%)
        `,
      }} />

      {/* Main UI */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 10,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        {/* Top status */}
        <div style={{
          position: 'absolute', top: '36px', left: '50%', transform: 'translateX(-50%)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '7px',
            background: 'rgba(var(--cyan-rgb),0.08)', border: '1px solid rgba(var(--cyan-rgb),0.3)',
            borderRadius: '20px', padding: '5px 14px',
            boxShadow: '0 0 12px rgba(var(--cyan-rgb),0.08)',
          }}>
            <div style={{
              width: '6px', height: '6px', borderRadius: '50%',
              background: !isOnline ? '#ff4444' : (isSpeaking ? 'var(--purple)' : 'var(--cyan)'),
              boxShadow: `0 0 10px ${!isOnline ? '#ff4444' : (isSpeaking ? 'var(--purple)' : 'var(--cyan)')}`,
              animation: 'status-blink 2s ease-in-out infinite',
            }} />
            <span style={{ fontSize: '10px', color: !isOnline ? 'rgba(255,100,100,0.9)' : 'rgba(var(--cyan-rgb),0.85)', letterSpacing: '2.5px', fontWeight: 500 }}>
              {!isOnline ? 'OFFLINE' : (isSpeaking ? 'PROCESSING' : 'IDLE')}
            </span>
          </div>
          <a href="/codepipeline" style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            background: 'rgba(var(--purple-rgb),0.1)', border: '1px solid rgba(var(--purple-rgb),0.35)',
            borderRadius: '20px', padding: '5px 14px', textDecoration: 'none',
            cursor: 'pointer', transition: 'all 0.3s', marginTop: '6px',
            boxShadow: '0 0 12px rgba(var(--purple-rgb),0.1)',
          }}>
            <span style={{ fontSize: '10px' }}>🤖</span>
            <span style={{ fontSize: '10px', color: 'var(--purple)', letterSpacing: '2px', fontWeight: 500 }}>CODE PIPELINE</span>
          </a>
        </div>

        {/* Split Time-based Greeting */}
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '100%',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          opacity: chatOpen ? 0 : 1, transition: 'opacity 0.5s ease',
          pointerEvents: 'none', zIndex: 12,
        }}>
          {(() => {
            const g = (dynamicGreeting || '').trim();
            const mid = Math.ceil(g.length / 2);
            const left = g.slice(0, mid);
            const right = g.slice(mid);
            return (
              <>
                {/* Left part */}
                <div
                  className="greeting-text-split"
                  style={{
                    position: 'absolute',
                    right: '50%',
                    marginRight: 'clamp(200px, 22vw, 320px)',
                    textAlign: 'right',
                    color: greetingAccent.primary,
                    textShadow: greetingTextShadow,
                  }}
                >
                  {left}
                </div>

                {/* Right part */}
                <div
                  className="greeting-text-split"
                  style={{
                    position: 'absolute',
                    left: '50%',
                    marginLeft: 'clamp(200px, 22vw, 320px)',
                    textAlign: 'left',
                    color: greetingAccent.primary,
                    textShadow: greetingTextShadow,
                  }}
                >
                  {right}
                </div>
              </>
            );
          })()}
        </div>

        {/* Sub-greeting & Icon below Orb */}
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, calc(-50% + 180px))',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
          opacity: chatOpen ? 0 : 1, transition: 'opacity 0.5s ease',
          pointerEvents: 'none', zIndex: 12,
        }}>
          <div
            className="greeting-icon"
            style={{
              color: greetingAccent.secondary,
              textShadow: `0 0 18px ${greetingAccent.glow1}`,
            }}
          >
            {'✨'}
          </div>
          <div
            className="greeting-sub"
            style={{
              color: 'rgba(0, 255, 170, 0.85)',
              textShadow: `0 0 10px rgba(0,255,170,0.25)`,
            }}
          >
            {dynamicGreeting}
          </div>
        </div>

        {/* Orb */}
        <Orb isSpeaking={isSpeaking} onClick={openChat} />

        {/* Hint */}
        <div
          className="tap-hint"
          style={{ opacity: chatOpen ? 0 : 1 }}
        >
          Tap to awaken
        </div>
      </div>

      {/* Chat panel */}
      <ChatPanel
        isOpen={chatOpen}
        onClose={closeChat}
        onSpeakingChange={setIsSpeaking}
      />
    </div>
  );
}
