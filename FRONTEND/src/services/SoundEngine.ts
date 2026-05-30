'use client';

/**
 * AERIS Procedural Sound Engine
 * Generates cinematic sci-fi sound effects using Web Audio API.
 * Zero external audio files — all sounds are synthesized procedurally.
 */

class AerisSoundEngine {
  private ctx: AudioContext | null = null;
  private masterGain: GainNode | null = null;
  private ambientOsc: OscillatorNode | null = null;
  private ambientGain: GainNode | null = null;
  private muted = false;

  private getCtx(): AudioContext {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      this.masterGain = this.ctx.createGain();
      this.masterGain.gain.value = 0.3;
      this.masterGain.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  private getMaster(): GainNode {
    this.getCtx();
    return this.masterGain!;
  }

  setMuted(muted: boolean) { this.muted = muted; }
  isMuted() { return this.muted; }

  /* ── Core Activation Sounds ──────────────────────── */

  playBootSequence() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    // Rising filtered sweep
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const filter = ctx.createBiquadFilter();

    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(60, now);
    osc.frequency.exponentialRampToValueAtTime(800, now + 2.5);

    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(200, now);
    filter.frequency.exponentialRampToValueAtTime(4000, now + 2.5);
    filter.Q.value = 8;

    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.15, now + 0.3);
    gain.gain.linearRampToValueAtTime(0.08, now + 2);
    gain.gain.linearRampToValueAtTime(0, now + 3);

    osc.connect(filter).connect(gain).connect(this.getMaster());
    osc.start(now);
    osc.stop(now + 3);

    // Sub-bass thump
    const sub = ctx.createOscillator();
    const subGain = ctx.createGain();
    sub.type = 'sine';
    sub.frequency.setValueAtTime(40, now);
    sub.frequency.exponentialRampToValueAtTime(25, now + 1);
    subGain.gain.setValueAtTime(0.2, now);
    subGain.gain.exponentialRampToValueAtTime(0.001, now + 1.5);
    sub.connect(subGain).connect(this.getMaster());
    sub.start(now);
    sub.stop(now + 1.5);
  }

  playLoadingTick() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(1200, now);
    osc.frequency.exponentialRampToValueAtTime(800, now + 0.06);
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
    osc.connect(gain).connect(this.getMaster());
    osc.start(now);
    osc.stop(now + 0.1);
  }

  playLoadingComplete() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    // Two-note chime
    [1400, 1800].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.1, now + i * 0.08);
      gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.08 + 0.3);
      osc.connect(gain).connect(this.getMaster());
      osc.start(now + i * 0.08);
      osc.stop(now + i * 0.08 + 0.35);
    });
  }

  /* ── Agent Arrival Sounds ────────────────────────── */

  playAgentMaterialize() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    // Whoosh + resonance
    const noise = ctx.createBufferSource();
    const buf = ctx.createBuffer(1, ctx.sampleRate * 0.4, ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * 0.3;
    noise.buffer = buf;

    const filter = ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.setValueAtTime(300, now);
    filter.frequency.exponentialRampToValueAtTime(3000, now + 0.15);
    filter.frequency.exponentialRampToValueAtTime(500, now + 0.35);
    filter.Q.value = 3;

    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.12, now + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);

    noise.connect(filter).connect(gain).connect(this.getMaster());
    noise.start(now);
    noise.stop(now + 0.4);

    // Resonance tone
    const osc = ctx.createOscillator();
    const oscGain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(600, now + 0.05);
    osc.frequency.exponentialRampToValueAtTime(400, now + 0.3);
    oscGain.gain.setValueAtTime(0.06, now + 0.05);
    oscGain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    osc.connect(oscGain).connect(this.getMaster());
    osc.start(now + 0.05);
    osc.stop(now + 0.4);
  }

  playStatusChange() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(500, now);
    osc.frequency.linearRampToValueAtTime(900, now + 0.1);
    gain.gain.setValueAtTime(0.06, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
    osc.connect(gain).connect(this.getMaster());
    osc.start(now);
    osc.stop(now + 0.18);
  }

  playAgentOnline() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    // Bright ascending ping
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(800, now);
    osc.frequency.exponentialRampToValueAtTime(1600, now + 0.08);
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
    osc.connect(gain).connect(this.getMaster());
    osc.start(now);
    osc.stop(now + 0.3);
  }

  /* ── Network / Sync Sounds ───────────────────────── */

  playConnectionDraw() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(200, now);
    osc.frequency.exponentialRampToValueAtTime(2000, now + 0.2);
    osc.frequency.exponentialRampToValueAtTime(600, now + 0.35);
    gain.gain.setValueAtTime(0.05, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
    osc.connect(gain).connect(this.getMaster());
    osc.start(now);
    osc.stop(now + 0.45);
  }

  playSyncPulse() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 80;
    gain.gain.setValueAtTime(0.15, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
    osc.connect(gain).connect(this.getMaster());
    osc.start(now);
    osc.stop(now + 0.55);
  }

  /* ── Assembly Complete ───────────────────────────── */

  playAssemblyComplete() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    // Triumphant major chord (C-E-G-C)
    const freqs = [261.63, 329.63, 392.00, 523.25];
    freqs.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, now + i * 0.06);
      gain.gain.linearRampToValueAtTime(0.08, now + i * 0.06 + 0.1);
      gain.gain.setValueAtTime(0.08, now + i * 0.06 + 1.2);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 2.5);
      osc.connect(gain).connect(this.getMaster());
      osc.start(now + i * 0.06);
      osc.stop(now + 2.8);
    });

    // Shimmer
    const shimmer = ctx.createOscillator();
    const shimGain = ctx.createGain();
    shimmer.type = 'triangle';
    shimmer.frequency.setValueAtTime(2000, now);
    shimmer.frequency.exponentialRampToValueAtTime(4000, now + 0.5);
    shimmer.frequency.exponentialRampToValueAtTime(1500, now + 2);
    shimGain.gain.setValueAtTime(0.03, now);
    shimGain.gain.exponentialRampToValueAtTime(0.001, now + 2.5);
    shimmer.connect(shimGain).connect(this.getMaster());
    shimmer.start(now);
    shimmer.stop(now + 2.8);
  }

  /* ── Disassemble Sound ───────────────────────────── */

  playDisassemble() {
    if (this.muted) return;
    const ctx = this.getCtx();
    const now = ctx.currentTime;

    // Descending sweep
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(800, now);
    osc.frequency.exponentialRampToValueAtTime(40, now + 2);
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(3000, now);
    filter.frequency.exponentialRampToValueAtTime(100, now + 2);
    gain.gain.setValueAtTime(0.1, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 2.5);
    osc.connect(filter).connect(gain).connect(this.getMaster());
    osc.start(now);
    osc.stop(now + 2.5);
  }

  /* ── Ambient Hum ─────────────────────────────────── */

  startAmbientHum() {
    if (this.muted || this.ambientOsc) return;
    const ctx = this.getCtx();

    this.ambientOsc = ctx.createOscillator();
    this.ambientGain = ctx.createGain();
    this.ambientOsc.type = 'sine';
    this.ambientOsc.frequency.value = 55;
    this.ambientGain.gain.value = 0;
    this.ambientGain.gain.linearRampToValueAtTime(0.03, ctx.currentTime + 1);
    this.ambientOsc.connect(this.ambientGain).connect(this.getMaster());
    this.ambientOsc.start();
  }

  stopAmbientHum() {
    if (this.ambientOsc && this.ambientGain) {
      const ctx = this.getCtx();
      this.ambientGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.5);
      const osc = this.ambientOsc;
      setTimeout(() => { try { osc.stop(); } catch {} }, 600);
      this.ambientOsc = null;
      this.ambientGain = null;
    }
  }

  /* ── Cleanup ─────────────────────────────────────── */

  dispose() {
    this.stopAmbientHum();
    if (this.ctx) {
      this.ctx.close();
      this.ctx = null;
      this.masterGain = null;
    }
  }
}

// Singleton
export const soundEngine = new AerisSoundEngine();
