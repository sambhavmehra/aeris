'use client';
import { useState, useRef, useEffect, useCallback } from 'react';

type Stage = 'idle' | 'planner' | 'coder' | 'verifier' | 'complete' | 'error';

interface FileEntry { path: string; description: string; language: string; }
interface Manifest {
  project_name: string; language: string; tech_stack: string[];
  entry_point: string; files: FileEntry[]; run_command: string; reasoning: string;
}
interface VerificationReport {
  passed: boolean; syntax_errors: any[]; runtime_output: string;
  runtime_error: string; llm_review: string; files_checked: number;
}
interface WrittenFile { path: string; content: string; }

const API = 'http://localhost:8000';

const STAGES = [
  { key: 'planner', label: 'Planning', icon: '📐', desc: 'Designing workspace...' },
  { key: 'coder', label: 'Coding', icon: '💻', desc: 'Writing source files...' },
  { key: 'verifier', label: 'Verifying', icon: '🔍', desc: 'Testing & reviewing...' },
];

export default function CodePipelinePage() {
  const [objective, setObjective] = useState('');
  const [language, setLanguage] = useState('python');
  const [stage, setStage] = useState<Stage>('idle');
  const [stageMsg, setStageMsg] = useState('');
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [writtenFiles, setWrittenFiles] = useState<WrittenFile[]>([]);
  const [report, setReport] = useState<VerificationReport | null>(null);
  const [error, setError] = useState('');
  const [projectPath, setProjectPath] = useState('');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [codingProgress, setCodingProgress] = useState({ current: 0, total: 0, file: '' });
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const startTimer = () => {
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed(p => p + 0.1), 100);
  };
  const stopTimer = () => { if (timerRef.current) clearInterval(timerRef.current); };

  useEffect(() => () => { stopTimer(); wsRef.current?.close(); }, []);

  const launchPipeline = useCallback(async () => {
    if (!objective.trim() || stage !== 'idle') return;
    setStage('planner'); setStageMsg('Initializing pipeline...'); setError('');
    setManifest(null); setWrittenFiles([]); setReport(null); setProjectPath('');
    setSelectedFile(null); setCodingProgress({ current: 0, total: 0, file: '' });
    startTimer();

    try {
      const res = await fetch(`${API}/api/codepipeline/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective, language }),
      });
      if (!res.ok) throw new Error('Pipeline API failed');
      const data = await res.json();
      const pid = data.pipeline_id;
      if (!pid) throw new Error('No pipeline_id returned');

      // Connect WebSocket for live updates
      const ws = new WebSocket(`ws://localhost:8000/ws/codepipeline/${pid}`);
      wsRef.current = ws;

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.stage) setStage(msg.stage as Stage);
          if (msg.message) setStageMsg(msg.message);

          if (msg.stage === 'planner' && msg.manifest) {
            setManifest(msg.manifest);
          }
          if (msg.stage === 'coder' && msg.file) {
            setCodingProgress({ current: msg.progress_current || 0, total: msg.progress_total || 0, file: msg.file });
          }
          if (msg.stage === 'coder' && msg.written_file) {
            setWrittenFiles(prev => [...prev, msg.written_file]);
          }
          if (msg.stage === 'verifier' && msg.report) {
            setReport(msg.report);
          }
          if (msg.stage === 'complete') {
            setStage('complete');
            if (msg.project_path) setProjectPath(msg.project_path);
            stopTimer();
          }
          if (msg.stage === 'error') {
            setStage('error'); setError(msg.message || 'Pipeline failed');
            stopTimer();
          }
        } catch {}
      };
      ws.onerror = () => { setStage('error'); setError('WebSocket connection failed'); stopTimer(); };
      ws.onclose = () => { if (stage !== 'complete' && stage !== 'error') {} };
    } catch (e: any) {
      setStage('error'); setError(e.message); stopTimer();
    }
  }, [objective, language, stage]);

  const reset = () => {
    wsRef.current?.close(); stopTimer();
    setStage('idle'); setStageMsg(''); setManifest(null); setWrittenFiles([]);
    setReport(null); setError(''); setProjectPath(''); setSelectedFile(null);
    setCodingProgress({ current: 0, total: 0, file: '' }); setElapsed(0);
  };

  const stageIndex = STAGES.findIndex(s => s.key === stage);
  const selectedContent = writtenFiles.find(f => f.path === selectedFile)?.content || '';

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#000', overflow: 'auto', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>
      {/* Background */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, backgroundImage: 'linear-gradient(rgba(0,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(0,255,255,0.02) 1px, transparent 1px)', backgroundSize: '30px 30px' }} />
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, background: 'radial-gradient(ellipse 60% 55% at 50% 30%, rgba(0,20,40,0.5) 0%, transparent 70%)' }} />

      {/* Content */}
      <div style={{ position: 'relative', zIndex: 1, maxWidth: '1200px', margin: '0 auto', padding: '32px 24px' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '32px' }}>
          <a href="/" style={{ color: 'rgba(0,255,255,0.5)', textDecoration: 'none', fontSize: '13px', letterSpacing: '2px' }}>← AERIS</a>
          <div style={{ flex: 1 }} />
          <div style={{ fontSize: '11px', color: 'rgba(0,255,255,0.3)', letterSpacing: '3px' }}>AUTONOMOUS CODE PIPELINE</div>
        </div>

        {/* Title */}
        <h1 style={{ fontSize: '28px', fontWeight: 300, color: 'rgba(0,255,255,0.9)', letterSpacing: '4px', marginBottom: '8px' }}>
          Code Pipeline
        </h1>
        <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.3)', letterSpacing: '1px', marginBottom: '32px' }}>
          Planner → Coder → Verifier — Fully autonomous code generation
        </p>

        {/* Input Section */}
        {stage === 'idle' && (
          <div style={{ background: 'rgba(0,255,255,0.03)', border: '1px solid rgba(0,255,255,0.1)', borderRadius: '16px', padding: '24px', marginBottom: '32px', animation: 'msg-appear 0.5s ease' }}>
            <label style={{ fontSize: '11px', color: 'rgba(0,255,255,0.5)', letterSpacing: '2px', display: 'block', marginBottom: '12px' }}>DESCRIBE YOUR PROJECT</label>
            <textarea
              value={objective} onChange={e => setObjective(e.target.value)}
              placeholder="e.g. Build a Flask REST API for a todo list with SQLite database..."
              rows={4}
              style={{ width: '100%', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,255,255,0.08)', borderRadius: '10px', padding: '14px 16px', color: 'rgba(200,240,255,0.88)', fontSize: '13px', fontFamily: 'inherit', resize: 'vertical', outline: 'none', lineHeight: '1.6' }}
            />
            <div style={{ display: 'flex', gap: '12px', marginTop: '16px', alignItems: 'center' }}>
              <select value={language} onChange={e => setLanguage(e.target.value)}
                style={{ background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(0,255,255,0.12)', borderRadius: '8px', padding: '8px 14px', color: 'rgba(0,255,255,0.7)', fontSize: '12px', fontFamily: 'inherit', outline: 'none', cursor: 'pointer' }}>
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="typescript">TypeScript</option>
                <option value="go">Go</option>
                <option value="rust">Rust</option>
              </select>
              <div style={{ flex: 1 }} />
              <button onClick={launchPipeline} disabled={!objective.trim()}
                style={{ background: objective.trim() ? 'linear-gradient(135deg, rgba(0,255,255,0.15), rgba(0,200,255,0.1))' : 'rgba(255,255,255,0.03)', border: `1px solid ${objective.trim() ? 'rgba(0,255,255,0.3)' : 'rgba(255,255,255,0.08)'}`, borderRadius: '10px', padding: '10px 28px', color: objective.trim() ? 'rgba(0,255,255,0.9)' : 'rgba(255,255,255,0.2)', fontSize: '12px', fontFamily: 'inherit', cursor: objective.trim() ? 'pointer' : 'default', letterSpacing: '2px', transition: 'all 0.3s' }}>
                🚀 LAUNCH PIPELINE
              </button>
            </div>
            {/* Quick templates */}
            <div style={{ display: 'flex', gap: '8px', marginTop: '14px', flexWrap: 'wrap' }}>
              {['Flask REST API with SQLite', 'Express.js CRUD server', 'Python CLI calculator', 'FastAPI websocket chat'].map(t => (
                <button key={t} onClick={() => setObjective(`Build a ${t}`)}
                  style={{ background: 'rgba(0,255,255,0.04)', border: '1px solid rgba(0,255,255,0.08)', borderRadius: '16px', padding: '5px 12px', fontSize: '10px', color: 'rgba(0,255,255,0.4)', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.2s' }}>
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Pipeline Progress */}
        {stage !== 'idle' && (
          <div style={{ marginBottom: '28px', animation: 'msg-appear 0.5s ease' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <span style={{ fontSize: '11px', color: 'rgba(0,255,255,0.5)', letterSpacing: '2px' }}>PIPELINE</span>
              <div style={{ flex: 1, height: '1px', background: 'rgba(0,255,255,0.08)' }} />
              <span style={{ fontSize: '11px', color: 'rgba(0,255,255,0.3)' }}>{elapsed.toFixed(1)}s</span>
            </div>

            {/* Step indicators */}
            <div style={{ display: 'flex', gap: '4px', marginBottom: '20px' }}>
              {STAGES.map((s, i) => {
                const isActive = s.key === stage;
                const isDone = stageIndex > i || stage === 'complete';
                const bg = isDone ? 'rgba(0,255,170,0.12)' : isActive ? 'rgba(0,255,255,0.08)' : 'rgba(255,255,255,0.02)';
                const border = isDone ? 'rgba(0,255,170,0.3)' : isActive ? 'rgba(0,255,255,0.25)' : 'rgba(255,255,255,0.06)';
                const color = isDone ? 'rgba(0,255,170,0.9)' : isActive ? 'rgba(0,255,255,0.8)' : 'rgba(255,255,255,0.25)';
                return (
                  <div key={s.key} style={{ flex: 1, background: bg, border: `1px solid ${border}`, borderRadius: '10px', padding: '14px 16px', transition: 'all 0.5s' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '16px' }}>{isDone ? '✅' : s.icon}</span>
                      <span style={{ fontSize: '12px', color, letterSpacing: '1px', fontWeight: 500 }}>{s.label}</span>
                      {isActive && <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'rgba(0,255,255,0.6)', marginLeft: 'auto', animation: 'thinking-pulse 1.2s ease-in-out infinite' }} />}
                    </div>
                    {isActive && <div style={{ fontSize: '10px', color: 'rgba(0,255,255,0.4)', marginTop: '6px' }}>{stageMsg || s.desc}</div>}
                  </div>
                );
              })}
            </div>

            {/* Coding progress bar */}
            {stage === 'coder' && codingProgress.total > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'rgba(0,255,255,0.4)', marginBottom: '6px' }}>
                  <span>Writing: {codingProgress.file}</span>
                  <span>{codingProgress.current}/{codingProgress.total}</span>
                </div>
                <div style={{ height: '3px', background: 'rgba(0,255,255,0.06)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(codingProgress.current / codingProgress.total) * 100}%`, background: 'linear-gradient(90deg, rgba(0,255,255,0.4), rgba(0,255,170,0.5))', borderRadius: '2px', transition: 'width 0.5s ease' }} />
                </div>
              </div>
            )}

            {/* Complete / Error banner */}
            {stage === 'complete' && (
              <div style={{ background: 'rgba(0,255,170,0.06)', border: '1px solid rgba(0,255,170,0.2)', borderRadius: '10px', padding: '14px 18px', display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                <span style={{ fontSize: '20px' }}>🎉</span>
                <div>
                  <div style={{ fontSize: '13px', color: 'rgba(0,255,170,0.9)', fontWeight: 500 }}>Pipeline Complete!</div>
                  {projectPath && <div style={{ fontSize: '10px', color: 'rgba(0,255,170,0.5)', marginTop: '2px' }}>{projectPath}</div>}
                </div>
                <div style={{ flex: 1 }} />
                <button onClick={reset} style={{ background: 'rgba(0,255,255,0.06)', border: '1px solid rgba(0,255,255,0.15)', borderRadius: '8px', padding: '6px 16px', fontSize: '11px', color: 'rgba(0,255,255,0.6)', cursor: 'pointer', fontFamily: 'inherit' }}>New Project</button>
              </div>
            )}
            {stage === 'error' && (
              <div style={{ background: 'rgba(255,60,60,0.06)', border: '1px solid rgba(255,60,60,0.2)', borderRadius: '10px', padding: '14px 18px', marginBottom: '16px' }}>
                <div style={{ fontSize: '13px', color: 'rgba(255,100,100,0.9)' }}>❌ Pipeline Error</div>
                <div style={{ fontSize: '11px', color: 'rgba(255,100,100,0.5)', marginTop: '4px' }}>{error}</div>
                <button onClick={reset} style={{ marginTop: '10px', background: 'rgba(255,100,100,0.08)', border: '1px solid rgba(255,100,100,0.2)', borderRadius: '8px', padding: '6px 16px', fontSize: '11px', color: 'rgba(255,100,100,0.7)', cursor: 'pointer', fontFamily: 'inherit' }}>Try Again</button>
              </div>
            )}
          </div>
        )}

        {/* Manifest Panel */}
        {manifest && (
          <div style={{ background: 'rgba(0,255,255,0.03)', border: '1px solid rgba(0,255,255,0.1)', borderRadius: '14px', padding: '20px', marginBottom: '24px', animation: 'msg-appear 0.5s ease' }}>
            <div style={{ fontSize: '11px', color: 'rgba(0,255,255,0.5)', letterSpacing: '2px', marginBottom: '14px' }}>📐 WORKSPACE MANIFEST</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '16px' }}>
              {[
                ['Project', manifest.project_name],
                ['Language', manifest.language],
                ['Stack', manifest.tech_stack.join(', ')],
                ['Entry', manifest.entry_point],
                ['Run', manifest.run_command],
              ].map(([k, v]) => (
                <div key={k as string} style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '10px 12px' }}>
                  <div style={{ fontSize: '9px', color: 'rgba(0,255,255,0.35)', letterSpacing: '1.5px', marginBottom: '4px' }}>{k}</div>
                  <div style={{ fontSize: '12px', color: 'rgba(0,255,255,0.75)' }}>{v}</div>
                </div>
              ))}
            </div>
            {manifest.reasoning && (
              <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.35)', borderTop: '1px solid rgba(0,255,255,0.06)', paddingTop: '10px' }}>
                💡 {manifest.reasoning}
              </div>
            )}
          </div>
        )}

        {/* File Explorer + Code Viewer */}
        {writtenFiles.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: '16px', marginBottom: '24px', animation: 'msg-appear 0.5s ease' }}>
            {/* File tree */}
            <div style={{ background: 'rgba(0,255,255,0.03)', border: '1px solid rgba(0,255,255,0.1)', borderRadius: '14px', padding: '16px', maxHeight: '500px', overflowY: 'auto' }}>
              <div style={{ fontSize: '10px', color: 'rgba(0,255,255,0.4)', letterSpacing: '2px', marginBottom: '12px' }}>FILES ({writtenFiles.length})</div>
              {writtenFiles.map(f => (
                <div key={f.path} onClick={() => setSelectedFile(f.path)}
                  style={{ padding: '7px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '11px', marginBottom: '2px', color: selectedFile === f.path ? 'rgba(0,255,255,0.9)' : 'rgba(0,255,255,0.5)', background: selectedFile === f.path ? 'rgba(0,255,255,0.08)' : 'transparent', transition: 'all 0.2s', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '12px' }}>{f.path.endsWith('.py') ? '🐍' : f.path.endsWith('.js') || f.path.endsWith('.ts') ? '📜' : f.path.endsWith('.json') ? '📋' : f.path.endsWith('.md') ? '📄' : '📁'}</span>
                  {f.path}
                </div>
              ))}
            </div>
            {/* Code viewer */}
            <div style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,255,255,0.08)', borderRadius: '14px', overflow: 'hidden' }}>
              <div style={{ padding: '10px 16px', borderBottom: '1px solid rgba(0,255,255,0.06)', fontSize: '11px', color: 'rgba(0,255,255,0.5)' }}>
                {selectedFile || 'Select a file'}
              </div>
              <pre style={{ padding: '16px', margin: 0, fontSize: '11px', lineHeight: '1.6', color: 'rgba(200,240,255,0.8)', overflowX: 'auto', maxHeight: '440px', overflowY: 'auto' }}>
                {selectedContent || '// Click a file to view its contents'}
              </pre>
            </div>
          </div>
        )}

        {/* Verification Report */}
        {report && (
          <div style={{ background: report.passed ? 'rgba(0,255,170,0.03)' : 'rgba(255,60,60,0.03)', border: `1px solid ${report.passed ? 'rgba(0,255,170,0.15)' : 'rgba(255,60,60,0.15)'}`, borderRadius: '14px', padding: '20px', animation: 'msg-appear 0.5s ease' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <span style={{ fontSize: '18px' }}>{report.passed ? '✅' : '❌'}</span>
              <span style={{ fontSize: '14px', color: report.passed ? 'rgba(0,255,170,0.9)' : 'rgba(255,100,100,0.9)', fontWeight: 500 }}>
                Verification {report.passed ? 'PASSED' : 'FAILED'}
              </span>
              <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)', marginLeft: 'auto' }}>{report.files_checked} files checked</span>
            </div>

            {report.syntax_errors.length > 0 && (
              <div style={{ marginBottom: '14px' }}>
                <div style={{ fontSize: '10px', color: 'rgba(255,100,100,0.6)', letterSpacing: '1px', marginBottom: '6px' }}>SYNTAX ERRORS</div>
                {report.syntax_errors.map((e: any, i: number) => (
                  <div key={i} style={{ fontSize: '11px', color: 'rgba(255,100,100,0.7)', padding: '4px 0' }}>
                    • {e.file} line {e.line}: {e.message}
                  </div>
                ))}
              </div>
            )}

            {report.runtime_output && (
              <div style={{ marginBottom: '14px' }}>
                <div style={{ fontSize: '10px', color: 'rgba(0,255,255,0.4)', letterSpacing: '1px', marginBottom: '6px' }}>RUNTIME OUTPUT</div>
                <pre style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '10px', fontSize: '10px', color: 'rgba(200,240,255,0.6)', maxHeight: '150px', overflow: 'auto', margin: 0 }}>
                  {report.runtime_output}
                </pre>
              </div>
            )}

            {report.runtime_error && (
              <div style={{ marginBottom: '14px' }}>
                <div style={{ fontSize: '10px', color: 'rgba(255,100,100,0.5)', letterSpacing: '1px', marginBottom: '6px' }}>RUNTIME ERROR</div>
                <pre style={{ background: 'rgba(255,0,0,0.04)', borderRadius: '8px', padding: '10px', fontSize: '10px', color: 'rgba(255,100,100,0.6)', maxHeight: '150px', overflow: 'auto', margin: 0 }}>
                  {report.runtime_error}
                </pre>
              </div>
            )}

            {report.llm_review && (
              <div>
                <div style={{ fontSize: '10px', color: 'rgba(0,255,255,0.4)', letterSpacing: '1px', marginBottom: '6px' }}>AI CODE REVIEW</div>
                <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.5)', lineHeight: '1.7', whiteSpace: 'pre-wrap' }}>{report.llm_review}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
