'use client';
import React, { useEffect, useRef } from 'react';
import { useAgentStore, Agent } from '@/store/agentStore';

interface NetworkGraphProps {
  width?: number;
  height?: number;
  mini?: boolean;
}

export const NetworkGraph: React.FC<NetworkGraphProps> = ({ width, height, mini = false }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const agents = useAgentStore((state) => state.agents);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let rotationAngle = 0;

    // Handle resizing if no dimensions are explicitly passed
    const resizeCanvas = () => {
      if (width && height) {
        canvas.width = width;
        canvas.height = height;
      } else {
        const rect = canvas.parentElement?.getBoundingClientRect();
        canvas.width = rect?.width || 600;
        canvas.height = rect?.height || 500;
      }
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Render loop running at 30/60 fps
    const render = () => {
      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      
      // Scaling factor depending on layout size
      const scale = mini ? 0.35 : Math.min(canvas.width, canvas.height) / 750;

      // Define ring radii
      const rCore = 130 * scale;
      const rControl = 200 * scale;
      const rSwarm = 270 * scale;
      const rSpecial = 330 * scale;

      // Rotation speeds
      rotationAngle += 0.002;
      const specialRotation = rotationAngle * 0.5;

      // Draw background orbits/rings
      ctx.strokeStyle = 'rgba(0, 255, 255, 0.04)';
      ctx.lineWidth = 1;
      [rCore, rControl, rSwarm, rSpecial].forEach((r) => {
        ctx.beginPath();
        ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
        ctx.stroke();
      });

      // Filter to online/working agents
      const onlineAgents = agents.filter((a) => a.status === 'online' || a.status === 'working');

      // ── Draw Connection Lines and Flow Particles ────────────────────────
      const timeOffset = (Date.now() / 1500) % 1.0;

      onlineAgents.forEach((agent) => {
        const coords = getAgentCoordinates(agent, centerX, centerY, scale, specialRotation);
        if (!coords) return;

        const { x: ax, y: ay } = coords;

        // Connection line
        ctx.beginPath();
        ctx.strokeStyle = `${agent.color}25`; // Semi-transparent agent color
        ctx.lineWidth = 1.5;
        ctx.moveTo(ax, ay);
        ctx.lineTo(centerX, centerY);
        ctx.stroke();

        // Flowing particle dot (traveling center-wards)
        const px = ax + (centerX - ax) * timeOffset;
        const py = ay + (centerY - ay) * timeOffset;

        ctx.beginPath();
        ctx.fillStyle = agent.color;
        ctx.arc(px, py, mini ? 1.5 : 2.5, 0, Math.PI * 2);
        ctx.shadowColor = agent.color;
        ctx.shadowBlur = mini ? 2 : 6;
        ctx.fill();
        ctx.shadowBlur = 0; // Reset shadow
      });

      // ── Draw Agent Nodes ────────────────────────────────────────────────
      onlineAgents.forEach((agent) => {
        const coords = getAgentCoordinates(agent, centerX, centerY, scale, specialRotation);
        if (!coords) return;

        const { x: ax, y: ay } = coords;
        const nodeRadius = mini ? 3.5 : 5.5;

        // Outer pulse for active/working agents
        if (agent.status === 'working') {
          const pulseSize = nodeRadius + (Math.sin(Date.now() / 100) * 2 + 3) * (mini ? 0.5 : 1);
          ctx.beginPath();
          ctx.fillStyle = `${agent.color}33`;
          ctx.arc(ax, ay, pulseSize, 0, Math.PI * 2);
          ctx.fill();
        }

        // Inner solid node
        ctx.beginPath();
        ctx.fillStyle = agent.color;
        ctx.arc(ax, ay, nodeRadius, 0, Math.PI * 2);
        ctx.shadowColor = agent.color;
        ctx.shadowBlur = mini ? 3 : 8;
        ctx.fill();
        ctx.shadowBlur = 0; // Reset shadow

        // Node outline/ring
        ctx.strokeStyle = '#02040a';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Node Label (Omitted or tiny in mini mode)
        if (!mini) {
          ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
          ctx.font = '8px "JetBrains Mono", monospace';
          ctx.textAlign = 'center';
          ctx.fillText(agent.codename, ax, ay - 10);
        }
      });

      // ── Draw Central AERIS Node ─────────────────────────────────────────
      const centerRadius = mini ? 12 : 28 * scale;
      const centerPulse = centerRadius + Math.sin(Date.now() / 300) * (mini ? 1 : 2.5);

      // Pulse glow ring
      ctx.beginPath();
      ctx.fillStyle = 'rgba(0, 255, 255, 0.05)';
      ctx.arc(centerX, centerY, centerPulse + (mini ? 3 : 8), 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.fillStyle = 'rgba(0, 255, 255, 0.15)';
      ctx.arc(centerX, centerY, centerPulse, 0, Math.PI * 2);
      ctx.shadowColor = '#00ffff';
      ctx.shadowBlur = mini ? 5 : 15;
      ctx.fill();
      ctx.shadowBlur = 0; // Reset

      ctx.beginPath();
      ctx.fillStyle = '#02040a';
      ctx.arc(centerX, centerY, centerRadius, 0, Math.PI * 2);
      ctx.strokeStyle = '#00ffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      if (!mini) {
        ctx.fillStyle = '#00ffff';
        ctx.font = 'bold 9px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('AERIS', centerX, centerY);
      }

      animationFrameId = requestAnimationFrame(render);
    };

    // Computes polar coordinates mapping agent index to concentric ring position
    const getAgentCoordinates = (
      agent: Agent,
      cx: number,
      cy: number,
      scale: number,
      specialRotation: number
    ) => {
      // Find index within category to distribute evenly along the ring
      const categoryAgents = agents.filter((a) => a.category === agent.category);
      const catIndex = categoryAgents.findIndex((a) => a.id === agent.id);
      if (catIndex === -1) return null;

      const total = categoryAgents.length;
      let angle = (catIndex / total) * Math.PI * 2;
      let radius = 0;

      // Map ring sizes
      const rCore = 130 * scale;
      const rControl = 200 * scale;
      const rSwarm = 270 * scale;
      const rSpecial = 330 * scale;

      switch (agent.category) {
        case 'core':
          radius = rCore;
          angle += rotationAngle * 0.2; // Slowly rotate core ring
          break;
        case 'control':
          radius = rControl;
          angle -= rotationAngle * 0.1; // Rotate counter
          break;
        case 'swarm':
          radius = rSwarm;
          angle += rotationAngle * 0.05;
          break;
        case 'special':
          radius = rSpecial;
          angle += specialRotation; // Orbiting ring
          break;
      }

      return {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
      };
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [agents, width, height, mini]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        display: 'block',
        width: width ? `${width}px` : '100%',
        height: height ? `${height}px` : '100%',
        zIndex: 1,
      }}
    />
  );
};
