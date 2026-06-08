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
      if (dot) {
        dot.style.transform = `translate3d(calc(${mx}px - 50%), calc(${my}px - 50%), 0)`;
      }
    }

    function animate() {
      gx += (mx - gx) * 0.1;
      gy += (my - gy) * 0.1;
      if (glow) {
        glow.style.transform = `translate3d(calc(${gx}px - 50%), calc(${gy}px - 50%), 0)`;
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

