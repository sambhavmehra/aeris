'use client';
import { useRef, useState, useEffect } from 'react';
import Orb from './Orb';
import ChatPanel from './ChatPanel';
import { useParticles } from '@/hooks/useParticles';
import { useCursor } from '@/hooks/useCursor';

export default function AerisInterface() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [isOnline, setIsOnline] = useState(false);
  const particleRef = useRef<HTMLCanvasElement>(null);

  useParticles(particleRef, isSpeaking);
  useCursor();

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/status');
        if (res.ok) setIsOnline(true);
        else setIsOnline(false);
      } catch (e) {
        setIsOnline(false);
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const openChat = () => setChatOpen(true);
  const closeChat = () => { setChatOpen(false); setIsSpeaking(false); };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'var(--navy)', overflow: 'hidden', cursor: 'none' }}>

      {/* Custom cursor */}
      <div
        id="aeris-cursor-glow"
        style={{
          position: 'fixed', width: '220px', height: '220px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0,255,255,0.065) 0%, transparent 70%)',
          pointerEvents: 'none', transform: 'translate(-50%, -50%)',
          zIndex: 9999, transition: 'opacity 0.3s',
        }}
      />
      <div
        id="aeris-cursor-dot"
        style={{
          position: 'fixed', width: '6px', height: '6px', borderRadius: '50%',
          background: 'rgba(0,255,255,0.85)', pointerEvents: 'none',
          transform: 'translate(-50%, -50%)', zIndex: 10000,
          boxShadow: '0 0 12px rgba(0,255,255,0.9)',
        }}
      />

      {/* Particle background */}
      <canvas ref={particleRef} style={{ position: 'fixed', inset: 0, zIndex: 1 }} />

      {/* Background grid */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        backgroundImage: `
          linear-gradient(rgba(0,255,255,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,255,255,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '30px 30px',
      }} />

      {/* Ambient background glow */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        background: `
          radial-gradient(ellipse 60% 55% at 50% 50%, rgba(0,20,40,0.55) 0%, transparent 70%),
          radial-gradient(ellipse 35% 35% at 20% 80%, rgba(0,255,170,0.04) 0%, transparent 60%),
          radial-gradient(ellipse 35% 35% at 80% 20%, rgba(0,255,255,0.05) 0%, transparent 60%)
        `,
      }} />

      {/* Main UI */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 10,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        {/* Brand */}
        <div style={{
          position: 'absolute', top: '36px', left: '50%', transform: 'translateX(-50%)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
        }}>
          <div style={{
            fontSize: '11px', fontWeight: 400, letterSpacing: '10px',
            color: 'rgba(0,255,255,0.38)', textTransform: 'uppercase',
          }}>AERIS</div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '7px',
            background: 'rgba(0,255,255,0.04)', border: '1px solid rgba(0,255,255,0.1)',
            borderRadius: '20px', padding: '5px 14px',
          }}>
            <div style={{
              width: '5px', height: '5px', borderRadius: '50%',
              background: !isOnline ? '#ff4444' : (isSpeaking ? '#00ffaa' : '#00ffff'),
              boxShadow: `0 0 8px ${!isOnline ? '#ff4444' : (isSpeaking ? '#00ffaa' : '#00ffff')}`,
              animation: 'status-blink 2s ease-in-out infinite',
            }} />
            <span style={{ fontSize: '10px', color: !isOnline ? 'rgba(255,100,100,0.7)' : 'rgba(0,255,255,0.5)', letterSpacing: '2.5px' }}>
              {!isOnline ? 'OFFLINE' : (isSpeaking ? 'PROCESSING' : 'IDLE')}
            </span>
          </div>
          <a href="/codepipeline" style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            background: 'rgba(0,255,170,0.04)', border: '1px solid rgba(0,255,170,0.12)',
            borderRadius: '20px', padding: '5px 14px', textDecoration: 'none',
            cursor: 'pointer', transition: 'all 0.3s', marginTop: '6px',
          }}>
            <span style={{ fontSize: '10px' }}>🤖</span>
            <span style={{ fontSize: '10px', color: 'rgba(0,255,170,0.55)', letterSpacing: '2px' }}>CODE PIPELINE</span>
          </a>
        </div>

        {/* Orb */}
        <Orb isSpeaking={isSpeaking} onClick={openChat} />

        {/* Hint */}
        <div style={{
          position: 'absolute', bottom: '56px', left: '50%', transform: 'translateX(-50%)',
          color: 'rgba(255,255,255,0.2)', fontSize: '11px', letterSpacing: '3.5px',
          textTransform: 'uppercase', animation: 'hint-pulse 3s ease-in-out infinite',
          opacity: chatOpen ? 0 : 1, transition: 'opacity 0.3s',
          whiteSpace: 'nowrap',
        }}>
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
