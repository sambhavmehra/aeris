'use client';
import { useEffect, useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  streaming?: boolean;
  agent?: string;
  intent?: string;
}

interface FormField {
  name: string;
  label: string;
  type: string;
  placeholder?: string;
  required?: boolean;
}

interface FormConfig {
  __ui_action__: string;
  title: string;
  description: string;
  server_name: string;
  fields: FormField[];
  submit_endpoint: string;
}

function DynamicForm({ config }: { config: FormConfig }) {
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [discoveredTools, setDiscoveredTools] = useState<any[]>([]);

  const handleInputChange = (name: string, value: string) => {
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: any) => {
    e.preventDefault();
    setStatus('loading');
    setErrorMsg('');

    try {
      const res = await fetch(`http://localhost:8000${config.submit_endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_name: config.server_name,
          env_vars: formData
        })
      });

      if (!res.ok) {
        throw new Error('Server connection request failed.');
      }

      const data = await res.json();
      if (data.success) {
        setStatus('success');
        setDiscoveredTools(data.discovered_tools || []);
      } else {
        setStatus('error');
        setErrorMsg(data.error || 'Failed to verify connection.');
      }
    } catch (err: any) {
      setStatus('error');
      setErrorMsg(err.message || 'Error communicating with backend.');
    }
  };

  if (status === 'success') {
    return (
      <div style={{
        background: 'rgba(16,185,129,0.06)',
        border: '1px solid rgba(16,185,129,0.3)',
        borderRadius: '12px',
        padding: '16px',
        marginTop: '8px',
        color: '#a7f3d0',
        animation: 'msg-appear 0.4s ease',
        width: '100%',
        minWidth: '280px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <span style={{ fontSize: '18px' }}>✅</span>
          <strong style={{ fontSize: '14px', color: '#34d399' }}>Connection Verified!</strong>
        </div>
        <p style={{ fontSize: '12.5px', margin: '0 0 12px 0', lineHeight: '1.5' }}>
          Successfully connected to the <strong>{config.server_name}</strong> MCP server.
          The following {discoveredTools.length} tools have been dynamically registered and are ready to use:
        </p>
        <div style={{
          maxHeight: '120px',
          overflowY: 'auto',
          background: 'rgba(0,0,0,0.2)',
          padding: '8px 12px',
          borderRadius: '8px',
          fontSize: '11px',
          fontFamily: 'monospace'
        }}>
          {discoveredTools.map((t: any) => (
            <div key={t.name} style={{ margin: '4px 0', color: '#6ee7b7' }}>
              • {t.name}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{
      background: 'rgba(3,9,25,0.6)',
      border: '1px solid rgba(var(--cyan-rgb),0.15)',
      borderRadius: '12px',
      padding: '16px',
      marginTop: '8px',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
      width: '100%',
      minWidth: '280px',
      boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      animation: 'msg-appear 0.4s ease'
    }}>
      <div>
        <h4 style={{
          fontSize: '14px',
          fontWeight: 600,
          margin: '0 0 4px 0',
          color: 'rgba(var(--cyan-rgb), 0.95)'
        }}>{config.title}</h4>
        <p style={{
          fontSize: '11.5px',
          margin: 0,
          color: 'rgba(200, 240, 255, 0.6)',
          lineHeight: '1.4'
        }}>{config.description}</p>
      </div>

      {config.fields.map(field => (
        <div key={field.name} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{
            fontSize: '11px',
            fontWeight: 500,
            color: 'rgba(200, 240, 255, 0.8)',
            letterSpacing: '0.5px'
          }}>
            {field.label} {field.required && <span style={{ color: '#ef4444' }}>*</span>}
          </label>
          <input
            type={field.type || 'text'}
            placeholder={field.placeholder}
            required={field.required}
            value={formData[field.name] || ''}
            onChange={e => handleInputChange(field.name, e.target.value)}
            disabled={status === 'loading'}
            style={{
              background: 'rgba(var(--cyan-rgb),0.03)',
              border: '1px solid rgba(var(--cyan-rgb),0.15)',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '12.5px',
              color: 'rgba(200,240,255,0.9)',
              outline: 'none',
              transition: 'border-color 0.2s',
            }}
          />
        </div>
      ))}

      {status === 'error' && (
        <div style={{
          background: 'rgba(239,68,68,0.06)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: '8px',
          padding: '10px 12px',
          fontSize: '12px',
          color: '#fca5a5',
          lineHeight: '1.4'
        }}>
          ⚠️ {errorMsg}
        </div>
      )}

      <button
        type="submit"
        disabled={status === 'loading'}
        style={{
          background: status === 'loading'
            ? 'rgba(var(--cyan-rgb),0.1)'
            : 'linear-gradient(135deg, rgba(var(--cyan-rgb),0.25), rgba(0,140,200,0.2))',
          border: '1px solid rgba(var(--cyan-rgb),0.35)',
          color: 'rgba(var(--cyan-rgb),0.95)',
          borderRadius: '8px',
          padding: '9px',
          fontSize: '13px',
          fontWeight: 500,
          cursor: status === 'loading' ? 'not-allowed' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          transition: 'all 0.2s'
        }}
      >
        {status === 'loading' ? (
          <>
            <span style={{
              width: '12px',
              height: '12px',
              border: '2px solid rgba(var(--cyan-rgb),0.3)',
              borderTopColor: 'rgba(var(--cyan-rgb),0.95)',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite'
            }} />
            Verifying Connection...
          </>
        ) : (
          'Connect Server'
        )}
      </button>
    </form>
  );
}


// Intent -> icon + color mapping
const INTENT_META: Record<string, { icon: string; color: string; label: string }> = {
  chat:        { icon: '💬', color: 'rgba(var(--cyan-rgb),0.7)',  label: 'Chat' },
  security:    { icon: '🛡',  color: 'rgba(255,80,80,0.75)', label: 'Security' },
  system:      { icon: '⚙',  color: 'rgba(255,180,50,0.75)', label: 'System' },
  research:    { icon: '🔍', color: 'rgba(100,220,100,0.75)', label: 'Research' },
  code:        { icon: '💻', color: 'rgba(180,130,255,0.8)', label: 'Code' },
  image:       { icon: '🎨', color: 'rgba(255,140,200,0.8)', label: 'Image' },
  diagram:     { icon: '📊', color: 'rgba(96,165,250,0.85)', label: 'Diagram' },
  codepipeline:{ icon: '📐', color: 'rgba(52,211,153,0.85)', label: 'CodePipeline' },
};

function CodeBlock({
  language,
  codeText,
}: {
  language: string;
  codeText: string;
}) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(codeText.replace(/\n$/, ''));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1000);
    } catch {
      // Fallback: best-effort (some environments may block clipboard)
      try {
        const ta = document.createElement('textarea');
        ta.value = codeText.replace(/\n$/, '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        ta.style.top = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1000);
      } catch {
        // no-op
      }
    }
  }

  return (
    <div style={{ position: 'relative', marginTop: '10px', marginBottom: '10px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'rgba(0,10,30,0.65)',
          border: '1px solid rgba(var(--cyan-rgb),0.15)',
          borderBottom: 'none',
          borderRadius: '8px 8px 0 0',
          padding: '4px 12px',
          fontSize: '10px',
          color: 'rgba(var(--cyan-rgb),0.5)',
          fontFamily: 'monospace',
          textTransform: 'uppercase',
          letterSpacing: '1px',
          gap: '10px',
        }}
      >
        <span>{language}</span>

        <button
          onClick={onCopy}
          type="button"
          style={{
            marginLeft: 'auto',
            cursor: 'pointer',
            background: copied ? 'rgba(var(--cyan-rgb),0.18)' : 'rgba(var(--cyan-rgb),0.08)',
            border: '1px solid rgba(var(--cyan-rgb),0.18)',
            color: copied ? 'rgba(var(--cyan-rgb),0.95)' : 'rgba(var(--cyan-rgb),0.75)',
            borderRadius: '6px',
            padding: '3px 8px',
            fontSize: '9.5px',
            letterSpacing: '0.5px',
            transition: 'background 0.15s ease, border-color 0.15s ease',
          }}
          aria-label="Copy code"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      <SyntaxHighlighter
        PreTag="div"
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          background: 'rgba(0,4,16,0.85)',
          border: '1px solid rgba(var(--cyan-rgb),0.15)',
          borderRadius: '0 0 8px 8px',
          padding: '12px',
          fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
          fontSize: '11.5px',
          lineHeight: 1.55,
        }}
      >
        {codeText.replace(/\n$/, '')}
      </SyntaxHighlighter>
    </div>
  );
}

const CustomMarkdown = ({ content }: { content: string }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ node, ...props }) => (
          <h1
            style={{
              fontSize: '18px',
              fontWeight: 700,
              margin: '16px 0 8px 0',
              background: 'linear-gradient(135deg, var(--cyan), #8b5cf6)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              textShadow: '0 0 15px rgba(var(--cyan-rgb),0.15)',
            }}
            {...props}
          />
        ),
        h2: ({ node, ...props }) => (
          <h2
            style={{
              fontSize: '16px',
              fontWeight: 600,
              margin: '14px 0 6px 0',
              color: 'rgba(var(--cyan-rgb), 0.95)',
              borderBottom: '1px solid rgba(var(--cyan-rgb), 0.1)',
              paddingBottom: '4px',
            }}
            {...props}
          />
        ),
        h3: ({ node, ...props }) => (
          <h3
            style={{
              fontSize: '14px',
              fontWeight: 600,
              margin: '12px 0 6px 0',
              color: 'rgba(200, 240, 255, 0.95)',
            }}
            {...props}
          />
        ),
        p: ({ node, ...props }) => (
          <p
            style={{
              margin: '0 0 10px 0',
              color: 'rgba(200, 240, 255, 0.85)',
              lineHeight: 1.6,
            }}
            {...props}
          />
        ),
        a: ({ node, ...props }) => (
          <a
            style={{
              color: 'var(--cyan)',
              textDecoration: 'none',
              borderBottom: '1px dashed rgba(var(--cyan-rgb), 0.4)',
              transition: 'border-color 0.2s',
            }}
            target="_blank"
            rel="noopener noreferrer"
            {...props}
          />
        ),
        blockquote: ({ node, ...props }) => (
          <blockquote
            style={{
              borderLeft: '3px solid rgba(var(--cyan-rgb), 0.5)',
              background: 'rgba(var(--cyan-rgb), 0.03)',
              padding: '8px 16px',
              margin: '12px 0',
              color: 'rgba(200, 240, 255, 0.7)',
              borderRadius: '0 8px 8px 0',
              fontSize: '12.5px',
              fontStyle: 'italic',
            }}
            {...props}
          />
        ),
        table: ({ node, ...props }) => (
          <div style={{ overflowX: 'auto', margin: '12px 0', borderRadius: '8px', border: '1px solid rgba(var(--cyan-rgb), 0.15)' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '12px',
                textAlign: 'left',
              }}
              {...props}
            />
          </div>
        ),
        thead: ({ node, ...props }) => (
          <thead style={{ background: 'rgba(var(--cyan-rgb), 0.08)' }} {...props} />
        ),
        th: ({ node, ...props }) => (
          <th
            style={{
              padding: '8px 12px',
              fontWeight: 600,
              color: 'rgba(var(--cyan-rgb), 0.95)',
              borderBottom: '1px solid rgba(var(--cyan-rgb), 0.2)',
            }}
            {...props}
          />
        ),
        td: ({ node, ...props }) => (
          <td
            style={{
              padding: '8px 12px',
              color: 'rgba(200, 240, 255, 0.8)',
              borderBottom: '1px solid rgba(var(--cyan-rgb), 0.1)',
            }}
            {...props}
          />
        ),
        ul: ({ node, ...props }) => (
          <ul
            style={{
              paddingLeft: '20px',
              margin: '0 0 10px 0',
              listStyleType: 'disc',
            }}
            {...props}
          />
        ),
        ol: ({ node, ...props }) => (
          <ol
            style={{
              paddingLeft: '20px',
              margin: '0 0 10px 0',
              listStyleType: 'decimal',
            }}
            {...props}
          />
        ),
        li: ({ node, ...props }) => (
          <li
            style={{
              margin: '4px 0',
              color: 'rgba(200, 240, 255, 0.85)',
            }}
            {...props}
          />
        ),
        code: ({ node, className, children, ...props }: any) => {
          const match = /language-(\w+)/.exec(className || '');
          const inline = !match;
          if (inline) {
            return (
              <code
                style={{
                  background: 'rgba(var(--cyan-rgb), 0.12)',
                  color: 'var(--cyan)',
                  padding: '2px 5px',
                  borderRadius: '4px',
                  fontFamily: 'monospace',
                  fontSize: '11.5px',
                }}
                {...props}
              >
                {children}
              </code>
            );
          }
          return (
            <CodeBlock
              language={match[1] || 'text'}
              codeText={String(children).replace(/\n$/, '')}
            />
          );
        }
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

function renderContent(text: string) {
  // Split on [IMAGE:url] and [WIDGET:encoded_html] markers
  const parts = text.split(/(\[IMAGE:https?:\/\/[^\]]+\]|\[WIDGET:[^\]]+\])/g);

  return parts.map((part, index) => {
    // Image marker
    const imageMatch = part.match(/\[IMAGE:(https?:\/\/[^\]]+)\]/);
    if (imageMatch) {
      const imageUrl = imageMatch[1];
      return (
        <div key={index} style={{
          position: 'relative',
          display: 'inline-block',
          borderRadius: '12px',
          overflow: 'hidden',
          border: '1px solid rgba(var(--cyan-rgb),0.25)',
          boxShadow: '0 0 24px rgba(var(--cyan-rgb),0.12), 0 8px 32px rgba(0,0,0,0.4)',
          maxWidth: '100%',
          marginTop: '10px',
          marginBottom: '10px',
        }}>
          <img
            src={imageUrl}
            alt="AERIS Generated Image"
            style={{
              display: 'block',
              maxWidth: '420px',
              width: '100%',
              borderRadius: '11px',
            }}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
          <div style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            padding: '6px 10px',
            background: 'linear-gradient(transparent, rgba(0,4,18,0.85))',
            fontSize: '10px',
            color: 'rgba(var(--cyan-rgb),0.6)',
            letterSpacing: '1px',
          }}>AERIS · AI GENERATED</div>
        </div>
      );
    }

    // Widget marker — render interactive diagram/chart in an iframe
    const widgetMatch = part.match(/\[WIDGET:([^\]]+)\]/);
    if (widgetMatch) {
      const html = decodeURIComponent(widgetMatch[1]);
      return (
        <div key={index} style={{
          marginTop: '14px',
          marginBottom: '10px',
          borderRadius: '16px',
          overflow: 'hidden',
          border: '1px solid rgba(var(--cyan-rgb),0.2)',
          boxShadow: '0 8px 40px rgba(0,0,0,0.5), 0 0 0 1px rgba(var(--cyan-rgb),0.05)',
          width: '100%',
        }}>
          <iframe
            srcDoc={html}
            style={{
              width: '100%',
              height: '520px',
              border: 'none',
              display: 'block',
              borderRadius: '16px',
              background: 'rgba(3,9,25,0.97)',
            }}
            title="AERIS Interactive Diagram"
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      );
    }

    if (!part.trim()) return null;
    return <CustomMarkdown key={index} content={part} />;
  });
}

interface StreamingBubbleProps {
  content: string;
  onDone: () => void;
}

function StreamingBubble({ content, onDone }: StreamingBubbleProps) {
  const [displayed, setDisplayed] = useState('');

  useEffect(() => {
    let i = 0;
    const interval = setInterval(() => {
      if (i < content.length) {
        setDisplayed(content.slice(0, i + 1));
        i++;
      } else {
        clearInterval(interval);
        onDone();
      }
    }, 11);
    return () => clearInterval(interval);
  }, [content, onDone]);

  return (
    <span>
      {renderContent(displayed)}
      <span style={{
        display: 'inline-block',
        width: '2px',
        height: '13px',
        background: 'rgba(var(--cyan-rgb),0.8)',
        marginLeft: '2px',
        verticalAlign: 'middle',
        animation: 'cursor-blink 0.65s ease-in-out infinite',
      }} />
    </span>
  );
}

/* ── Agent Badge ──────────────────────────────────────────────────── */

function AgentBadge({ agent, intent }: { agent?: string; intent?: string }) {
  if (!agent && !intent) return null;

  const meta = INTENT_META[intent || 'chat'] || INTENT_META.chat;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      marginBottom: '6px',
      animation: 'msg-appear 0.3s ease',
    }}>
      <span style={{ fontSize: '12px' }}>{meta.icon}</span>
      <span style={{
        fontSize: '9.5px',
        fontWeight: 600,
        letterSpacing: '1.8px',
        color: meta.color,
        textTransform: 'uppercase',
        textShadow: `0 0 12px ${meta.color.replace(/[\d.]+\)$/, '0.3)')}`,
      }}>
        {agent || meta.label}
      </span>
      {intent && (
        <span style={{
          fontSize: '8.5px',
          color: 'rgba(255,255,255,0.2)',
          letterSpacing: '1px',
          fontWeight: 400,
        }}>
          / {intent}
        </span>
      )}
    </div>
  );
}

/* ── ChatMessage ──────────────────────────────────────────────────── */

interface ChatMessageProps {
  message: Message;
  onStreamDone?: () => void;
}

const ChatMessage = memo(function ChatMessage({ message, onStreamDone }: ChatMessageProps) {
  const isAI = message.role === 'ai';

  // Check if this AI message represents a form request UI Action
  let formConfig: FormConfig | null = null;
  if (isAI && !message.streaming && message.content.trim().startsWith('{')) {
    try {
      const parsed = JSON.parse(message.content);
      if (parsed && parsed.__ui_action__ === 'request_form') {
        formConfig = parsed;
      }
    } catch (e) {
      // not a UI action JSON
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        gap: '10px',
        flexDirection: isAI ? 'row' : 'row-reverse',
        animation: 'msg-appear 0.4s cubic-bezier(0.23,1,0.32,1)',
      }}
    >
      {/* Avatar */}
      <div style={{
        width: '28px',
        height: '28px',
        borderRadius: '50%',
        flexShrink: 0,
        marginTop: '3px',
        ...(isAI ? {
          background: 'radial-gradient(circle at 35% 30%, rgba(var(--cyan-rgb),0.32) 0%, transparent 60%), radial-gradient(circle, #020820 0%, #050f32 100%)',
          border: '1px solid rgba(var(--cyan-rgb),0.3)',
          boxShadow: '0 0 10px rgba(var(--cyan-rgb),0.18)',
        } : {
          background: 'linear-gradient(135deg, rgba(139,92,246,0.28), rgba(0,100,200,0.18))',
          border: '1px solid rgba(139,92,246,0.28)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '9px',
          color: 'rgba(190,160,255,0.85)',
          fontWeight: 500,
          letterSpacing: '0.5px',
        }),
      }}>
        {!isAI && 'YOU'}
      </div>

      {/* Bubble */}
      <div style={{
        maxWidth: '76%',
        padding: '11px 15px',
        borderRadius: isAI ? '4px 14px 14px 14px' : '14px 4px 14px 14px',
        fontSize: '13px',
        lineHeight: 1.65,
        ...(isAI ? {
          background: 'rgba(var(--cyan-rgb),0.05)',
          border: '1px solid rgba(var(--cyan-rgb),0.1)',
          color: 'rgba(200,240,255,0.88)',
        } : {
          background: 'rgba(139,92,246,0.09)',
          border: '1px solid rgba(139,92,246,0.15)',
          color: 'rgba(215,195,255,0.88)',
        }),
      }}>
        {/* Agent badge for AI messages */}
        {isAI && <AgentBadge agent={message.agent} intent={message.intent} />}

        {formConfig ? (
          <DynamicForm config={formConfig} />
        ) : isAI && message.streaming && onStreamDone ? (
          <StreamingBubble content={message.content} onDone={onStreamDone} />
        ) : (
          renderContent(message.content)
        )}
      </div>
    </div>
  );
}, (prev, next) => {
  return (
    prev.message.id === next.message.id &&
    prev.message.content === next.message.content &&
    prev.message.streaming === next.message.streaming &&
    prev.message.agent === next.message.agent &&
    prev.message.intent === next.message.intent
  );
});

export default ChatMessage;
