'use client';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useAgentStore, Agent } from '@/store/agentStore';
import { soundEngine } from '@/services/SoundEngine';
import { AgentPanel } from './AgentPanel';
import { AgentResponse } from './AgentResponse';
import { NetworkGraph } from '../assembly/NetworkGraph';

interface CommandCenterProps {
  onDisassemble: () => void;
  onSpeakingChange: (v: boolean) => void;
}

interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  streaming?: boolean;
  agent?: string;
  intent?: string;
}

const THINKING_STAGES = [
  'ANALYZING CORE DATA...',
  'ROUTING TO TARGET AGENT...',
  'EXECUTING SUB-PROCESSES...',
  'COMPILING RESULTS...'
];

export const CommandCenter: React.FC<CommandCenterProps> = ({
  onDisassemble,
  onSpeakingChange
}) => {
  const agents = useAgentStore((state) => state.agents);
  const triggerDisassembly = useAgentStore((state) => state.triggerDisassembly);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  // States
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [thinkingStage, setThinkingStage] = useState(0);
  const [isMuted, setIsMuted] = useState(soundEngine.isMuted());
  const [isListening, setIsListening] = useState(false);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatScrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const thinkingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Load chat history on mount
  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/api/chat/history');
      if (!res.ok) throw new Error();
      const data = await res.json();
      if (data.history && data.history.length > 0) {
        const mapped: Message[] = data.history
          .filter((m: any) => !m.content.startsWith('[SYSTEM]:'))
          .map((m: any, i: number) => ({
            id: `cc-hist-${i}`,
            role: m.role === 'assistant' ? 'ai' : 'user',
            content: m.content,
            agent: m.agent || undefined,
            intent: m.intent || undefined
          }));
        setMessages(mapped);
      } else {
        // Welcome message
        setMessages([
          {
            id: 'welcome',
            role: 'ai',
            content: 'AERIS Command Center online. Swarm agents synchronized and awaiting orders, Sir.',
            agent: 'aurora'
          }
        ]);
      }
    } catch (e) {
      console.warn("Failed to load history:", e);
      setMessages([
        {
          id: 'welcome-offline',
          role: 'ai',
          content: 'AERIS Command Center online (Offline Mode).',
          agent: 'aurora'
        }
      ]);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Lock window scroll to prevent layout shifting on input focus
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
    lockScroll();
    window.addEventListener('scroll', lockScroll);
    window.addEventListener('resize', lockScroll);
    return () => {
      window.removeEventListener('scroll', lockScroll);
      window.removeEventListener('resize', lockScroll);
    };
  }, []);

  // Scroll to bottom of message list
  const scrollToBottom = () => {
    const container = chatScrollContainerRef.current;
    if (container) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // Toggle Mute
  const handleToggleMute = () => {
    const nextMuted = !isMuted;
    soundEngine.setMuted(nextMuted);
    setIsMuted(nextMuted);
  };

  // Trigger disassembly sequence
  const handleDisassemble = () => {
    triggerDisassembly();
    onDisassemble();
  };

  // Thinking Animation Cycle
  const startThinking = () => {
    setIsTyping(true);
    setThinkingStage(0);
    let current = 0;
    
    if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
    thinkingTimerRef.current = setInterval(() => {
      current = (current + 1) % THINKING_STAGES.length;
      setThinkingStage(current);
    }, 1200);
  };

  const stopThinking = () => {
    if (thinkingTimerRef.current) {
      clearInterval(thinkingTimerRef.current);
      thinkingTimerRef.current = null;
    }
    setIsTyping(false);
  };

  // Send message implementation
  const handleSendMessage = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isTyping) return;
    
    setInput('');
    if (inputRef.current) inputRef.current.focus();

    // Check disassembly command
    if (msg.toLowerCase().includes('agent disassemble') || msg.toLowerCase() === 'disassemble') {
      handleDisassemble();
      return;
    }

    // Append user message
    const userMsgId = Date.now().toString();
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: msg }]);
    
    // Start thinking state
    startThinking();
    onSpeakingChange(true);

    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg })
      });

      if (!res.ok) throw new Error();
      const data = await res.json();
      
      stopThinking();
      onSpeakingChange(false);

      // Append AI response
      const aiMsgId = (Date.now() + 1).toString();
      setMessages(prev => [...prev, {
        id: aiMsgId,
        role: 'ai',
        content: data.response || 'No output recorded.',
        agent: data.agent || undefined,
        intent: data.intent || undefined
      }]);

    } catch (e) {
      stopThinking();
      onSpeakingChange(false);
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'ai',
        content: 'Error: Connection lost with AERIS neural system.',
        agent: 'sentinel'
      }]);
    }
  };

  // Web Speech API Microphone logic
  const handleToggleMic = () => {
    if (isListening) {
      stopMic();
    } else {
      startMic();
    }
  };

  const startMic = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition not supported in this browser.");
      return;
    }

    const rec = new SpeechRecognition();
    rec.lang = 'en-IN';
    rec.continuous = false;
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    recognitionRef.current = rec;

    rec.onstart = () => {
      setIsListening(true);
      onSpeakingChange(true);
    };

    rec.onresult = async (event: any) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (transcript) {
        setIsListening(false);
        onSpeakingChange(false);
        
        // Append user message
        setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: transcript }]);
        
        // Run voice processing path
        startThinking();
        onSpeakingChange(true);

        try {
          // Check disassembly first
          if (transcript.toLowerCase().includes('agent disassemble') || transcript.toLowerCase() === 'disassemble') {
            stopThinking();
            onSpeakingChange(false);
            handleDisassemble();
            return;
          }

          const res = await fetch('http://localhost:8000/api/voice/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript: transcript + '. Bas Hinglish mein jawab do.', speak: true })
          });

          if (!res.ok) throw new Error();
          const data = await res.json();
          
          stopThinking();
          onSpeakingChange(false);

          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'ai',
            content: data.response_text || 'No speech response generated.',
            agent: data.intent || undefined
          }]);
        } catch (e) {
          stopThinking();
          onSpeakingChange(false);
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'ai',
            content: 'Error processing voice command.',
            agent: 'sentinel'
          }]);
        }
      }
    };

    rec.onerror = () => {
      setIsListening(false);
      onSpeakingChange(false);
    };

    rec.onend = () => {
      setIsListening(false);
      onSpeakingChange(false);
    };

    try {
      rec.start();
    } catch (e) {
      console.error(e);
    }
  };

  const stopMic = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }
    setIsListening(false);
    onSpeakingChange(false);
  };

  useEffect(() => {
    return () => {
      if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
      stopMic();
    };
  }, []);

  // ── Filters message list for selected agent thread ─────────────────
  const getCleanAgentId = (agentField?: string) => {
    if (!agentField) return '';
    return agentField.toLowerCase().replace('agent', '').trim();
  };

  const filteredMessages = selectedAgentId
    ? messages.filter((msg, idx) => {
        // Show AI message if it matches selected agent
        if (msg.role === 'ai') {
          return getCleanAgentId(msg.agent) === selectedAgentId.toLowerCase();
        }
        // Show User message if it is immediately followed by a message from that agent
        const nextMsg = messages[idx + 1];
        if (msg.role === 'user' && nextMsg && nextMsg.role === 'ai') {
          return getCleanAgentId(nextMsg.agent) === selectedAgentId.toLowerCase();
        }
        // Show User message if it contains the codename
        const agentObj = agents.find(a => a.id === selectedAgentId);
        if (agentObj && msg.content.toLowerCase().includes(agentObj.codename.toLowerCase())) {
          return true;
        }
        return false;
      })
    : messages;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      width: '100vw',
      height: '100vh',
      background: 'radial-gradient(circle at center, #070d1f 0%, #020307 100%)',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: 'JetBrains Mono, monospace',
      color: '#fff',
      zIndex: 4000,
      overflow: 'hidden'
    }}>
      {/* Moving Holographic Grid Overlay */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: 'linear-gradient(rgba(0, 255, 255, 0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 255, 255, 0.015) 1px, transparent 1px)',
        backgroundSize: '35px 35px',
        backgroundPosition: 'center',
        opacity: 0.8,
        pointerEvents: 'none',
        zIndex: 1,
        animation: 'grid-scroll 360s linear infinite'
      }} />

      {/* Futuristic Scanlines */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.15) 50%)',
        backgroundSize: '100% 4px',
        pointerEvents: 'none',
        zIndex: 2
      }} />

      {/* High-Tech Glowing Ambient Nodes */}
      <div style={{
        position: 'absolute',
        width: '600px',
        height: '600px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0, 229, 255, 0.02) 0%, transparent 70%)',
        top: '-15%',
        left: '-10%',
        pointerEvents: 'none',
        zIndex: 1
      }} />
      <div style={{
        position: 'absolute',
        width: '600px',
        height: '600px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(168, 85, 247, 0.015) 0%, transparent 70%)',
        bottom: '-15%',
        right: '-10%',
        pointerEvents: 'none',
        zIndex: 1
      }} />

      {/* ── Top Bar ── */}
      <div style={{
        height: '56px',
        background: 'rgba(4, 7, 18, 0.8)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderBottom: '1px solid rgba(0, 255, 255, 0.08)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        boxSizing: 'border-box',
        position: 'relative',
        zIndex: 10
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h1 style={{
            fontSize: '15px',
            fontWeight: 800,
            letterSpacing: '3px',
            color: 'var(--cyan)',
            textShadow: '0 0 10px rgba(0, 255, 255, 0.5)',
            margin: 0
          }}>
            AERIS COMMAND CENTER
          </h1>
          <span style={{
            fontSize: '9px',
            padding: '2px 8px',
            background: 'rgba(0, 255, 255, 0.04)',
            border: '1px solid rgba(0, 255, 255, 0.2)',
            borderRadius: '4px',
            color: 'var(--cyan)',
            fontWeight: 700,
            letterSpacing: '1px',
            textShadow: '0 0 5px rgba(0, 255, 255, 0.3)'
          }}>
            SWARM CODES ACTIVE [32/32]
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          {/* Mute button */}
          <button
            onClick={handleToggleMute}
            style={{
              background: 'none',
              border: 'none',
              color: 'rgba(255,255,255,0.6)',
              cursor: 'pointer',
              fontSize: '13px',
              outline: 'none',
              padding: '4px',
              transition: 'transform 0.2s ease'
            }}
            title={isMuted ? "Unmute sound engine" : "Mute sound engine"}
            onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.1)'}
            onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
          >
            {isMuted ? '🔇' : '🔊'}
          </button>
          
          {/* Disassemble button */}
          <button
            onClick={handleDisassemble}
            style={{
              background: 'rgba(255, 51, 102, 0.08)',
              border: '1px solid rgba(255, 51, 102, 0.35)',
              borderRadius: '4px',
              color: '#ff3366',
              padding: '6px 14px',
              fontSize: '9px',
              fontWeight: 800,
              cursor: 'pointer',
              fontFamily: 'inherit',
              letterSpacing: '1.5px',
              transition: 'background 0.2s, box-shadow 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 51, 102, 0.15)';
              e.currentTarget.style.boxShadow = '0 0 8px rgba(255,51,102,0.25)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 51, 102, 0.08)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            DISASSEMBLE
          </button>
        </div>
      </div>

      {/* ── Main Body Layout (3 columns) ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative', zIndex: 5 }}>
        
        {/* Left Side: AgentPanel */}
        <AgentPanel 
          selectedAgentId={selectedAgentId}
          onSelectAgent={setSelectedAgentId}
        />

        {/* Center: Main interaction area */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(3, 5, 12, 0.45)',
          backdropFilter: 'blur(10px)',
          position: 'relative',
          overflow: 'hidden'
        }}>
          {/* Messages scroll list */}
          <div 
            ref={chatScrollContainerRef}
            className="command-chat-scrollbar"
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '20px 24px',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box'
            }}
          >
            {filteredMessages.map((msg) => {
              if (msg.role === 'ai') {
                const messageAgentId = getCleanAgentId(msg.agent) || 'aurora';
                const agentObj = agents.find((a) => a.id === messageAgentId) || {
                  codename: msg.agent || 'SYSTEM',
                  icon: '💬',
                  color: 'var(--cyan)',
                  role: 'AERIS Agent',
                  id: 'aurora'
                } as Agent;

                return (
                  <AgentResponse
                    key={msg.id}
                    agent={agentObj}
                    content={msg.content}
                    messageId={msg.id}
                  />
                );
              } else {
                // User message bubble styled as secure personal transmission
                return (
                  <div
                    key={msg.id}
                    style={{
                      alignSelf: 'flex-end',
                      maxWidth: '75%',
                      background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.06) 0%, rgba(6, 10, 24, 0.8) 100%)',
                      border: '1px solid rgba(168, 85, 247, 0.35)',
                      borderRight: '3px solid #a855f7',
                      borderRadius: '12px 12px 4px 12px',
                      padding: '12px 16px',
                      margin: '8px 0',
                      fontSize: '13px',
                      lineHeight: '1.5',
                      color: 'rgba(255,255,255,0.95)',
                      boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3), 0 0 10px rgba(168, 85, 247, 0.05)',
                      position: 'relative'
                    }}
                  >
                    <div style={{ fontSize: '8px', color: '#a855f7', marginBottom: '6px', textAlign: 'right', letterSpacing: '1px', fontWeight: 700 }}>
                      SECURE TRANSMISSION // USER
                    </div>
                    {msg.content}
                  </div>
                );
              }
            })}

            {/* Thinking / typing stage indicator */}
            {isTyping && (
              <div style={{
                alignSelf: 'flex-start',
                fontSize: '10px',
                color: 'var(--cyan)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 14px',
                background: 'rgba(0, 255, 255, 0.02)',
                border: '1px solid rgba(0, 255, 255, 0.15)',
                borderRadius: '4px',
                margin: '10px 0',
                letterSpacing: '1px',
                boxShadow: '0 0 8px rgba(0,255,255,0.1)',
                animation: 'pulse-glow 1.2s ease-in-out infinite'
              }}>
                <span className="thinking-spinner" style={{ fontSize: '11px' }}>⚡</span>
                <span>{THINKING_STAGES[thinkingStage]}</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Bottom input area */}
          <div style={{
            padding: '16px 24px',
            borderTop: '1px solid rgba(0, 255, 255, 0.06)',
            background: 'rgba(4, 7, 18, 0.75)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            boxSizing: 'border-box'
          }}>
            <form 
              onSubmit={(e) => { e.preventDefault(); handleSendMessage(); }}
              style={{ display: 'flex', gap: '12px', alignItems: 'center' }}
            >
              {/* Voice indicator glow wrap */}
              <div style={{ display: 'flex', flex: 1, position: 'relative' }}>
                <input
                  ref={inputRef}
                  type="text"
                  placeholder={selectedAgentId 
                    ? `DIRECT OBJECTIVE FOR ${agents.find(a=>a.id===selectedAgentId)?.codename || 'AGENT'}...` 
                    : "ENTER COMMAND OR DIRECT OBJECTIVE..."
                  }
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  style={{
                    flex: 1,
                    background: 'rgba(0, 255, 255, 0.01)',
                    border: '1px solid rgba(0, 255, 255, 0.15)',
                    borderRadius: '4px',
                    color: '#fff',
                    padding: '12px 16px',
                    fontSize: '11px',
                    fontFamily: 'inherit',
                    outline: 'none',
                    letterSpacing: '0.5px',
                    boxShadow: isListening ? '0 0 12px rgba(0, 255, 255, 0.15)' : 'inset 0 0 8px rgba(0,255,255,0.03)',
                    transition: 'all 0.25s ease'
                  }}
                  onFocus={(e) => e.target.style.borderColor = 'rgba(0, 255, 255, 0.4)'}
                  onBlur={(e) => e.target.style.borderColor = 'rgba(0, 255, 255, 0.15)'}
                />
              </div>

              {/* Mic button */}
              <button
                type="button"
                onClick={handleToggleMic}
                style={{
                  width: '42px',
                  height: '42px',
                  background: isListening ? 'rgba(255, 51, 102, 0.2)' : 'rgba(0, 255, 255, 0.02)',
                  border: isListening ? '1.5px solid #ff3366' : '1px solid rgba(0, 255, 255, 0.15)',
                  borderRadius: '4px',
                  color: isListening ? '#ff3366' : 'rgba(255, 255, 255, 0.7)',
                  cursor: 'pointer',
                  fontSize: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  outline: 'none',
                  boxShadow: isListening ? '0 0 15px rgba(255,51,102,0.4)' : 'none',
                  transition: 'all 0.2s ease'
                }}
                title={isListening ? "Listening... click to stop" : "Start voice input"}
              >
                {isListening ? '🎤' : '🎙️'}
              </button>

              {/* Send button */}
              <button
                type="submit"
                style={{
                  height: '42px',
                  padding: '0 24px',
                  background: 'rgba(0, 255, 255, 0.08)',
                  border: '1px solid rgba(0, 255, 255, 0.35)',
                  borderRadius: '4px',
                  color: 'var(--cyan)',
                  fontSize: '10px',
                  fontWeight: 800,
                  letterSpacing: '1.5px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  transition: 'all 0.2s ease',
                  outline: 'none',
                  boxShadow: 'inset 0 0 8px rgba(0,255,255,0.05)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(0, 255, 255, 0.15)';
                  e.currentTarget.style.boxShadow = '0 0 10px rgba(0,255,255,0.3)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(0, 255, 255, 0.08)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                TRANSMIT
              </button>
            </form>
          </div>
        </div>

        {/* Right Side: Network Minimap & Diagnostics Telemetry */}
        <div style={{
          width: '200px',
          height: '100%',
          background: 'rgba(3, 6, 15, 0.45)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderLeft: '1px solid rgba(0, 255, 255, 0.06)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '16px',
          boxSizing: 'border-box',
          position: 'relative'
        }}>
          <div style={{
            fontSize: '9px',
            color: 'rgba(255,255,255,0.4)',
            letterSpacing: '1.5px',
            fontWeight: 700,
            borderBottom: '1px solid rgba(0, 255, 255, 0.06)',
            paddingBottom: '8px',
            width: '100%',
            textAlign: 'center',
            marginBottom: '15px'
          }}>
            NETWORK STREAM
          </div>
          
          <div style={{
            flex: 1,
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative'
          }}>
            <NetworkGraph mini={true} />
          </div>

          <div style={{
            fontSize: '8px',
            color: 'rgba(0, 255, 255, 0.4)',
            textAlign: 'center',
            width: '100%',
            marginTop: '8px',
            letterSpacing: '0.5px'
          }}>
            DEVICES DEPLOYED [32]
          </div>

          {/* Diagnostic Stats Widget */}
          <div style={{
            width: '100%',
            background: 'rgba(0, 255, 255, 0.02)',
            border: '1px solid rgba(0, 255, 255, 0.08)',
            borderRadius: '4px',
            padding: '10px',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            marginTop: '15px'
          }}>
            <div style={{ fontSize: '8px', color: 'rgba(0, 255, 255, 0.6)', fontWeight: 700, letterSpacing: '0.5px' }}>
              SYSTEM DIAGNOSTICS
            </div>
            
            {/* CPU Metric */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'rgba(255,255,255,0.5)' }}>
                <span>CPU UTILIZATION</span>
                <span style={{ color: 'var(--cyan)' }}>42%</span>
              </div>
              <div style={{ height: '3px', background: 'rgba(255,255,255,0.05)', borderRadius: '1.5px', overflow: 'hidden' }}>
                <div style={{ height: '100%', background: 'var(--cyan)', width: '42%', animation: 'telemetry-bar 3s infinite ease-in-out' }} />
              </div>
            </div>

            {/* RAM Metric */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'rgba(255,255,255,0.5)' }}>
                <span>MEMORY LOAD</span>
                <span style={{ color: '#a855f7' }}>61%</span>
              </div>
              <div style={{ height: '3px', background: 'rgba(255,255,255,0.05)', borderRadius: '1.5px', overflow: 'hidden' }}>
                <div style={{ height: '100%', background: '#a855f7', width: '61%' }} />
              </div>
            </div>

            {/* Network Bandwidth */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'rgba(255,255,255,0.5)' }}>
                <span>NET DATA RATE</span>
                <span style={{ color: '#ff9100' }}>842 KB/s</span>
              </div>
              <div style={{ height: '3px', background: 'rgba(255,255,255,0.05)', borderRadius: '1.5px', overflow: 'hidden' }}>
                <div style={{ height: '100%', background: '#ff9100', width: '38%', animation: 'telemetry-bar-net 2.5s infinite ease-in-out' }} />
              </div>
            </div>
          </div>
        </div>

      </div>

      <style jsx global>{`
        .command-chat-scrollbar::-webkit-scrollbar {
          width: 2px;
        }
        .command-chat-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .command-chat-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(0, 255, 255, 0.08);
          border-radius: 1px;
        }
        .command-chat-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(0, 255, 255, 0.25);
        }
        @keyframes pulse-glow {
          0%, 100% { opacity: 0.8; }
          50% { opacity: 1; filter: drop-shadow(0 0 2px rgba(0,255,255,0.4)); }
        }
        @keyframes spinner-rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .thinking-spinner {
          display: inline-block;
          animation: spinner-rotate 2s linear infinite;
        }
        @keyframes grid-scroll {
          from { background-position: 0 0; }
          to { background-position: 0 1000px; }
        }
        @keyframes telemetry-bar {
          0%, 100% { width: 42%; }
          30% { width: 58%; }
          70% { width: 35%; }
        }
        @keyframes telemetry-bar-net {
          0%, 100% { width: 38%; }
          45% { width: 72%; }
          80% { width: 20%; }
        }
      `}</style>
    </div>
  );
};
