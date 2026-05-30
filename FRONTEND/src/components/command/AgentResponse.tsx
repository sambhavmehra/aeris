'use client';
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Agent } from '@/store/agentStore';

interface AgentResponseProps {
  agent: Agent;
  content: string;
  messageId: string;
  isStreaming?: boolean;
  onStreamDone?: () => void;
}

export const AgentResponse: React.FC<AgentResponseProps> = ({
  agent,
  content,
  messageId,
  isStreaming = false,
  onStreamDone
}) => {
  const [isSpeaking, setIsSpeaking] = useState(false);

  const handleSpeak = async () => {
    if (isSpeaking) return;
    setIsSpeaking(true);
    try {
      await fetch('http://localhost:8000/api/voice/agent-speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: agent.id,
          text: content
        })
      });
    } catch (e) {
      console.error("Agent speak request failed:", e);
    } finally {
      // Release speaking pulse after a few seconds
      setTimeout(() => setIsSpeaking(false), 3000);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 120, damping: 14 }}
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: `linear-gradient(135deg, ${agent.color}0a 0%, rgba(6, 10, 24, 0.75) 100%)`,
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        border: `1px solid ${agent.color}25`,
        borderLeft: `3px solid ${agent.color}`,
        boxShadow: `0 8px 32px rgba(0, 0, 0, 0.4), inset 0 0 16px ${agent.color}05`,
        borderRadius: '4px 16px 16px 16px',
        margin: '14px 0',
        padding: '16px 20px',
        maxWidth: '85%',
        alignSelf: 'flex-start',
        color: '#fff',
        fontFamily: 'JetBrains Mono, monospace',
      }}
    >
      {/* Top Header Section */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: `1px solid ${agent.color}15`,
        paddingBottom: '8px',
        marginBottom: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '15px' }}>{agent.icon}</span>
          <span style={{ 
            fontSize: '11px', 
            fontWeight: 800, 
            color: agent.color,
            letterSpacing: '1.5px',
            textShadow: `0 0 10px ${agent.color}50`
          }}>
            {agent.codename}
          </span>
          <span style={{ color: `${agent.color}35`, fontSize: '9px' }}>//</span>
          <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {agent.role}
          </span>
        </div>
      </div>

      {/* Message Body Content (ReactMarkdown with Prism highlighting) */}
      <div style={{ fontSize: '13px', lineHeight: '1.6', overflowWrap: 'break-word' }} className="markdown-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code({ node, inline, className, children, ...props }: any) {
              const match = /language-(\w+)/.exec(className || '');
              return !inline && match ? (
                <div style={{ borderRadius: '4px', overflow: 'hidden', margin: '8px 0', fontSize: '11px' }}>
                  <SyntaxHighlighter
                    style={oneDark as any}
                    language={match[1]}
                    PreTag="div"
                    {...props}
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                </div>
              ) : (
                <code
                  style={{
                    background: 'rgba(255, 255, 255, 0.08)',
                    padding: '2px 4px',
                    borderRadius: '3px',
                    fontSize: '11px',
                    color: 'rgba(255, 255, 255, 0.9)',
                  }}
                  {...props}
                >
                  {children}
                </code>
              );
            },
            p: ({ children }) => <p style={{ margin: '0 0 10px 0' }}>{children}</p>,
            ul: ({ children }) => <ul style={{ margin: '0 0 10px 0', paddingLeft: '20px' }}>{children}</ul>,
            ol: ({ children }) => <ol style={{ margin: '0 0 10px 0', paddingLeft: '20px' }}>{children}</ol>,
            li: ({ children }) => <li style={{ margin: '0 0 4px 0' }}>{children}</li>,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>

      {/* Bottom Actions Section */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
        <motion.button
          onClick={handleSpeak}
          whileHover={{ scale: 1.05, background: `${agent.color}15` }}
          whileTap={{ scale: 0.98 }}
          style={{
            background: isSpeaking ? `${agent.color}12` : 'transparent',
            border: `1px solid ${agent.color}35`,
            borderRadius: '4px',
            color: agent.color,
            padding: '4px 10px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '9px',
            outline: 'none',
            fontFamily: 'inherit',
            letterSpacing: '1px',
            boxShadow: isSpeaking ? `0 0 8px ${agent.color}20` : 'none',
            transition: 'all 0.2s ease'
          }}
        >
          <motion.span
            animate={isSpeaking ? { scale: [1, 1.2, 1] } : {}}
            transition={{ repeat: Infinity, duration: 0.6 }}
          >
            🔊
          </motion.span>
          {isSpeaking ? 'TRANSMITTING...' : 'REPLAY'}
        </motion.button>
      </div>
    </motion.div>
  );
};
