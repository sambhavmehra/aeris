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
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [thinkingStage, setThinkingStage] = useState(0);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const hasOpened = useRef(false);
  const thinkingTimers = useRef<NodeJS.Timeout[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/chat/history');
        const data = await res.json();
        if (data.history && data.history.length > 0) {
          const mapped: Message[] = data.history.map((m: any, i: number) => ({
            id: `hist-${i}`,
            role: m.role === 'assistant' ? 'ai' : 'user',
            content: m.content,
            streaming: false
          }));
          setMessages(mapped);
          hasOpened.current = true;
        } else if (isOpen && !hasOpened.current) {
          hasOpened.current = true;
          setTimeout(() => {
            addAIMessage('Neural link established. I am AERIS -- Autonomous Enhanced Reasoning Intelligence System. How may I assist you?');
          }, 450);
        }
      } catch (e) {
        console.warn('Failed to fetch history (Backend might be offline/initializing):', e);
        if (isOpen && !hasOpened.current) {
          hasOpened.current = true;
          addAIMessage('Neural link established. I am AERIS. (Offline Mode: History unavailable)');
        }
      }
    };

    if (isOpen) {
      fetchHistory();
    }
  }, [isOpen]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 600);
  }, [isOpen]);

  const addAIMessage = useCallback((content: string, isStreaming = true, agent?: string, intent?: string) => {
    onSpeakingChange(true);
    const id = Date.now().toString();
    setMessages(prev => [...prev, { id, role: 'ai', content, streaming: isStreaming, agent, intent }]);
  }, [onSpeakingChange]);

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

      // Pass agent and intent metadata to the message
      addAIMessage(
        data.response || 'No response received.',
        true,
        data.agent || undefined,
        data.intent || undefined
      );
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

  const toggleVoice = useCallback(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      addAIMessage('Speech recognition is not supported in this browser. Please use Chrome or Edge.', false);
      return;
    }

    // If already listening, stop (manual off)
    if (isListening && recognitionRef.current) {
      recognitionRef.current.onresult = null;
      recognitionRef.current.onerror = null;
      recognitionRef.current.onend = null;

      recognitionRef.current.stop();
      recognitionRef.current = null;
      setIsListening(false);
      onSpeakingChange(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-IN'; // Supports English + Hindi

    // Keep mic ON until user toggles off
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setIsListening(true);
      onSpeakingChange(true);
    };

    recognition.onresult = async (event: any) => {
      // Grab the latest final transcript from the batch
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

      // Enforce Hinglish for voice replies (minimal, affects routing less than rewriting everything)
      const hinglishTranscript =
        transcript.trim() +
        '. Bas Hinglish mein jawab do.';

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

        addAIMessage(
          data.response_text || data.response || 'No response received.',
          true,
          undefined,
          data.intent || undefined,
        );
      } catch (e) {
        stopThinking();
        addAIMessage('Error: Could not process voice command. Backend may be offline.', false);
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
      // Auto-restart only if mic is still ON (manual off should not restart)
      if (recognitionRef.current === recognition && isListening) {
        try {
          recognition.start();
        } catch {
          setIsListening(false);
          onSpeakingChange(false);
          recognitionRef.current = null;
        }
      } else {
        setIsListening(false);
        recognitionRef.current = null;
        onSpeakingChange(false);
      }
    };

    recognition.start();
  }, [isListening, onSpeakingChange, addAIMessage, startThinking, stopThinking]);

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
      background: 'rgba(3,9,25,0.97)',
      border: '1px solid rgba(0,200,255,0.15)',
      borderBottom: 'none',
      borderRadius: isExpanded ? '0' : '24px 24px 0 0',
      zIndex: 200,
      display: 'flex',
      flexDirection: 'column' as const,
      transition: 'transform 0.62s cubic-bezier(0.23,1,0.32,1)',
      backdropFilter: 'blur(40px)',
      WebkitBackdropFilter: 'blur(40px)',
    },
  };

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,4,18,0.72)',
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
          borderBottom: '1px solid rgba(0,200,255,0.08)',
          flexShrink: 0,
        }}>
          <div style={{
            width: '32px', height: '32px', borderRadius: '50%', flexShrink: 0,
            background: 'radial-gradient(circle at 35% 30%, rgba(0,220,255,0.32) 0%, transparent 60%), radial-gradient(circle, #020820 0%, #050f32 100%)',
            border: '1px solid rgba(0,200,255,0.3)',
            boxShadow: '0 0 12px rgba(0,200,255,0.2)',
            animation: 'orb-breathe 4.5s ease-in-out infinite',
          }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '13px', fontWeight: 500, color: 'rgba(0,220,255,0.92)', letterSpacing: '2.5px' }}>AERIS</div>
            <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)', letterSpacing: '1.5px', marginTop: '1px' }}>AUTONOMOUS AI CONSCIOUSNESS</div>
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            style={{
              background: 'rgba(0,200,255,0.06)', border: '1px solid rgba(0,200,255,0.15)',
              color: 'rgba(0,200,255,0.65)', borderRadius: '50%',
              width: '30px', height: '30px', cursor: 'pointer', fontSize: '14px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s', flexShrink: 0,
            }}
            title={isExpanded ? "Minimize" : "Maximize"}
          >{isExpanded ? '↙' : '↗'}</button>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(0,200,255,0.06)', border: '1px solid rgba(0,200,255,0.15)',
              color: 'rgba(0,200,255,0.65)', borderRadius: '50%',
              width: '30px', height: '30px', cursor: 'pointer', fontSize: '13px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s', flexShrink: 0,
            }}
          >✕</button>
        </div>

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
                background: 'radial-gradient(circle at 35% 30%, rgba(0,220,255,0.32) 0%, transparent 60%), radial-gradient(circle, #020820 0%, #050f32 100%)',
                border: '1px solid rgba(0,200,255,0.3)',
                animation: 'orb-breathe 1.5s ease-in-out infinite',
              }} />
              <div style={{
                padding: '10px 16px', borderRadius: '4px 14px 14px 14px',
                background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.1)',
                display: 'flex', flexDirection: 'column', gap: '6px',
              }}>
                {/* Stage text */}
                <div key={thinkingStage} style={{
                  display: 'flex', alignItems: 'center', gap: '8px',
                  fontSize: '11.5px', color: 'rgba(0,220,255,0.7)',
                  letterSpacing: '0.5px',
                  animation: 'thinking-fade 0.4s ease',
                }}>
                  <div style={{
                    width: '6px', height: '6px', borderRadius: '50%',
                    background: 'rgba(0,220,255,0.6)',
                    animation: 'thinking-pulse 1.2s ease-in-out infinite',
                    boxShadow: '0 0 8px rgba(0,220,255,0.4)',
                  }} />
                  {currentStageText}
                </div>

                {/* Bouncing dots */}
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  {[0, 1, 2].map(i => (
                    <div key={i} style={{
                      width: '4px', height: '4px', borderRadius: '50%',
                      background: 'rgba(0,200,255,0.4)',
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
        <div style={{ padding: '12px 20px 20px', borderTop: '1px solid rgba(0,200,255,0.08)', flexShrink: 0 }}>
          {/* Quick actions */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', overflowX: 'auto', paddingBottom: '2px' }}>
            {QUICK_ACTIONS.map(a => (
              <button
                key={a.label}
                onClick={() => sendMessage(a.msg)}
                style={{
                  background: 'rgba(0,200,255,0.04)', border: '1px solid rgba(0,200,255,0.1)',
                  borderRadius: '20px', padding: '5px 13px', fontSize: '11px',
                  color: 'rgba(0,200,255,0.52)', cursor: 'pointer', whiteSpace: 'nowrap',
                  transition: 'all 0.2s', letterSpacing: '0.5px', fontFamily: 'inherit',
                }}
                onMouseEnter={e => {
                  (e.target as HTMLElement).style.background = 'rgba(0,200,255,0.1)';
                  (e.target as HTMLElement).style.color = 'rgba(0,220,255,0.85)';
                }}
                onMouseLeave={e => {
                  (e.target as HTMLElement).style.background = 'rgba(0,200,255,0.04)';
                  (e.target as HTMLElement).style.color = 'rgba(0,200,255,0.52)';
                }}
              >{a.label}</button>
            ))}
          </div>

          {/* Input row */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            background: 'rgba(0,200,255,0.04)', border: '1px solid rgba(0,200,255,0.13)',
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
                background: isListening ? 'rgba(139,92,246,0.28)' : 'rgba(139,92,246,0.1)',
                border: '1px solid rgba(139,92,246,0.22)',
                color: isListening ? 'rgba(190,160,255,0.95)' : 'rgba(160,120,255,0.72)',
                cursor: 'pointer', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                animation: isListening ? 'voice-ring 1s ease-out infinite' : 'none',
                transition: 'all 0.2s', flexShrink: 0,
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
                  : 'linear-gradient(135deg, rgba(0,200,255,0.2), rgba(0,140,200,0.15))',
                border: isTyping
                  ? '1px solid rgba(255,80,80,0.4)'
                  : '1px solid rgba(0,200,255,0.32)',
                color: isTyping ? 'rgba(255,120,120,0.95)' : 'rgba(0,220,255,0.92)',
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
