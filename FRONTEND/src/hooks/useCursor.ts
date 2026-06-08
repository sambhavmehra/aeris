'use client';
import { useEffect } from 'react';

export function useCursor() {
  useEffect(() => {
    const glow = document.getElementById('aeris-cursor-glow');
    const dot = document.getElementById('aeris-cursor-dot');
    if (!glow || !dot) return;

    let mx = window.innerWidth / 2;
    let my = window.innerHeight / 2;
    let gx = mx, gy = my;
    let animId: number;

    function onMove(e: MouseEvent) {
      mx = e.clientX;
      my = e.clientY;
    }

    function animate() {
      // Sync dot position to animation frame, bypassing DOM style updates on raw mousemove events
      if (dot) {
        dot.style.transform = `translate3d(${mx - 3}px, ${my - 3}px, 0)`;
      }
      
      // Interpolate glow position smoothly
      gx += (mx - gx) * 0.12;
      gy += (my - gy) * 0.12;
      
      if (glow) {
        glow.style.transform = `translate3d(${gx - 110}px, ${gy - 110}px, 0)`;
      }
      
      animId = requestAnimationFrame(animate);
    }

    window.addEventListener('mousemove', onMove);
    animate();
    
    return () => {
      window.removeEventListener('mousemove', onMove);
      cancelAnimationFrame(animId);
    };
  }, []);
}


