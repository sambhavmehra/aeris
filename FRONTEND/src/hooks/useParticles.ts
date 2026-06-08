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
    rOffset: Math.pow(Math.random(), 1 / 3),
    size: Math.random() * 1.5 + 1,
    colorType: Math.random() > 0.2, // 80% neon cyan, 20% neon green
    speedTheta: (Math.random() - 0.5) * 0.015,
    speedPhi: (Math.random() - 0.5) * 0.015,
  };
}

export function useParticles(canvasRef: React.RefObject<HTMLCanvasElement>, isSpeaking: boolean, isHacker: boolean) {
  const speakingRef = useRef(isSpeaking);
  speakingRef.current = isSpeaking;
  const hackerRef = useRef(isHacker);
  hackerRef.current = isHacker;

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

    // Create a dense particle sphere
    for (let i = 0; i < 1000; i++) {
      particles.push(createParticle());
    }

    const focalLength = 400;
    let currentRadius = 260; // Start idle radius

    // Pre-render core gradients to offscreen canvases to avoid createRadialGradient calls on every frame
    const offscreenNormal = document.createElement('canvas');
    offscreenNormal.width = 512;
    offscreenNormal.height = 512;
    const ctxNormal = offscreenNormal.getContext('2d')!;
    const gradNormal = ctxNormal.createRadialGradient(256, 256, 0, 256, 256, 256);
    gradNormal.addColorStop(0, 'rgba(0, 255, 255, 0.18)');
    gradNormal.addColorStop(0.8, 'rgba(0, 255, 255, 0.06)');
    gradNormal.addColorStop(1, 'transparent');
    ctxNormal.fillStyle = gradNormal;
    ctxNormal.beginPath();
    ctxNormal.arc(256, 256, 256, 0, Math.PI * 2);
    ctxNormal.fill();

    const offscreenHacker = document.createElement('canvas');
    offscreenHacker.width = 512;
    offscreenHacker.height = 512;
    const ctxHacker = offscreenHacker.getContext('2d')!;
    const gradHacker = ctxHacker.createRadialGradient(256, 256, 0, 256, 256, 256);
    gradHacker.addColorStop(0, 'rgba(255, 51, 51, 0.18)');
    gradHacker.addColorStop(0.8, 'rgba(255, 51, 51, 0.06)');
    gradHacker.addColorStop(1, 'transparent');
    ctxHacker.fillStyle = gradHacker;
    ctxHacker.beginPath();
    ctxHacker.arc(256, 256, 256, 0, Math.PI * 2);
    ctxHacker.fill();

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
      const baseTargetRadius = speaking ? 260 : 200;
      const targetRadius = baseTargetRadius + voiceAmplitude;
      currentRadius += (targetRadius - currentRadius) * (speaking ? 0.2 : 0.05);

      // Query hacker mode state from reactive ref rather than querying DOM classList every frame
      const isHackerMode = hackerRef.current;

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

        ctx.fillStyle = isHackerMode
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
      
      // Fast draw pre-rendered offscreen gradient scaled to currentRadius
      ctx.save();
      ctx.globalAlpha = speaking ? 1.0 : 0.55;
      const targetCanvas = isHackerMode ? offscreenHacker : offscreenNormal;
      ctx.drawImage(
        targetCanvas,
        cx - currentRadius,
        cy - currentRadius,
        currentRadius * 2,
        currentRadius * 2
      );
      ctx.restore();

      animId = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, [canvasRef]);
}

