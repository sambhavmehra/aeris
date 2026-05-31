'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import ChatMessage, { Message } from './ChatMessage';
import { useAgentStore } from '@/store/agentStore';


const QUICK_ACTIONS = [
  { label: 'Capabilities', msg: 'What can you do?' },
  { label: '🤖 Build Project', msg: 'Build me a Python Flask REST API for a todo list' },
  { label: '🎨 Generate Image', msg: 'Generate image of a futuristic cyberpunk cityscape at night' },
  { label: 'Full Recon', msg: 'Do a full recon on example.com' },
  { label: 'Check SSL', msg: 'Check SSL for google.com' },
  { label: 'System Info', msg: 'Get system info' },
  { label: 'Research', msg: 'Search the latest AI news' },
];

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSpeakingChange: (v: boolean) => void;
}

// Thinking stage labels
const THINKING_STAGES = [
  { text: 'Analyzing query...', duration: 800 },
  { text: 'Classifying intent...', duration: 900 },
  { text: 'Routing to agent...', duration: 1200 },
  { text: 'Processing...', duration: 30000 },
];

export default function ChatPanel({ isOpen, onClose, onSpeakingChange }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isHacker, setIsHacker] = useState(false);
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isVoiceModeEnabled, setIsVoiceModeEnabled] = useState(false);
  const [isTyping, setIsTyping] = useState(false);

  // Hacker Mode Challenge State
  const [showHackerPrompt, setShowHackerPrompt] = useState(false);
  const [hackerPassword, setHackerPassword] = useState('');
  const [hackerError, setHackerError] = useState('');

  const [thinkingStage, setThinkingStage] = useState(0);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatScrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const hasOpened = useRef(false);
  const thinkingTimers = useRef<NodeJS.Timeout[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Real-time Voice WebSocket Refs
  const wsRef = useRef<WebSocket | null>(null);
  const audioInContextRef = useRef<AudioContext | null>(null);
  const audioOutContextRef = useRef<AudioContext | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const nextPlayTimeRef = useRef<number>(0);

  const addAIMessage = useCallback((content: string, isStreaming = true, agent?: string, intent?: string) => {
    onSpeakingChange(true);
    const id = Date.now().toString();
    setMessages(prev => [...prev, { id, role: 'ai', content, streaming: isStreaming, agent, intent }]);
  }, [onSpeakingChange]);

  const fetchHistory = useCallback(async () => {
    try {
      const statusRes = await fetch('http://localhost:8000/api/status');
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setIsHacker(!!statusData.hacker_mode);
        if (statusData.hacker_mode) {
          document.body.classList.add('hacker');
        } else {
          document.body.classList.remove('hacker');
        }
      }

      const res = await fetch('http://localhost:8000/api/chat/history');
      const data = await res.json();
      if (data.history && data.history.length > 0) {
        const mapped: Message[] = data.history.map((m: any, i: number) => ({
          id: `hist-${i}`,
          role: m.role === 'assistant' ? 'ai' : 'user',
          content: m.content,
          streaming: false
        }));
        const filtered = mapped.filter((m: Message) => !m.content.startsWith('[SYSTEM]:'));
        setMessages(filtered);
        hasOpened.current = true;
      } else {
        setMessages([]);
        if (!hasOpened.current) {
          hasOpened.current = true;
          setTimeout(() => {
            if (document.body.classList.contains('hacker')) {
              addAIMessage('Neural link established in Hacker Brain Mode. System secure. Ready for OSINT, VAPT, or CTF operations, Sir.', false);
            } else {
              addAIMessage('Neural link established. I am AERIS -- Autonomous Enhanced Reasoning Intelligence System. How may I assist you?', false);
            }
          }, 450);
        }
      }
    } catch (e) {
      console.warn('Failed to fetch history (Backend might be offline/initializing):', e);
      if (!hasOpened.current) {
        hasOpened.current = true;
        addAIMessage('Neural link established. I am AERIS. (Offline Mode: History unavailable)', false);
      }
    }
  }, [addAIMessage]);

  useEffect(() => {
    if (isOpen) {
      fetchHistory();
    }
  }, [isOpen, isHacker, fetchHistory]);

  useEffect(() => {
    const container = chatScrollContainerRef.current;
    if (container) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages, isTyping]);

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 600);
  }, [isOpen]);

  useEffect(() => {
    const lockScroll = () => {
      if (window.scrollY !== 0 || window.scrollX !== 0) {
        window.scrollTo(0, 0);
      }
      if (document.body && document.body.scrollTop !== 0) {
        document.body.scrollTop = 0;
      }
      if (document.documentElement && document.documentElement.scrollTop !== 0) {
        document.documentElement.scrollTop = 0;
      }
    };
    if (isOpen) {
      lockScroll();
      window.addEventListener('scroll', lockScroll);
      window.addEventListener('resize', lockScroll);
    }
    return () => {
      window.removeEventListener('scroll', lockScroll);
      window.removeEventListener('resize', lockScroll);
    };
  }, [isOpen]);




  const handleStreamDone = useCallback((id: string) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, streaming: false } : m));
    onSpeakingChange(false);
  }, [onSpeakingChange]);

  // Start thinking animation
  const startThinking = useCallback(() => {
    setIsTyping(true);
    setThinkingStage(0);
    setActiveAgent(null);

    // Clear any existing timers
    thinkingTimers.current.forEach(t => clearTimeout(t));
    thinkingTimers.current = [];

    let elapsed = 0;
    THINKING_STAGES.forEach((stage, index) => {
      if (index > 0) {
        const timer = setTimeout(() => {
          setThinkingStage(index);
        }, elapsed);
        thinkingTimers.current.push(timer);
      }
      elapsed += stage.duration;
    });
  }, []);

  const stopThinking = useCallback(() => {
    thinkingTimers.current.forEach(t => clearTimeout(t));
    thinkingTimers.current = [];
    setIsTyping(false);
    setThinkingStage(0);
    setActiveAgent(null);
  }, []);

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    stopThinking();
    onSpeakingChange(false);
  }, [stopThinking, onSpeakingChange]);

  const submitHackerPassword = useCallback(async () => {
    if (!hackerPassword.trim()) return;
    try {
      const res = await fetch('http://localhost:8000/api/hacker-mode/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: hackerPassword.trim() })
      });
      const data = await res.json();
      if (data.success) {
        setShowHackerPrompt(false);
        setHackerPassword('');
        setHackerError('');
        document.body.classList.add('hacker');
        setIsHacker(true);
      } else {
        setHackerError(data.message || 'Access Denied.');
      }
    } catch (e) {
      setHackerError('Authentication service offline.');
    }
  }, [hackerPassword]);

  const cancelHackerChallenge = useCallback(() => {
    setShowHackerPrompt(false);
    setHackerPassword('');
    setHackerError('');
    addAIMessage('Security clearance cancelled. Remaining in Productivity Mode.', false);
  }, [addAIMessage]);

  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isTyping) return;
    setInput('');
    
    // Intercept Assembly Command
    if (msg.toLowerCase().includes('agent assemble') || msg.toLowerCase().trim() === 'assemble') {
      onClose();
      useAgentStore.getState().triggerAssembly();
      return;
    }

    setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: msg }]);
    startThinking();
    onSpeakingChange(true);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'process_text', text: msg }));
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error('Backend error');

      const data = await res.json();

      abortControllerRef.current = null;
      stopThinking();

      if (data.hacker_mode_challenge) {
        setShowHackerPrompt(true);
        setHackerPassword('');
        setHackerError('');
        onSpeakingChange(false);
        return;
      }

      // Voice-keyword activation: keyword was in the command, mode already activated
      if (data.hacker_mode_activated) {
        document.body.classList.add('hacker');
        setIsHacker(true);
        addAIMessage(
          data.response || 'Hacker Brain Mode activated.',
          true,
          data.agent || 'Brain',
          data.intent || 'hacker_mode_activation'
        );
        return;
      }

      if (data.intent === 'hacker_mode_deactivation' || data.hacker_mode_deactivated) {
        document.body.classList.remove('hacker');
        setIsHacker(false);
        addAIMessage(
          data.response || 'Productivity Mode activated.',
          true,
          data.agent || 'Brain',
          data.intent || 'hacker_mode_deactivation'
        );
        return;
      } else {
        // Pass agent and intent metadata to the message
        addAIMessage(
          data.response || 'No response received.',
          true,
          data.agent || undefined,
          data.intent || undefined
        );
      }
    } catch (e: any) {
      abortControllerRef.current = null;
      stopThinking();
      if (e?.name === 'AbortError') {
        addAIMessage('⏹ Request cancelled.', false);
      } else {
        addAIMessage('Error: Could not connect to AERIS neural core. System may be offline or initializing.');
      }
    }
  }, [input, isTyping, addAIMessage, onSpeakingChange, startThinking, stopThinking]);

  const stopPlayback = useCallback(() => {
    activeSourcesRef.current.forEach(source => {
      try {
        source.stop();
      } catch (err) {}
    });
    activeSourcesRef.current = [];
    nextPlayTimeRef.current = 0;
  }, []);

  const stopVoiceSession = useCallback(() => {
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }

    if (audioProcessorRef.current) {
      try {
        audioProcessorRef.current.disconnect();
      } catch {}
      audioProcessorRef.current = null;
    }
    if (audioStreamRef.current) {
      try {
        audioStreamRef.current.getTracks().forEach(t => t.stop());
      } catch {}
      audioStreamRef.current = null;
    }
    if (audioInContextRef.current) {
      try {
        audioInContextRef.current.close();
      } catch {}
      audioInContextRef.current = null;
    }

    stopPlayback();
    if (audioOutContextRef.current) {
      try {
        audioOutContextRef.current.close();
      } catch {}
      audioOutContextRef.current = null;
    }

    setIsVoiceModeEnabled(false);
    setIsListening(false);
    onSpeakingChange(false);
    stopThinking();
  }, [stopPlayback, onSpeakingChange, stopThinking]);

  useEffect(() => {
    return () => {
      stopVoiceSession();
    };
  }, [stopVoiceSession]);

  const startVoiceSession = useCallback(async () => {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) {
      addAIMessage('Browser does not support Web Audio API.', false);
      return;
    }
    
    const outContext = new AudioContextClass({ sampleRate: 24000 });
    audioOutContextRef.current = outContext;
    nextPlayTimeRef.current = 0;
    activeSourcesRef.current = [];

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//localhost:8000/ws/voice`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsVoiceModeEnabled(true);
      setIsListening(true);
      onSpeakingChange(true);
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof Blob) {
        const arrayBuffer = await event.data.arrayBuffer();
        const int16Samples = new Int16Array(arrayBuffer);
        
        if (outContext.state === 'suspended') {
          await outContext.resume();
        }
        
        const audioBuffer = outContext.createBuffer(1, int16Samples.length, 24000);
        const channelData = audioBuffer.getChannelData(0);
        for (let i = 0; i < int16Samples.length; i++) {
          channelData[i] = int16Samples[i] / 32768.0;
        }

        const source = outContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(outContext.destination);
        
        activeSourcesRef.current.push(source);
        source.onended = () => {
          activeSourcesRef.current = activeSourcesRef.current.filter(s => s !== source);
        };

        const currentTime = outContext.currentTime;
        const playTime = Math.max(currentTime, nextPlayTimeRef.current);
        source.start(playTime);
        nextPlayTimeRef.current = playTime + audioBuffer.duration;
      } else {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'speak_start') {
            onSpeakingChange(true);
          } else if (data.type === 'speak_end') {
            if (activeSourcesRef.current.length === 0) {
              nextPlayTimeRef.current = 0;
            }
          } else if (data.type === 'transcription') {
            setMessages(prev => [
              ...prev,
              { id: Date.now().toString(), role: 'user', content: data.text }
            ]);
            startThinking();
          } else if (data.type === 'chat_response') {
            stopThinking();
            
            if (data.hacker_mode_activated === true) {
              document.body.classList.add('hacker');
              setIsHacker(true);
              addAIMessage(data.response || 'Hacker Brain Mode activated.', true, 'Brain', 'hacker_mode_activation');
            } else if (data.hacker_mode_challenge) {
              setShowHackerPrompt(true);
              setHackerPassword('');
              setHackerError('');
            } else if (data.intent === 'hacker_mode_activation' && data.hacker_mode_activated === false) {
              addAIMessage(data.response || 'Access Denied. Invalid security clearance.', false, 'Brain', 'hacker_mode_activation');
            } else if (data.intent === 'hacker_mode_deactivation' || data.hacker_mode_deactivated) {
              document.body.classList.remove('hacker');
              setIsHacker(false);
              addAIMessage(data.response || 'Productivity Mode activated.', true, 'Brain', 'hacker_mode_deactivation');
            } else {
              addAIMessage(data.response || 'No response received.', true, data.agent, data.intent);
            }
          } else if (data.type === 'interrupted') {
            stopPlayback();
          }
        } catch (e) {
          console.warn('Failed to parse WebSocket JSON message:', e);
        }
      }
    };

    ws.onerror = (e) => {
      console.error('Voice WebSocket error:', e);
      addAIMessage('Voice connection error. Backing out.', false);
      stopVoiceSession();
    };

    ws.onclose = () => {
      stopVoiceSession();
    };

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;

      const inContext = new AudioContextClass({ sampleRate: 16000 });
      audioInContextRef.current = inContext;

      const source = inContext.createMediaStreamSource(stream);
      const processor = inContext.createScriptProcessor(4096, 1, 1);
      audioProcessorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        const pcmData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(pcmData.buffer);
        }
      };

      source.connect(processor);
      processor.connect(inContext.destination);
    } catch (e) {
      console.error('Failed to access microphone:', e);
      addAIMessage('Mic permission denied. Please allow microphone access to use voice mode.', false);
      stopVoiceSession();
    }
  }, [addAIMessage, onSpeakingChange, startThinking, stopThinking, stopPlayback, stopVoiceSession]);

  const toggleVoice = useCallback(() => {
    if (isVoiceModeEnabled) {
      stopVoiceSession();
    } else {
      startVoiceSession();
    }
  }, [isVoiceModeEnabled, startVoiceSession, stopVoiceSession]);

  const currentStageText = THINKING_STAGES[thinkingStage]?.text || 'Processing...';

  const style = {
    panel: {
      position: 'fixed' as const,
      bottom: 0,
      left: '50%',
      transform: isOpen ? 'translateX(-50%) translateY(0)' : 'translateX(-50%) translateY(100%)',
      width: isExpanded ? '100%' : '92%',
      maxWidth: isExpanded ? '100%' : '1100px',
      height: isExpanded ? '100vh' : '85vh',
      minHeight: '520px',
      background: isHacker ? 'rgba(22, 4, 4, 0.98)' : 'rgba(3,9,25,0.97)',
      borderTop: isHacker ? '1px solid rgba(255,51,51,0.25)' : '1px solid rgba(var(--cyan-rgb),0.15)',
      borderLeft: isHacker ? '1px solid rgba(255,51,51,0.25)' : '1px solid rgba(var(--cyan-rgb),0.15)',
      borderRight: isHacker ? '1px solid rgba(255,51,51,0.25)' : '1px solid rgba(var(--cyan-rgb),0.15)',
      borderBottom: 'none',
      borderRadius: isExpanded ? '0' : '24px 24px 0 0',
      zIndex: 200,
      display: 'flex',
      flexDirection: 'column' as const,
      transition: 'transform 0.62s cubic-bezier(0.23,1,0.32,1)',
      backdropFilter: 'blur(40px)',
      WebkitBackdropFilter: 'blur(40px)',
      boxShadow: isHacker ? '0 -10px 40px rgba(255,51,51,0.12)' : 'none',
    },
  };

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: isHacker ? 'rgba(15, 2, 2, 0.75)' : 'rgba(0,4,18,0.72)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          zIndex: 100,
          opacity: isOpen ? 1 : 0,
          pointerEvents: isOpen ? 'all' : 'none',
          transition: 'opacity 0.5s ease',
        }}
      />

      <div style={style.panel}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          padding: '18px 24px 14px',
          borderBottom: '1px solid rgba(var(--cyan-rgb),0.08)',
          flexShrink: 0,
        }}>
          <div style={{
            width: '32px', height: '32px', borderRadius: '50%', flexShrink: 0,
            background: 'radial-gradient(circle at 35% 30%, rgba(var(--cyan-rgb),0.32) 0%, transparent 60%), radial-gradient(circle, #020820 0%, #050f32 100%)',
            border: '1px solid rgba(var(--cyan-rgb),0.3)',
            boxShadow: '0 0 12px rgba(var(--cyan-rgb),0.2)',
            animation: 'orb-breathe 4.5s ease-in-out infinite',
          }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '13px', fontWeight: 500, color: 'rgba(var(--cyan-rgb),0.92)', letterSpacing: '2.5px' }}>AERIS</div>
            <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)', letterSpacing: '1.5px', marginTop: '1px' }}>AUTONOMOUS AI CONSCIOUSNESS</div>
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            style={{
              background: 'rgba(var(--cyan-rgb),0.06)', border: '1px solid rgba(var(--cyan-rgb),0.15)',
              color: 'rgba(var(--cyan-rgb),0.65)', borderRadius: '50%',
              width: '30px', height: '30px', cursor: 'pointer', fontSize: '14px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s', flexShrink: 0,
            }}
            title={isExpanded ? "Minimize" : "Maximize"}
          >{isExpanded ? '↙' : '↗'}</button>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(var(--cyan-rgb),0.06)', border: '1px solid rgba(var(--cyan-rgb),0.15)',
              color: 'rgba(var(--cyan-rgb),0.65)', borderRadius: '50%',
              width: '30px', height: '30px', cursor: 'pointer', fontSize: '13px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s', flexShrink: 0,
            }}
          >✕</button>
        </div>

        {/* Hacker Password Overlay Challenge */}
        {showHackerPrompt && (
          <div style={{
            position: 'absolute',
            inset: 0,
            top: '64px',
            background: 'rgba(5, 2, 2, 0.95)',
            zIndex: 250,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '40px',
            animation: 'msg-appear 0.3s ease',
          }}>
            <div style={{
              width: '100%',
              maxWidth: '400px',
              background: 'rgba(25, 5, 5, 0.6)',
              border: '1px solid #ff3333',
              borderRadius: '16px',
              padding: '30px',
              boxShadow: '0 0 25px rgba(255,51,51,0.15)',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
              textAlign: 'center',
            }}>
              <div style={{ fontSize: '32px', filter: 'drop-shadow(0 0 10px #ff3333)' }}>🛡️</div>
              <div>
                <h3 style={{ color: '#ff3333', letterSpacing: '2px', fontSize: '16px', margin: '0 0 6px 0', textTransform: 'uppercase' }}>Security Clearance Required</h3>
                <p style={{ color: 'rgba(255,51,51,0.7)', fontSize: '11px', lineHeight: '1.5' }}>Enter authorization key to unlock AERIS Hacker Brain Mode.</p>
              </div>

              <input
                type="password"
                value={hackerPassword}
                onChange={e => setHackerPassword(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submitHackerPassword(); }}
                placeholder="ENTER PASSCODE"
                style={{
                  width: '100%',
                  background: 'rgba(255,51,51,0.05)',
                  border: '1px solid rgba(255,51,51,0.4)',
                  borderRadius: '8px',
                  padding: '12px',
                  color: '#ff3333',
                  fontFamily: 'inherit',
                  textAlign: 'center',
                  fontSize: '14px',
                  letterSpacing: '4px',
                  outline: 'none',
                  boxShadow: 'inset 0 0 10px rgba(255,51,51,0.05)',
                }}
                autoFocus
              />

              {hackerError && (
                <div style={{ color: '#ff4444', fontSize: '11px', letterSpacing: '0.5px' }}>
                  ⚠️ {hackerError}
                </div>
              )}

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  onClick={cancelHackerChallenge}
                  style={{
                    flex: 1,
                    background: 'transparent',
                    border: '1px solid rgba(255,51,51,0.3)',
                    color: 'rgba(255,51,51,0.6)',
                    borderRadius: '8px',
                    padding: '10px 0',
                    fontSize: '12px',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'all 0.2s',
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={submitHackerPassword}
                  style={{
                    flex: 1,
                    background: 'rgba(255,51,51,0.15)',
                    border: '1px solid #ff3333',
                    color: '#ff3333',
                    borderRadius: '8px',
                    padding: '10px 0',
                    fontSize: '12px',
                    fontWeight: 'bold',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'all 0.2s',
                    boxShadow: '0 0 10px rgba(255,51,51,0.2)',
                  }}
                >
                  Authorize
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        <div 
          ref={chatScrollContainerRef}
          style={{
            flex: 1, overflowY: 'auto', padding: '20px 24px',
            display: 'flex', flexDirection: 'column', gap: '16px',
          }}
        >
          {messages.map(msg => (
            <ChatMessage
              key={msg.id}
              message={msg}
              onStreamDone={msg.streaming ? () => handleStreamDone(msg.id) : undefined}
            />
          ))}

          {/* Multi-stage thinking indicator */}
          {isTyping && (
            <div style={{ display: 'flex', gap: '10px', animation: 'msg-appear 0.4s ease' }}>
              <div style={{
                width: '28px', height: '28px', borderRadius: '50%', flexShrink: 0, marginTop: '3px',
                background: 'radial-gradient(circle at 35% 30%, rgba(var(--cyan-rgb),0.32) 0%, transparent 60%), radial-gradient(circle, #020820 0%, #050f32 100%)',
                border: '1px solid rgba(var(--cyan-rgb),0.3)',
                animation: 'orb-breathe 1.5s ease-in-out infinite',
              }} />
              <div style={{
                padding: '10px 16px', borderRadius: '4px 14px 14px 14px',
                background: 'rgba(var(--cyan-rgb),0.05)', border: '1px solid rgba(var(--cyan-rgb),0.1)',
                display: 'flex', flexDirection: 'column', gap: '6px',
              }}>
                {/* Stage text */}
                <div key={thinkingStage} style={{
                  display: 'flex', alignItems: 'center', gap: '8px',
                  fontSize: '11.5px', color: 'rgba(var(--cyan-rgb),0.7)',
                  letterSpacing: '0.5px',
                  animation: 'thinking-fade 0.4s ease',
                }}>
                  <div style={{
                    width: '6px', height: '6px', borderRadius: '50%',
                    background: 'rgba(var(--cyan-rgb),0.6)',
                    animation: 'thinking-pulse 1.2s ease-in-out infinite',
                    boxShadow: '0 0 8px rgba(var(--cyan-rgb),0.4)',
                  }} />
                  {currentStageText}
                </div>

                {/* Bouncing dots */}
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  {[0, 1, 2].map(i => (
                    <div key={i} style={{
                      width: '4px', height: '4px', borderRadius: '50%',
                      background: 'rgba(var(--cyan-rgb),0.4)',
                      animation: `typing-bounce 1.1s ease-in-out infinite`,
                      animationDelay: `${i * 0.18}s`,
                    }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div style={{ padding: '12px 20px 20px', borderTop: '1px solid rgba(var(--cyan-rgb),0.08)', flexShrink: 0 }}>
          {/* Quick actions */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', overflowX: 'auto', paddingBottom: '2px' }}>
            {QUICK_ACTIONS.map(a => (
              <button
                key={a.label}
                onClick={() => sendMessage(a.msg)}
                style={{
                  background: 'rgba(var(--cyan-rgb),0.04)', border: '1px solid rgba(var(--cyan-rgb),0.1)',
                  borderRadius: '20px', padding: '5px 13px', fontSize: '11px',
                  color: 'rgba(var(--cyan-rgb),0.52)', cursor: 'pointer', whiteSpace: 'nowrap',
                  transition: 'all 0.2s', letterSpacing: '0.5px', fontFamily: 'inherit',
                }}
                onMouseEnter={e => {
                  (e.target as HTMLElement).style.background = 'rgba(var(--cyan-rgb),0.1)';
                  (e.target as HTMLElement).style.color = 'rgba(var(--cyan-rgb),0.85)';
                }}
                onMouseLeave={e => {
                  (e.target as HTMLElement).style.background = 'rgba(var(--cyan-rgb),0.04)';
                  (e.target as HTMLElement).style.color = 'rgba(var(--cyan-rgb),0.52)';
                }}
              >{a.label}</button>
            ))}
          </div>

          {/* Input row */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            background: 'rgba(var(--cyan-rgb),0.04)', border: '1px solid rgba(var(--cyan-rgb),0.13)',
            borderRadius: '14px', padding: '9px 12px',
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 80) + 'px';
              }}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
              }}
              placeholder="Interface with AERIS..."
              rows={1}
              style={{
                flex: 1, background: 'none', border: 'none', outline: 'none',
                color: 'rgba(200,240,255,0.88)', fontSize: '13px',
                fontFamily: 'inherit', resize: 'none', lineHeight: '1.4',
                maxHeight: '80px', minHeight: '20px',
              }}
            />
            <button
              onClick={toggleVoice}
              title="Voice input"
              style={{
                width: '32px', height: '32px', borderRadius: '50%',
                background: isListening 
                  ? 'rgba(139,92,246,0.28)' 
                  : (isVoiceModeEnabled ? 'rgba(139,92,246,0.2)' : 'rgba(139,92,246,0.1)'),
                border: isListening 
                  ? '1px solid rgba(139,92,246,0.4)' 
                  : (isVoiceModeEnabled ? '1px solid rgba(139,92,246,0.25)' : '1px solid rgba(139,92,246,0.22)'),
                color: isListening 
                  ? 'rgba(190,160,255,0.95)' 
                  : (isVoiceModeEnabled ? 'rgba(190,160,255,0.8)' : 'rgba(160,120,255,0.72)'),
                cursor: 'pointer', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                animation: isListening ? 'voice-ring 1s ease-out infinite' : 'none',
                transition: 'all 0.2s', flexShrink: 0,
                boxShadow: isListening 
                  ? '0 0 10px rgba(139,92,246,0.4)' 
                  : (isVoiceModeEnabled ? '0 0 6px rgba(139,92,246,0.2)' : 'none'),
              }}
            >🎙</button>
            <button
              onClick={() => isTyping ? handleStop() : sendMessage()}
              title={isTyping ? 'Stop' : 'Send'}
              style={{
                width: '32px', height: '32px',
                borderRadius: isTyping ? '6px' : '50%',
                background: isTyping
                  ? 'linear-gradient(135deg, rgba(255,60,60,0.25), rgba(200,40,40,0.2))'
                  : 'linear-gradient(135deg, rgba(var(--cyan-rgb),0.2), rgba(var(--cyan-rgb),0.15))',
                border: isTyping
                  ? '1px solid rgba(255,80,80,0.4)'
                  : '1px solid rgba(var(--cyan-rgb),0.32)',
                color: isTyping ? 'rgba(255,120,120,0.95)' : 'rgba(var(--cyan-rgb),0.92)',
                cursor: 'pointer', fontSize: '13px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.25s ease', flexShrink: 0,
              }}
            >{isTyping ? '■' : '➤'}</button>
          </div>
        </div>
      </div>
    </>
  );
}
