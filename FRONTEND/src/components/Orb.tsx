'use client';
import { useRef } from 'react';
import { useWaveform } from '@/hooks/useWaveform';

interface OrbProps {
  isSpeaking: boolean;
  onClick: () => void;
}

export default function Orb({ isSpeaking, onClick }: OrbProps) {
  const waveRef = useRef<HTMLCanvasElement>(null);
  useWaveform(waveRef, isSpeaking);

  return (
    <div
      style={{
        position: 'relative',
        width: 'clamp(160px, 28vw, 240px)',
        height: 'clamp(160px, 28vw, 240px)',
        cursor: 'pointer',
        flexShrink: 0,
      }}
      onClick={onClick}
    >
      {/* Waveform canvas */}
      <canvas
        ref={waveRef}
        width={320}
        height={320}
        style={{
          position: 'absolute',
          inset: '-40px',
          borderRadius: '50%',
          pointerEvents: 'none',
          opacity: isSpeaking ? 1 : 0,
          transition: 'opacity 0.5s ease',
        }}
      />

      {/* Main orb container */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          background: 'transparent',
          animation: isSpeaking
            ? 'orb-speak 0.5s ease-in-out infinite alternate'
            : 'orb-breathe 4.5s ease-in-out infinite',
          transition: 'all 0.7s ease',
          overflow: 'hidden',
        }}
      >
        {/* Inner highlight */}
        <div
          style={{
            position: 'absolute',
            top: '9%',
            left: '13%',
            width: '46%',
            height: '46%',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(255,255,255,0.13) 0%, transparent 70%)',
            filter: 'blur(9px)',
          }}
        />
        {/* Rotating conic layer */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            background: 'conic-gradient(from 0deg, transparent 0%, rgba(0,255,255,0.05) 30%, transparent 60%, rgba(0,255,170,0.05) 80%, transparent 100%)',
            animation: 'particle-orbit 14s linear infinite',
          }}
        />
        {/* Neural grid overlay */}
        {isSpeaking && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: '50%',
              backgroundImage: `
                linear-gradient(rgba(0,255,255,0.1) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0,255,255,0.1) 1px, transparent 1px)
              `,
              backgroundSize: '10px 10px',
              animation: 'grid-move 4s linear infinite',
            }}
          />
        )}
      </div>

      {/* Text and Mic Overlay - placed outside the overflow: hidden container */}
      <div style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '8px',
        zIndex: 20,
        width: '150%', // Allow text to extend past the orb's edges
        pointerEvents: 'none', 
      }}>
        <h1 style={{ 
          fontSize: 'clamp(24px, 5vw, 36px)', 
          fontWeight: '400',
          color: '#ffffff',
          margin: 0,
          whiteSpace: 'nowrap',
          textShadow: '0 2px 10px rgba(0,0,0,0.8)'
        }}>
          Hi, I'm <span style={{ fontWeight: '700' }}>AERIS</span>
        </h1>
        
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '8px',
          fontSize: 'clamp(11px, 2vw, 13px)',
          color: 'rgba(255,255,255,0.7)',
          textShadow: '0 2px 4px rgba(0,0,0,0.8)'
        }}>
          <span>an AI</span>
          <div style={{ width: '1px', height: '12px', background: 'rgba(255,255,255,0.3)' }} />
          <span>Assistant &rarr;</span>
          <div style={{
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            border: '1px solid rgba(255,255,255,0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(255,255,255,0.1)',
            backdropFilter: 'blur(4px)',
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}
