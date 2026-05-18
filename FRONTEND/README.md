# AERIS — Autonomous AI Consciousness Interface

A futuristic Next.js AI interface with two states: idle orb and reactive speaking mode.

## Quick Start

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
src/
├── app/
│   ├── globals.css       # All CSS animations & variables
│   ├── layout.tsx        # Root layout + metadata
│   └── page.tsx          # Entry point
├── components/
│   ├── AerisInterface.tsx # Main orchestrator
│   ├── Orb.tsx            # Animated orb + waveform rings
│   ├── ChatPanel.tsx      # Slide-up chat UI
│   └── ChatMessage.tsx    # Message bubble + streaming
└── hooks/
    ├── useParticles.ts    # Canvas particle system
    ├── useWaveform.ts     # Canvas waveform on orb
    └── useCursor.ts       # Custom glow cursor
```

## Features

- **Idle State**: Breathing orb, ambient particles, holographic rings
- **Speaking State**: Reactive waveform, pulsing energy rings, faster particles
- **Chat Panel**: Slides up from bottom, streaming typewriter animation
- **Custom Cursor**: Glowing cyan dot with trailing halo
- **Responsive**: Works on mobile and desktop
- **Quick Actions**: Pre-built prompts for instant demo
- **Code Blocks**: Terminal-style syntax display
- **Voice Mode**: Simulated listening state with pulse animation
