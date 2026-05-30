'use client';
import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { soundEngine } from '@/services/SoundEngine';

interface FinalScreenProps {
  onComplete: () => void;
}

export const FinalScreen: React.FC<FinalScreenProps> = ({ onComplete }) => {
  const [showLine1, setShowLine1] = useState(false);
  const [showLine2, setShowLine2] = useState(false);
  const [showLine3, setShowLine3] = useState(false);
  const [showLine4, setShowLine4] = useState(false);
  const [showTotal, setShowTotal] = useState(false);

  useEffect(() => {
    // Play assembly complete chord
    soundEngine.playAssemblyComplete();

    // Typewriter/line-by-line staggered display for the stats
    const t1 = setTimeout(() => setShowLine1(true), 600);
    const t2 = setTimeout(() => setShowLine2(true), 1000);
    const t3 = setTimeout(() => setShowLine3(true), 1400);
    const t4 = setTimeout(() => setShowLine4(true), 1800);
    const t5 = setTimeout(() => setShowTotal(true), 2400);

    // Call onComplete after 4 seconds to transition to the main interface
    const tComplete = setTimeout(() => {
      onComplete();
    }, 4500);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
      clearTimeout(t5);
      clearTimeout(tComplete);
    };
  }, [onComplete]);

  return (
    <div style={{
      position: 'relative',
      width: '100%',
      height: '100vh',
      background: 'radial-gradient(circle, rgba(5,15,35,0.95) 0%, rgba(1,2,5,1) 100%)',
      fontFamily: 'JetBrains Mono, monospace',
      color: '#fff',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden'
    }}>
      {/* Dynamic scan line scan sweep */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%)',
        backgroundSize: '100% 4px',
        zIndex: 2,
        pointerEvents: 'none'
      }} />

      {/* Glow Backdrop */}
      <div style={{
        position: 'absolute',
        width: '400px',
        height: '400px',
        borderRadius: '50%',
        background: 'rgba(0, 255, 255, 0.03)',
        filter: 'blur(80px)',
        zIndex: 1,
        pointerEvents: 'none'
      }} />

      {/* Main Title Container */}
      <div style={{
        zIndex: 5,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        padding: '20px'
      }}>
        {/* Glowing Success Icon */}
        <motion.div
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 100, damping: 10, delay: 0.1 }}
          style={{
            fontSize: '48px',
            color: 'var(--cyan)',
            textShadow: '0 0 20px rgba(0,255,255,0.8)',
            marginBottom: '20px'
          }}
        >
          🌐
        </motion.div>

        {/* Title */}
        <motion.h1
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 80, damping: 12, delay: 0.2 }}
          style={{
            fontSize: '28px',
            fontWeight: 800,
            letterSpacing: '8px',
            color: '#fff',
            textShadow: '0 0 15px rgba(0, 255, 255, 0.75), 0 0 30px rgba(0, 255, 255, 0.3)',
            marginBottom: '40px',
            textTransform: 'uppercase'
          }}
        >
          ALL AGENTS ASSEMBLED
        </motion.h1>

        {/* Console Summary Block */}
        <div style={{
          background: 'rgba(10, 15, 30, 0.5)',
          border: '1px solid rgba(0, 255, 255, 0.1)',
          borderRadius: '4px',
          padding: '24px 36px',
          width: '100%',
          maxWidth: '440px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          gap: '10px',
          boxSizing: 'border-box'
        }}>
          {showLine1 && (
            <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} style={{ width: '100%', display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>CORE AGENTS</span>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>.....................</span>
              <span style={{ color: '#00e5ff', fontWeight: 700 }}>ONLINE (12)</span>
            </motion.div>
          )}

          {showLine2 && (
            <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} style={{ width: '100%', display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>CONTROL AGENTS</span>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>..................</span>
              <span style={{ color: '#ff9100', fontWeight: 700 }}>ONLINE (4)</span>
            </motion.div>
          )}

          {showLine3 && (
            <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} style={{ width: '100%', display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>SWARM AGENTS</span>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>....................</span>
              <span style={{ color: '#a855f7', fontWeight: 700 }}>ONLINE (9)</span>
            </motion.div>
          )}

          {showLine4 && (
            <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} style={{ width: '100%', display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>SPECIAL AGENTS</span>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>..................</span>
              <span style={{ color: '#ff3366', fontWeight: 700 }}>ONLINE (7)</span>
            </motion.div>
          )}

          {showTotal && (
            <motion.div
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '13px',
                fontWeight: 700,
                borderTop: '1px solid rgba(0,255,255,0.2)',
                paddingTop: '12px',
                marginTop: '10px',
                color: 'var(--cyan)',
                textShadow: '0 0 8px rgba(0,255,255,0.4)'
              }}
            >
              <span>TOTAL OPERATIVE SWARM</span>
              <span>32 / 32 ONLINE</span>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};
