'use client';
import { useEffect, useRef } from 'react';

interface Particle {
  theta: number;
  phi: number;
  rOffset: number; // 0 to 1 (0 is center, 1 is surface)
  size: number;
  colorType: boolean;
  speedTheta: number;
  speedPhi: number;
  x3d?: number;
  y3d?: number;
  z3d?: number;
}

function createParticle(): Particle {
  return {
    theta: Math.random() * Math.PI * 2,
    phi: Math.acos(2 * Math.random() - 1),
    // Distribute mostly towards the surface for a clearer sphere shape
    rOffset: Math.pow(Math.random(), 1 / 3),
    size: Math.random() * 1.5 + 1,
    colorType: Math.random() > 0.2, // 80% neon cyan, 20% neon green
    speedTheta: (Math.random() - 0.5) * 0.015,
    speedPhi: (Math.random() - 0.5) * 0.015,
  };
}

export function useParticles(canvasRef: React.RefObject<HTMLCanvasElement>, isSpeaking: boolean) {
  const speakingRef = useRef(isSpeaking);
  speakingRef.current = isSpeaking;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    let animId: number;
    let particles: Particle[] = [];

    function resize() {
      canvas!.width = window.innerWidth;
      canvas!.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    // Create a dense particle sphere (1000 particles is optimal for visuals and performance)
    for (let i = 0; i < 1000; i++) {
      particles.push(createParticle());
    }

    const focalLength = 400;
    let currentRadius = 260; // Start idle radius

    function draw() {
      ctx.clearRect(0, 0, canvas!.width, canvas!.height);
      const speaking = speakingRef.current;
      const cx = canvas!.width / 2;
      const cy = canvas!.height / 2;

      // Simulate voice amplitude to make it pulsate like a voice assistant
      const time = Date.now() / 1000;
      const voiceAmplitude = speaking
        ? (Math.sin(time * 8) * 0.5 + 0.5) * 30 + (Math.sin(time * 23) * 0.5 + 0.5) * 20
        : 0;

      // Smooth radius transition
      const baseTargetRadius = speaking ? 260 : 200; // slightly smaller base so it doesn't get too massive
      const targetRadius = baseTargetRadius + voiceAmplitude;
      currentRadius += (targetRadius - currentRadius) * (speaking ? 0.2 : 0.05);

      // Query hacker mode state once per frame rather than in the loop
      const isHacker = typeof document !== 'undefined' && document.body.classList.contains('hacker');

      // Update positions in-place to avoid garbage collection pressure
      particles.forEach(p => {
        p.theta += p.speedTheta * (speaking ? 2.5 : 1);
        p.phi += p.speedPhi * (speaking ? 2.5 : 1);

        // Add 3D ripple/waveform effect across the surface when speaking
        const ripple = speaking
          ? Math.sin(p.theta * 5 + time * 4) * Math.sin(p.phi * 4 - time * 3) * 25
          : 0;

        // Actual distance from center for this particle
        const r = currentRadius * p.rOffset + ripple;

        // 3D coordinates
        p.x3d = r * Math.sin(p.phi) * Math.cos(p.theta);
        p.y3d = r * Math.cos(p.phi);
        p.z3d = r * Math.sin(p.phi) * Math.sin(p.theta);
      });

      // Use additive blending for natural, high-performance glow
      ctx.globalCompositeOperation = 'lighter';

      particles.forEach(p => {
        const x3d = p.x3d || 0;
        const y3d = p.y3d || 0;
        const z3d = p.z3d || 0;
        const zDepth = z3d + focalLength;
        if (zDepth < 0) return;

        const scale = focalLength / zDepth;
        const x2d = cx + x3d * scale;
        const y2d = cy + y3d * scale;

        ctx.beginPath();
        const renderSize = Math.max(0.1, p.size * scale);
        ctx.arc(x2d, y2d, renderSize, 0, Math.PI * 2);

        // Alpha is higher for particles closer to the camera and lower for particles further away
        let alpha = Math.min(1, Math.max(0.05, scale * 0.5));

        ctx.fillStyle = isHacker
          ? (p.colorType
            ? `rgba(255, 51, 51, ${alpha})`
            : `rgba(255, 102, 0, ${alpha * 0.9})`)
          : (p.colorType
            ? `rgba(0, 255, 255, ${alpha})`
            : `rgba(0, 255, 170, ${alpha * 0.9})`);

        ctx.fill();
      });

      // Reset composite operation to draw center core gradient
      ctx.globalCompositeOperation = 'source-over';

      // Draw a subtle center core glow to make it look cohesive
      ctx.beginPath();
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, currentRadius);
      if (isHacker) {
        grad.addColorStop(0, speaking ? 'rgba(255, 51, 51, 0.18)' : 'rgba(255, 51, 51, 0.10)');
        grad.addColorStop(0.8, speaking ? 'rgba(255, 51, 51, 0.06)' : 'rgba(255, 51, 51, 0.03)');
      } else {
        grad.addColorStop(0, speaking ? 'rgba(0, 255, 255, 0.18)' : 'rgba(0, 255, 255, 0.10)');
        grad.addColorStop(0.8, speaking ? 'rgba(0, 255, 255, 0.06)' : 'rgba(0, 255, 255, 0.03)');
      }
      grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad;
      ctx.arc(cx, cy, currentRadius, 0, Math.PI * 2);
      ctx.fill();

      animId = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, [canvasRef]);
}

