'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import ChatMessage, { Message } from './ChatMessage';

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

  const voiceModeEnabledRef = useRef(false);
  const isProcessingVoiceRef = useRef(false);
  const voiceStatusIntervalRef = useRef<any>(null);
  const startRecognitionRef = useRef<() => void>(() => {});
  const [thinkingStage, setThinkingStage] = useState(0);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const hasOpened = useRef(false);
  const thinkingTimers = useRef<NodeJS.Timeout[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

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
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 600);
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (voiceStatusIntervalRef.current) {
        clearInterval(voiceStatusIntervalRef.current);
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {}
      }
    };
  }, []);


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
    setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: msg }]);
    startThinking();
    onSpeakingChange(true);

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

  // -- Web Speech API for real STT --
  const recognitionRef = useRef<any>(null);

  const stopRecognition = useCallback(() => {
    if (recognitionRef.current) {
      const rec = recognitionRef.current;
      recognitionRef.current = null;
      try {
        rec.stop();
      } catch (e) {
        console.error('Error stopping SpeechRecognition:', e);
      }
    }
    setIsListening(false);
    onSpeakingChange(false);
  }, [onSpeakingChange]);

  const pollVoiceStatus = useCallback(() => {
    if (voiceStatusIntervalRef.current) {
      clearInterval(voiceStatusIntervalRef.current);
    }
    voiceStatusIntervalRef.current = setInterval(async () => {
      if (!voiceModeEnabledRef.current) {
        clearInterval(voiceStatusIntervalRef.current);
        voiceStatusIntervalRef.current = null;
        return;
      }
      try {
        const res = await fetch('http://localhost:8000/api/voice/status');
        if (res.ok) {
          const data = await res.json();
          if (!data.is_speaking) {
            clearInterval(voiceStatusIntervalRef.current);
            voiceStatusIntervalRef.current = null;
            isProcessingVoiceRef.current = false;
            if (voiceModeEnabledRef.current) {
              startRecognitionRef.current();
            }
          }
        } else {
          clearInterval(voiceStatusIntervalRef.current);
          voiceStatusIntervalRef.current = null;
          isProcessingVoiceRef.current = false;
          if (voiceModeEnabledRef.current) {
            startRecognitionRef.current();
          }
        }
      } catch (e) {
        clearInterval(voiceStatusIntervalRef.current);
        voiceStatusIntervalRef.current = null;
        isProcessingVoiceRef.current = false;
        if (voiceModeEnabledRef.current) {
          startRecognitionRef.current();
        }
      }
    }, 500);
  }, []);

  const startRecognition = useCallback(() => {
    if (recognitionRef.current || isProcessingVoiceRef.current) return;

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-IN';
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setIsListening(true);
      onSpeakingChange(true);
    };

    recognition.onresult = async (event: any) => {
      let transcript = '';
      for (let i = event.results.length - 1; i >= 0; i--) {
        const r = event.results[i];
        const text = r?.[0]?.transcript?.trim?.();
        if (text && r.isFinal) {
          transcript = text;
          break;
        }
      }
      if (!transcript) return;

      // Show user message (frontend only)
      setMessages(prev => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'user',
          content: transcript,
        },
      ]);

      const hinglishTranscript = transcript.trim() + '. Bas Hinglish mein jawab do.';

      // Pause mic for processing/speaking
      isProcessingVoiceRef.current = true;
      stopRecognition();

      startThinking();
        try {
          const res = await fetch('http://localhost:8000/api/voice/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript: hinglishTranscript, speak: true }),
          });

          if (!res.ok) throw new Error('Backend error');
          const data = await res.json();
          stopThinking();

          if (data.hacker_mode_activated === true) {
            // Password accepted or voice-keyword auto-activated → switch to hacker UI
            document.body.classList.add('hacker');
            setIsHacker(true);
            addAIMessage(
              data.response_text || data.response || 'Hacker Brain Mode activated.',
              true,
              'Brain',
              'hacker_mode_activation'
            );
          } else if (data.hacker_mode_challenge) {
            // Challenge prompt (password needed) — just display the message
            // Backend remembers the pending challenge state for the next voice input
            addAIMessage(
              data.response_text || data.response || 'Security clearance keyword required.',
              true,
              'Brain',
              'hacker_mode_activation'
            );
          } else if (data.intent === 'hacker_mode_activation' && data.hacker_mode_activated === false) {
            // Access denied — wrong password
            addAIMessage(
              data.response_text || data.response || 'Access Denied. Invalid security clearance.',
              false,
              'Brain',
              'hacker_mode_activation'
            );
          } else if (data.intent === 'hacker_mode_deactivation' || data.hacker_mode_deactivated) {
            document.body.classList.remove('hacker');
            setIsHacker(false);
            addAIMessage(
              data.response_text || data.response || 'Productivity Mode activated.',
              true,
              'Brain',
              data.intent || 'hacker_mode_deactivation'
            );
          } else {
            addAIMessage(
              data.response_text || data.response || 'No response received.',
              true,
              undefined,
              data.intent || undefined,
            );
          }
        } catch (e) {
          stopThinking();
          addAIMessage('Error: Could not process voice command. Backend may be offline.', false);
        } finally {
          pollVoiceStatus();
        }
    };

    recognition.onerror = (event: any) => {
      console.error('Speech recognition error:', event.error);
      if (event?.error !== 'aborted' && event?.error !== 'no-speech') {
        addAIMessage(`Voice error: ${event.error}. Try again.`, false);
      }
      setIsListening(false);
      onSpeakingChange(false);
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      setIsListening(false);
      onSpeakingChange(false);

      if (voiceModeEnabledRef.current && !isProcessingVoiceRef.current) {
        setTimeout(() => {
          if (voiceModeEnabledRef.current && !isProcessingVoiceRef.current) {
            startRecognitionRef.current();
          }
        }, 300);
      }
    };

    try {
      recognition.start();
    } catch (e) {
      console.error('Failed to start SpeechRecognition:', e);
      recognitionRef.current = null;
      setIsListening(false);
      onSpeakingChange(false);
    }
  }, [addAIMessage, onSpeakingChange, startThinking, stopThinking, pollVoiceStatus, stopRecognition]);

  useEffect(() => {
    startRecognitionRef.current = startRecognition;
  }, [startRecognition]);

  const toggleVoice = useCallback(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      addAIMessage('Speech recognition is not supported in this browser. Please use Chrome or Edge.', false);
      return;
    }

    if (voiceModeEnabledRef.current) {
      voiceModeEnabledRef.current = false;
      setIsVoiceModeEnabled(false);
      isProcessingVoiceRef.current = false;
      if (voiceStatusIntervalRef.current) {
        clearInterval(voiceStatusIntervalRef.current);
        voiceStatusIntervalRef.current = null;
      }
      stopRecognition();
    } else {
      voiceModeEnabledRef.current = true;
      setIsVoiceModeEnabled(true);
      startRecognition();
    }
  }, [addAIMessage, startRecognition, stopRecognition]);

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
        <div style={{
          flex: 1, overflowY: 'auto', padding: '20px 24px',
          display: 'flex', flexDirection: 'column', gap: '16px',
        }}>
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
