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
}

function createParticle(): Particle {
  return {
    theta: Math.random() * Math.PI * 2,
    phi: Math.acos(2 * Math.random() - 1),
    // Distribute mostly towards the surface for a clearer sphere shape
    rOffset: Math.pow(Math.random(), 1/3), 
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

    // Create a very dense particle sphere (1500 particles)
    for (let i = 0; i < 1500; i++) { 
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

      const renderedParticles = particles.map(p => {
        p.theta += p.speedTheta * (speaking ? 2.5 : 1);
        p.phi += p.speedPhi * (speaking ? 2.5 : 1);

        // Add 3D ripple/waveform effect across the surface when speaking
        const ripple = speaking 
          ? Math.sin(p.theta * 5 + time * 4) * Math.sin(p.phi * 4 - time * 3) * 25
          : 0;

        // Actual distance from center for this particle
        const r = currentRadius * p.rOffset + ripple;

        // 3D coordinates
        const x3d = r * Math.sin(p.phi) * Math.cos(p.theta);
        const y3d = r * Math.cos(p.phi);
        const z3d = r * Math.sin(p.phi) * Math.sin(p.theta);

        return { ...p, x3d, y3d, z3d };
      });

      // Sort back-to-front
      renderedParticles.sort((a, b) => b.z3d - a.z3d);

      renderedParticles.forEach(p => {
        const zDepth = p.z3d + focalLength;
        if (zDepth < 0) return; 

        const scale = focalLength / zDepth;
        const x2d = cx + p.x3d * scale;
        const y2d = cy + p.y3d * scale;

        ctx.beginPath();
        const renderSize = Math.max(0.1, p.size * scale);
        ctx.arc(x2d, y2d, renderSize, 0, Math.PI * 2);

        // Alpha is higher for particles closer to the camera and lower for particles further away
        let alpha = Math.min(1, Math.max(0.1, scale * 0.7));
        
        ctx.fillStyle = p.colorType
          ? `rgba(0, 255, 255, ${alpha})` // Neon cyan
          : `rgba(0, 255, 170, ${alpha * 0.9})`; // Cyber green
        
        // Add a subtle glow for the cyber aesthetic
        ctx.shadowBlur = 4 * scale;
        ctx.shadowColor = ctx.fillStyle;

        ctx.fill();
        ctx.shadowBlur = 0;
      });

      // Draw a subtle center core glow to make it look cohesive like the image
      ctx.beginPath();
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, currentRadius);
      grad.addColorStop(0, speaking ? 'rgba(0, 255, 255, 0.15)' : 'rgba(0, 255, 255, 0.08)');
      grad.addColorStop(0.8, speaking ? 'rgba(0, 255, 255, 0.05)' : 'rgba(0, 255, 255, 0.02)');
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
