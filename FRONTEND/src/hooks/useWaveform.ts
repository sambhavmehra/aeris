'use client';
import { useEffect, useRef } from 'react';

export function useWaveform(
  canvasRef: React.RefObject<HTMLCanvasElement>,
  isSpeaking: boolean
) {
  const phaseRef = useRef(0);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    function draw() {
      if (!canvas) return;
      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;
      const r = w / 2 - 12;
      ctx.clearRect(0, 0, w, h);

      const phase = phaseRef.current;
      const freqs = [0.8, 1.3, 1.9, 2.5, 3.2];
      const amps = freqs.map(f => (Math.sin(phase * f) * 0.4 + 0.6) * (7 + Math.random() * 7));

      ctx.beginPath();
      for (let a = 0; a < Math.PI * 2; a += 0.018) {
        const amp = amps.reduce((s, v, i) => s + v * Math.sin(a * freqs[i] + phase), 0) / freqs.length;
        const ro = r + amp * 0.75;
        const x = cx + Math.cos(a) * ro;
        const y = cy + Math.sin(a) * ro;
        a === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();

      const isHacker = typeof document !== 'undefined' && document.body.classList.contains('hacker');
      const cyanColor = isHacker ? 'rgba(255,51,51,0.28)' : 'rgba(0,255,255,0.28)';
      const cyanMid = isHacker ? 'rgba(255,51,51,0.14)' : 'rgba(0,255,255,0.14)';
      const purpleEnd = isHacker ? 'rgba(255,102,0,0.07)' : 'rgba(0,255,170,0.07)';
      const strokeCol = isHacker ? 'rgba(255,51,51,0.55)' : 'rgba(0,255,255,0.55)';

      const grad = ctx.createRadialGradient(cx, cy, r - 24, cx, cy, r + 24);
      grad.addColorStop(0, cyanColor);
      grad.addColorStop(0.5, cyanMid);
      grad.addColorStop(1, purpleEnd);

      ctx.strokeStyle = strokeCol;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = grad;
      ctx.fill();

      phaseRef.current += 0.065;
      animRef.current = requestAnimationFrame(draw);
    }

    if (isSpeaking) {
      draw();
    } else {
      cancelAnimationFrame(animRef.current);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    return () => cancelAnimationFrame(animRef.current);
  }, [isSpeaking, canvasRef]);
}
