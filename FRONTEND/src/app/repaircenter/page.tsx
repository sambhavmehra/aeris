'use client';
import { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

type State = 'idle' | 'analyzing' | 'plan_ready' | 'repairing' | 'complete' | 'error';

interface Issue {
  issue_type: string;
  file_path: string;
  error_msg: string;
  line_number: number | null;
  severity: string;
}

interface ProposedFix {
  file_path: string;
  description: string;
  original_content: string | null;
  fixed_content: string | null;
  command: string | null;
  risk_level: string;
}

interface RepairPlan {
  repair_id: string;
  issues: Issue[];
  proposed_fixes: ProposedFix[];
  risk_level: string;
  dry_run: boolean;
  auto_apply: boolean;
  requires_approval: boolean;
  explanation: string;
}

interface RepairResult {
  repair_id: string;
  success: boolean;
  issues_found: number;
  issues_fixed: number;
  files_changed: string[];
  commands_run: string[];
  verification_status: string;
  remaining_risks: string[];
  report: string;
}

interface PendingWatcherRepair {
  repair_id: string;
  rel_path: string;
  error: string;
  timestamp: string;
}

interface RepairMemory {
  failure_patterns: {
    agent: string;
    error_type: string;
    error_msg: string;
    root_cause: string;
    fix_applied: string;
    occurrences: number;
    last_seen: string;
    resolved: boolean;
  }[];
  known_fixes: Record<string, string>;
  user_preferences: {
    auto_email_on_failure: boolean;
    preferred_fix_style: string;
  };
  personal_notes: string[];
  stats: {
    total_repairs: number;
    successful_repairs: number;
    failed_repairs: number;
    most_common_error: string | null;
  };
  last_updated: string | null;
}

interface RepairHistoryItem {
  repair_id: string;
  timestamp: string;
  success: boolean;
  issues_found: number;
  issues_fixed: number;
  files_changed: string[];
  verification: string;
  type?: string;
  agent?: string;
  root_cause?: string;
}

const API = 'http://localhost:8000';

function RepairCenterContent() {
  const [description, setDescription] = useState('');
  const [targetPath, setTargetPath] = useState('');
  const [state, setState] = useState<State>('idle');
  const [plan, setPlan] = useState<RepairPlan | null>(null);
  const [result, setResult] = useState<RepairResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  
  // Sidebar data states
  const [pendingWatcher, setPendingWatcher] = useState<PendingWatcherRepair[]>([]);
  const [memory, setMemory] = useState<RepairMemory | null>(null);
  const [history, setHistory] = useState<RepairHistoryItem[]>([]);
  const [newNote, setNewNote] = useState('');

  // Polling ref/states
  const [activeRepairId, setActiveRepairId] = useState<string | null>(null);
  const [repairProgress, setRepairProgress] = useState(50);
  const [repairStageMsg, setRepairStageMsg] = useState('Initializing self-healing...');
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const searchParams = useSearchParams();
  const idParam = searchParams.get('id');
  const hasInitialized = useRef(false);

  // Fetch sidebar data
  const fetchSidebarData = useCallback(async () => {
    try {
      const wpRes = await fetch(`${API}/api/watcher/pending`);
      if (wpRes.ok) {
        const wpData = await wpRes.json();
        setPendingWatcher(wpData.pending_repairs || []);
      }
      
      const memRes = await fetch(`${API}/api/repair/memory`);
      if (memRes.ok) {
        const memData = await memRes.json();
        setMemory(memData);
      }

      const histRes = await fetch(`${API}/api/repair/history`);
      if (histRes.ok) {
        const histData = await histRes.json();
        // Show last 5
        setHistory(histData.reverse().slice(0, 5));
      }
    } catch (e) {
      console.error("Failed to load sidebar data", e);
    }
  }, []);

  // Poll status during execution
  const startPolling = useCallback((repairId: string) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    
    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API}/api/repair/status/${repairId}`);
        if (!res.ok) return;
        const data = await res.json();
        
        if (data.progress) setRepairProgress(data.progress);
        if (data.status) {
          if (data.status === 'repairing') {
            setRepairStageMsg('Applying targeted code corrections...');
          } else if (data.status === 'complete' || data.status === 'complete_dry_run') {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            setResult(data.result);
            setState('complete');
            fetchSidebarData();
          } else if (data.status === 'failed') {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            setState('error');
            setErrorMsg(data.result?.report || 'Repair execution failed.');
            fetchSidebarData();
          }
        }
      } catch (e) {
        console.error("Error polling repair status", e);
      }
    }, 1500);
  }, [fetchSidebarData]);

  useEffect(() => {
    if (idParam && state === 'idle' && !hasInitialized.current) {
      hasInitialized.current = true;
      setState('repairing');
      setActiveRepairId(idParam);
      startPolling(idParam);
    }
  }, [idParam, state, startPolling]);

  useEffect(() => {
    fetchSidebarData();
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [fetchSidebarData]);

  // Handle analysis
  const handleAnalyze = async () => {
    if (!description.trim()) return;
    setState('analyzing');
    setErrorMsg('');
    setPlan(null);
    setResult(null);

    try {
      const res = await fetch(`${API}/api/repair/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description, target_path: targetPath || null })
      });
      if (!res.ok) throw new Error('Analysis request failed');
      const planData: RepairPlan = await res.json();
      setPlan(planData);
      setState('plan_ready');
    } catch (e: any) {
      setState('error');
      setErrorMsg(e.message || 'An error occurred during analysis.');
    }
  };

  // Run repair execution
  const handleExecute = async (dryRun: boolean) => {
    if (!plan) return;
    setState('repairing');
    setRepairProgress(50);
    setRepairStageMsg('Preparing workspace patch...');

    try {
      const res = await fetch(`${API}/api/repair/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repair_plan: plan,
          dry_run: dryRun,
          auto_apply: !dryRun
        })
      });
      if (!res.ok) throw new Error('Failed to run repair plan');
      const runData = await res.json();
      setActiveRepairId(runData.repair_id);
      startPolling(runData.repair_id);
    } catch (e: any) {
      setState('error');
      setErrorMsg(e.message || 'Failed to start repair execution.');
    }
  };

  // Add memory note
  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNote.trim()) return;
    try {
      const res = await fetch(`${API}/api/repair/memory/note`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: newNote })
      });
      if (res.ok) {
        setNewNote('');
        fetchSidebarData();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handlePendingRepairClick = (item: PendingWatcherRepair) => {
    setDescription(`Watcher detected error in file: ${item.rel_path}\nError: ${item.error}`);
    setTargetPath(item.rel_path);
  };

  const reset = () => {
    setState('idle');
    setDescription('');
    setTargetPath('');
    setPlan(null);
    setResult(null);
    setErrorMsg('');
    setActiveRepairId(null);
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'radial-gradient(circle at center, #070d1f 0%, #020307 100%)',
      overflow: 'auto',
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      color: '#fff'
    }}>
      {/* Background Grid & Scanlines */}
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
        backgroundImage: 'linear-gradient(rgba(0,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(0,255,255,0.015) 1px, transparent 1px)',
        backgroundSize: '30px 30px',
      }} />
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
        background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06))',
        backgroundSize: '100% 4px, 6px 100%',
        opacity: 0.4
      }} />

      {/* Main Container */}
      <div style={{
        position: 'relative',
        zIndex: 1,
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
      }}>
        
        {/* Header Bar */}
        <header style={{
          height: '56px',
          borderBottom: '1px solid rgba(0,255,255,0.08)',
          background: 'rgba(6,10,24,0.7)',
          backdropFilter: 'blur(16px)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 24px',
          justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <a href="/" style={{
              color: 'rgba(0,255,255,0.5)',
              textDecoration: 'none',
              fontSize: '11px',
              letterSpacing: '2.5px',
              fontWeight: 'bold',
              transition: 'color 0.2s'
            }}
            onMouseEnter={e => e.currentTarget.style.color = '#00ffff'}
            onMouseLeave={e => e.currentTarget.style.color = 'rgba(0,255,255,0.5)'}
            >
              ← AERIS
            </a>
            <div style={{ width: '1px', height: '16px', background: 'rgba(0,255,255,0.15)' }} />
            <h1 style={{
              fontSize: '13px',
              fontWeight: 800,
              letterSpacing: '3px',
              color: '#fff',
              margin: 0,
            }}>
              REPAIR CENTER
            </h1>
          </div>
          
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'rgba(255,109,0,0.1)',
            border: '1px solid rgba(255,109,0,0.3)',
            borderRadius: '20px',
            padding: '4px 12px',
          }}>
            <span style={{ fontSize: '11px' }}>🛠️</span>
            <span style={{ fontSize: '9px', color: '#ff6d00', fontWeight: 800, letterSpacing: '2px' }}>MEDIC ONLINE</span>
          </div>
        </header>

        {/* Content Layout */}
        <div style={{
          display: 'flex',
          flex: 1,
          overflow: 'hidden',
        }}>
          
          {/* Main Area (Left) */}
          <main style={{
            flex: 1,
            padding: '28px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
          }}>
            
            {/* IDLE STATE */}
            {state === 'idle' && (
              <div style={{
                background: 'rgba(6,10,24,0.7)',
                border: '1px solid rgba(0,255,255,0.08)',
                borderRadius: '14px',
                padding: '24px',
                backdropFilter: 'blur(16px)',
                animation: 'fadeIn 0.3s ease-out'
              }}>
                <h2 style={{
                  fontSize: '11px',
                  color: 'rgba(0,255,255,0.4)',
                  letterSpacing: '2px',
                  fontWeight: 700,
                  margin: '0 0 16px 0',
                  textTransform: 'uppercase'
                }}>
                  Submit Failure Log / Diagnostics
                </h2>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <label style={{ fontSize: '9px', letterSpacing: '2px', fontWeight: 700, color: 'rgba(0,255,255,0.4)', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
                      Target File Path (Optional)
                    </label>
                    <input
                      type="text"
                      value={targetPath}
                      onChange={e => setTargetPath(e.target.value)}
                      placeholder="e.g. BACKEND/brain.py"
                      style={{
                        width: '100%',
                        background: 'rgba(0,255,255,0.01)',
                        border: '1px solid rgba(0,255,255,0.15)',
                        borderRadius: '4px',
                        color: '#fff',
                        padding: '10px 12px',
                        fontSize: '11px',
                        fontFamily: 'inherit',
                        outline: 'none',
                        transition: 'border-color 0.2s',
                      }}
                      onFocus={e => e.currentTarget.style.borderColor = 'rgba(0,255,255,0.4)'}
                      onBlur={e => e.currentTarget.style.borderColor = 'rgba(0,255,255,0.15)'}
                    />
                  </div>

                  <div>
                    <label style={{ fontSize: '9px', letterSpacing: '2px', fontWeight: 700, color: 'rgba(0,255,255,0.4)', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
                      Problem Details / Error Logs
                    </label>
                    <textarea
                      value={description}
                      onChange={e => setDescription(e.target.value)}
                      placeholder="Describe the issue or paste error traceback details..."
                      rows={10}
                      style={{
                        width: '100%',
                        background: 'rgba(0,255,255,0.01)',
                        border: '1px solid rgba(0,255,255,0.15)',
                        borderRadius: '4px',
                        color: '#fff',
                        padding: '12px',
                        fontSize: '11px',
                        fontFamily: 'inherit',
                        lineHeight: '1.6',
                        resize: 'vertical',
                        outline: 'none',
                        transition: 'border-color 0.2s',
                      }}
                      onFocus={e => e.currentTarget.style.borderColor = 'rgba(0,255,255,0.4)'}
                      onBlur={e => e.currentTarget.style.borderColor = 'rgba(0,255,255,0.15)'}
                    />
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '8px' }}>
                    <button
                      onClick={handleAnalyze}
                      disabled={!description.trim()}
                      style={{
                        background: description.trim() ? 'transparent' : 'rgba(255,255,255,0.02)',
                        border: `1px solid ${description.trim() ? 'rgba(0,255,255,0.3)' : 'rgba(255,255,255,0.05)'}`,
                        borderRadius: '4px',
                        fontSize: '10px',
                        fontWeight: 800,
                        letterSpacing: '1.5px',
                        padding: '8px 20px',
                        color: description.trim() ? 'var(--cyan)' : 'rgba(255,255,255,0.15)',
                        cursor: description.trim() ? 'pointer' : 'default',
                        transition: 'all 0.2s',
                      }}
                      onMouseEnter={e => {
                        if (description.trim()) {
                          e.currentTarget.style.background = 'rgba(0,255,255,0.05)';
                          e.currentTarget.style.borderColor = 'var(--cyan)';
                        }
                      }}
                      onMouseLeave={e => {
                        if (description.trim()) {
                          e.currentTarget.style.background = 'transparent';
                          e.currentTarget.style.borderColor = 'rgba(0,255,255,0.3)';
                        }
                      }}
                    >
                      DIAGNOSE ONLY
                    </button>
                    
                    <button
                      onClick={handleAnalyze}
                      disabled={!description.trim()}
                      style={{
                        background: description.trim() ? 'linear-gradient(135deg, rgba(0,255,255,0.15), rgba(0,200,255,0.1))' : 'rgba(255,255,255,0.02)',
                        border: `1px solid ${description.trim() ? 'rgba(0,255,255,0.4)' : 'rgba(255,255,255,0.05)'}`,
                        borderRadius: '4px',
                        fontSize: '10px',
                        fontWeight: 800,
                        letterSpacing: '1.5px',
                        padding: '8px 20px',
                        color: description.trim() ? '#fff' : 'rgba(255,255,255,0.15)',
                        cursor: description.trim() ? 'pointer' : 'default',
                        transition: 'all 0.2s',
                        boxShadow: description.trim() ? '0 0 10px rgba(0,255,255,0.05)' : 'none',
                      }}
                      onMouseEnter={e => {
                        if (description.trim()) {
                          e.currentTarget.style.background = 'linear-gradient(135deg, rgba(0,255,255,0.25), rgba(0,200,255,0.15))';
                        }
                      }}
                      onMouseLeave={e => {
                        if (description.trim()) {
                          e.currentTarget.style.background = 'linear-gradient(135deg, rgba(0,255,255,0.15), rgba(0,200,255,0.1))';
                        }
                      }}
                    >
                      ANALYZE & FIX
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* ANALYZING STATE */}
            {state === 'analyzing' && (
              <div style={{
                background: 'rgba(6,10,24,0.7)',
                border: '1px solid rgba(0,255,255,0.08)',
                borderRadius: '14px',
                padding: '48px 24px',
                backdropFilter: 'blur(16px)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '24px',
                animation: 'fadeIn 0.3s ease-out'
              }}>
                <div style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '50%',
                  border: '2px solid rgba(0,255,255,0.15)',
                  borderTopColor: '#ff6d00',
                  animation: 'spin 1s linear infinite',
                }} />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#ff6d00', letterSpacing: '2.5px', fontWeight: 'bold', marginBottom: '8px' }}>
                    MEDIC ANALYZING FAILURE
                  </div>
                  <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)', letterSpacing: '1px' }}>
                    Running AST parsing, traceback diagnosis, and checking failure memory...
                  </div>
                </div>
              </div>
            )}

            {/* PLAN READY STATE */}
            {state === 'plan_ready' && plan && (
              <div style={{
                background: 'rgba(6,10,24,0.7)',
                border: '1px solid rgba(0,255,255,0.08)',
                borderRadius: '14px',
                padding: '24px',
                backdropFilter: 'blur(16px)',
                animation: 'fadeIn 0.3s ease-out',
                display: 'flex',
                flexDirection: 'column',
                gap: '20px',
              }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'rgba(0,255,255,0.4)', letterSpacing: '2px', fontWeight: 700 }}>
                      PROPOSED REPAIR PLAN — {plan.repair_id}
                    </span>
                    <span style={{
                      fontSize: '9px',
                      padding: '2px 8px',
                      borderRadius: '10px',
                      fontWeight: 800,
                      letterSpacing: '1.5px',
                      background: plan.risk_level === 'high' ? 'rgba(255,68,68,0.1)' : plan.risk_level === 'medium' ? 'rgba(255,171,0,0.1)' : 'rgba(0,230,118,0.1)',
                      border: `1px solid ${plan.risk_level === 'high' ? '#ff4444' : plan.risk_level === 'medium' ? '#ffab00' : '#00e676'}`,
                      color: plan.risk_level === 'high' ? '#ff4444' : plan.risk_level === 'medium' ? '#ffab00' : '#00e676',
                    }}>
                      RISK LEVEL: {plan.risk_level.toUpperCase()}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.75)', lineHeight: '1.6', margin: 0 }}>
                    {plan.explanation}
                  </p>
                </div>

                {/* Issues Identified */}
                {plan.issues.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: '9px', color: 'rgba(0,255,255,0.4)', letterSpacing: '1.5px', margin: '0 0 8px 0', textTransform: 'uppercase' }}>
                      Issues Identified
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {plan.issues.map((iss, i) => (
                        <div key={i} style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(0,255,255,0.05)', borderRadius: '6px', padding: '10px 12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                            <span style={{ fontSize: '10px', color: '#ffab00', fontWeight: 'bold' }}>{iss.issue_type}</span>
                            <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.3)' }}>
                              {iss.file_path} {iss.line_number ? `(Line ${iss.line_number})` : ''}
                            </span>
                          </div>
                          <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)' }}>{iss.error_msg}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Proposed Corrections */}
                {plan.proposed_fixes.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: '9px', color: 'rgba(0,255,255,0.4)', letterSpacing: '1.5px', margin: '0 0 8px 0', textTransform: 'uppercase' }}>
                      Proposed Corrections
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {plan.proposed_fixes.map((fix, i) => (
                        <div key={i} style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(0,255,255,0.05)', borderRadius: '6px', padding: '10px 12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                            <span style={{ fontSize: '10px', color: '#00e676', fontWeight: 'bold' }}>Update File</span>
                            <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.3)' }}>{fix.file_path}</span>
                          </div>
                          <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.65)' }}>{fix.description}</div>
                          {fix.command && (
                            <div style={{ marginTop: '8px', background: '#111827', padding: '6px 10px', borderRadius: '4px', border: '1px solid rgba(0,255,255,0.05)' }}>
                              <code style={{ fontSize: '10px', color: 'var(--cyan)' }}>Suggested: {fix.command}</code>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', borderTop: '1px solid rgba(0,255,255,0.05)', paddingTop: '16px' }}>
                  <button
                    onClick={reset}
                    style={{
                      background: 'transparent',
                      border: '1px solid rgba(255,68,68,0.3)',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 800,
                      letterSpacing: '1.5px',
                      padding: '8px 20px',
                      color: '#ff4444',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,68,68,0.05)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                  >
                    CANCEL
                  </button>

                  <button
                    onClick={() => handleExecute(true)}
                    style={{
                      background: 'transparent',
                      border: '1px solid rgba(0,255,255,0.3)',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 800,
                      letterSpacing: '1.5px',
                      padding: '8px 20px',
                      color: 'var(--cyan)',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = 'rgba(0,255,255,0.05)';
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    DRY RUN PATCH
                  </button>

                  <button
                    onClick={() => handleExecute(false)}
                    style={{
                      background: 'linear-gradient(135deg, rgba(0,230,118,0.2), rgba(0,180,80,0.15))',
                      border: '1px solid rgba(0,230,118,0.4)',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 800,
                      letterSpacing: '1.5px',
                      padding: '8px 20px',
                      color: '#fff',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      boxShadow: '0 0 10px rgba(0,230,118,0.05)',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = 'linear-gradient(135deg, rgba(0,230,118,0.3), rgba(0,180,80,0.2))';
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'linear-gradient(135deg, rgba(0,230,118,0.2), rgba(0,180,80,0.15))';
                    }}
                  >
                    APPROVE & APPLY PATCH
                  </button>
                </div>
              </div>
            )}

            {/* REPAIRING STATE */}
            {state === 'repairing' && (
              <div style={{
                background: 'rgba(6,10,24,0.7)',
                border: '1px solid rgba(0,255,255,0.08)',
                borderRadius: '14px',
                padding: '32px 24px',
                backdropFilter: 'blur(16px)',
                animation: 'fadeIn 0.3s ease-out',
                display: 'flex',
                flexDirection: 'column',
                gap: '20px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', color: '#ff6d00', letterSpacing: '2.5px', fontWeight: 'bold' }}>
                    EXECUTING HEALING ENGINE
                  </span>
                  <span style={{ fontSize: '11px', color: 'rgba(0,255,255,0.4)' }}>
                    {repairProgress}%
                  </span>
                </div>

                <div style={{ height: '3px', background: 'rgba(0,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${repairProgress}%`,
                    background: 'linear-gradient(90deg, #ff6d00, #00ffff)',
                    transition: 'width 0.4s ease',
                  }} />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: '#ff6d00',
                    animation: 'thinking-pulse 1.2s ease-in-out infinite'
                  }} />
                  <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)', letterSpacing: '0.5px' }}>
                    {repairStageMsg}
                  </span>
                </div>
              </div>
            )}

            {/* COMPLETE STATE */}
            {state === 'complete' && result && (
              <div style={{
                background: 'rgba(6,10,24,0.7)',
                border: '1px solid rgba(0,255,255,0.08)',
                borderRadius: '14px',
                padding: '24px',
                backdropFilter: 'blur(16px)',
                animation: 'fadeIn 0.3s ease-out',
                display: 'flex',
                flexDirection: 'column',
                gap: '20px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span style={{ fontSize: '20px' }}>{result.success ? '✅' : '❌'}</span>
                  <div>
                    <div style={{ fontSize: '13px', color: result.success ? '#00e676' : '#ff4444', fontWeight: 800, letterSpacing: '1.5px' }}>
                      REPAIR JOB COMPLETED {result.success ? 'SUCCESSFULLY' : 'WITH FAILURES'}
                    </div>
                    <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.3)', marginTop: '2px', letterSpacing: '1.5px' }}>
                      REPAIR ID: {result.repair_id}
                    </div>
                  </div>
                  <div style={{ flex: 1 }} />
                  <span style={{
                    fontSize: '9px',
                    padding: '2px 8px',
                    borderRadius: '10px',
                    fontWeight: 800,
                    letterSpacing: '1.5px',
                    background: result.verification_status === 'passed' ? 'rgba(0,230,118,0.1)' : result.verification_status === 'failed' ? 'rgba(255,68,68,0.1)' : 'rgba(255,255,255,0.05)',
                    border: `1px solid ${result.verification_status === 'passed' ? '#00e676' : result.verification_status === 'failed' ? '#ff4444' : 'rgba(255,255,255,0.15)'}`,
                    color: result.verification_status === 'passed' ? '#00e676' : result.verification_status === 'failed' ? '#ff4444' : 'rgba(255,255,255,0.5)',
                  }}>
                    VERIFICATION: {result.verification_status.toUpperCase()}
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px 12px', borderRadius: '6px' }}>
                    <div style={{ fontSize: '8px', color: 'rgba(0,255,255,0.3)', letterSpacing: '1px', marginBottom: '2px' }}>ISSUES FOUND</div>
                    <div style={{ fontSize: '13px', color: '#fff' }}>{result.issues_found}</div>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px 12px', borderRadius: '6px' }}>
                    <div style={{ fontSize: '8px', color: 'rgba(0,255,255,0.3)', letterSpacing: '1px', marginBottom: '2px' }}>ISSUES RESOLVED</div>
                    <div style={{ fontSize: '13px', color: '#00e676' }}>{result.issues_fixed}</div>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px 12px', borderRadius: '6px' }}>
                    <div style={{ fontSize: '8px', color: 'rgba(0,255,255,0.3)', letterSpacing: '1px', marginBottom: '2px' }}>FILES MODIFIED</div>
                    <div style={{ fontSize: '13px', color: '#fff' }}>{result.files_changed.length}</div>
                  </div>
                </div>

                {/* Files Modified */}
                {result.files_changed.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: '9px', color: 'rgba(0,255,255,0.4)', letterSpacing: '1.5px', margin: '0 0 6px 0', textTransform: 'uppercase' }}>
                      Modified Files
                    </h3>
                    <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '11px', color: 'rgba(255,255,255,0.6)' }}>
                      {result.files_changed.map((f, idx) => (
                        <li key={idx} style={{ marginBottom: '4px' }}><code style={{ color: 'var(--cyan)' }}>{f}</code></li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Suggested Commands */}
                {result.commands_run.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: '9px', color: 'rgba(0,255,255,0.4)', letterSpacing: '1.5px', margin: '0 0 6px 0', textTransform: 'uppercase' }}>
                      Suggested Actions / Environment
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {result.commands_run.map((c, idx) => (
                        <div key={idx} style={{ background: '#111827', padding: '6px 12px', borderRadius: '4px', border: '1px solid rgba(0,255,255,0.05)' }}>
                          <code style={{ fontSize: '10px', color: '#ff6d00' }}>{c}</code>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Remaining Risks */}
                {result.remaining_risks.length > 0 && (
                  <div style={{ background: 'rgba(255,68,68,0.03)', border: '1px solid rgba(255,68,68,0.15)', borderRadius: '6px', padding: '12px' }}>
                    <div style={{ fontSize: '9px', color: '#ff4444', fontWeight: 'bold', letterSpacing: '1.5px', marginBottom: '6px' }}>
                      ⚠️ REMAINING RISK WARNINGS
                    </div>
                    <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '11px', color: 'rgba(255,100,100,0.8)' }}>
                      {result.remaining_risks.map((risk, idx) => (
                        <li key={idx} style={{ marginBottom: '4px' }}>{risk}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Main report output */}
                {result.report && (
                  <div style={{ borderTop: '1px solid rgba(0,255,255,0.05)', paddingTop: '16px' }}>
                    <h3 style={{ fontSize: '9px', color: 'rgba(0,255,255,0.4)', letterSpacing: '1.5px', margin: '0 0 8px 0', textTransform: 'uppercase' }}>
                      Repair Report Narrative
                    </h3>
                    <pre style={{
                      background: 'rgba(0,0,0,0.3)',
                      border: '1px solid rgba(0,255,255,0.04)',
                      borderRadius: '6px',
                      padding: '12px',
                      fontSize: '11px',
                      lineHeight: '1.6',
                      color: 'rgba(200,240,255,0.85)',
                      maxHeight: '200px',
                      overflowY: 'auto',
                      whiteSpace: 'pre-wrap',
                      margin: 0,
                    }}>
                      {result.report}
                    </pre>
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
                  <button
                    onClick={reset}
                    style={{
                      background: 'linear-gradient(135deg, rgba(0,255,255,0.15), rgba(0,200,255,0.1))',
                      border: '1px solid rgba(0,255,255,0.35)',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 800,
                      letterSpacing: '1.5px',
                      padding: '8px 24px',
                      color: '#fff',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'linear-gradient(135deg, rgba(0,255,255,0.25), rgba(0,200,255,0.15))'}
                    onMouseLeave={e => e.currentTarget.style.background = 'linear-gradient(135deg, rgba(0,255,255,0.15), rgba(0,200,255,0.1))'}
                  >
                    NEW REPAIR JOB
                  </button>
                </div>
              </div>
            )}

            {/* ERROR STATE */}
            {state === 'error' && (
              <div style={{
                background: 'rgba(255,68,68,0.03)',
                border: '1px solid rgba(255,68,68,0.25)',
                borderRadius: '14px',
                padding: '24px',
                backdropFilter: 'blur(16px)',
                animation: 'fadeIn 0.3s ease-out',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
              }}>
                <div>
                  <div style={{ fontSize: '13px', color: '#ff4444', fontWeight: 800, letterSpacing: '1.5px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>❌</span> REPAIR DIAGNOSIS EXCEPTION
                  </div>
                  <pre style={{
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,68,68,0.1)',
                    borderRadius: '6px',
                    padding: '12px',
                    fontSize: '10px',
                    lineHeight: '1.5',
                    color: 'rgba(255,100,100,0.85)',
                    maxHeight: '200px',
                    overflowY: 'auto',
                    margin: '12px 0 0 0',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {errorMsg}
                  </pre>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                  <button
                    onClick={reset}
                    style={{
                      background: 'rgba(255,68,68,0.1)',
                      border: '1px solid rgba(255,68,68,0.35)',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 800,
                      letterSpacing: '1.5px',
                      padding: '8px 20px',
                      color: '#ff4444',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,68,68,0.15)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,68,68,0.1)'}
                  >
                    RESET STATE
                  </button>
                </div>
              </div>
            )}

          </main>

          {/* Right Sidebar (280px) */}
          <aside style={{
            width: '280px',
            borderLeft: '1px solid rgba(0,255,255,0.08)',
            background: 'rgba(6,10,24,0.4)',
            backdropFilter: 'blur(16px)',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            padding: '20px',
            gap: '24px',
          }}>
            
            {/* Pending Watcher Repairs */}
            <div>
              <h3 style={{
                fontSize: '9px',
                color: 'rgba(0,255,255,0.4)',
                letterSpacing: '2px',
                fontWeight: 700,
                margin: '0 0 12px 0',
                textTransform: 'uppercase'
              }}>
                Pending Watcher Repairs
              </h3>
              
              {pendingWatcher.length === 0 ? (
                <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.25)', fontStyle: 'italic' }}>
                  No pending watcher repairs detected.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {pendingWatcher.map((item) => (
                    <div
                      key={item.repair_id}
                      onClick={() => handlePendingRepairClick(item)}
                      style={{
                        background: 'rgba(255,109,0,0.03)',
                        border: '1px solid rgba(255,109,0,0.15)',
                        borderRadius: '8px',
                        padding: '10px',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.background = 'rgba(255,109,0,0.08)';
                        e.currentTarget.style.borderColor = 'rgba(255,109,0,0.3)';
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.background = 'rgba(255,109,0,0.03)';
                        e.currentTarget.style.borderColor = 'rgba(255,109,0,0.15)';
                      }}
                    >
                      <div style={{ fontSize: '9px', color: '#ff6d00', fontWeight: 'bold', marginBottom: '4px' }}>
                        {item.rel_path}
                      </div>
                      <div style={{
                        fontSize: '9px',
                        color: 'rgba(255,255,255,0.5)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}>
                        {item.error}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Repair Memory Panel */}
            <div>
              <h3 style={{
                fontSize: '9px',
                color: 'rgba(0,255,255,0.4)',
                letterSpacing: '2px',
                fontWeight: 700,
                margin: '0 0 12px 0',
                textTransform: 'uppercase'
              }}>
                Repair Memory
              </h3>
              
              {memory ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {/* Stats */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
                    <div style={{ background: 'rgba(0,0,0,0.2)', padding: '6px 8px', borderRadius: '4px' }}>
                      <div style={{ fontSize: '7px', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.5px' }}>REPAIRS</div>
                      <div style={{ fontSize: '11px', color: '#fff', fontWeight: 'bold' }}>{memory.stats.total_repairs}</div>
                    </div>
                    <div style={{ background: 'rgba(0,0,0,0.2)', padding: '6px 8px', borderRadius: '4px' }}>
                      <div style={{ fontSize: '7px', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.5px' }}>SUCCESS %</div>
                      <div style={{ fontSize: '11px', color: '#00e676', fontWeight: 'bold' }}>
                        {memory.stats.total_repairs > 0 
                          ? Math.round((memory.stats.successful_repairs / memory.stats.total_repairs) * 100)
                          : 0}%
                      </div>
                    </div>
                  </div>

                  {/* Patterns */}
                  <div>
                    <div style={{ fontSize: '8px', color: 'rgba(0,255,255,0.35)', letterSpacing: '1px', marginBottom: '6px', fontWeight: 'bold' }}>
                      KNOWN ERRORS ({memory.failure_patterns.length})
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {memory.failure_patterns.slice(0, 3).map((p, idx) => (
                        <div key={idx} style={{
                          background: 'rgba(0,0,0,0.15)',
                          borderRadius: '4px',
                          padding: '6px 8px',
                          border: '1px solid rgba(0,255,255,0.03)',
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginBottom: '2px' }}>
                            <span>{p.agent}</span>
                            <span>{p.occurrences}x</span>
                          </div>
                          <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.6)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {p.error_msg}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Personal Notes */}
                  <div>
                    <div style={{ fontSize: '8px', color: 'rgba(0,255,255,0.35)', letterSpacing: '1px', marginBottom: '6px', fontWeight: 'bold' }}>
                      CONTEXT NOTES
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {memory.personal_notes.map((n, idx) => (
                        <div key={idx} style={{
                          background: 'rgba(0,255,255,0.02)',
                          padding: '6px',
                          borderRadius: '4px',
                          borderLeft: '2px solid #ff6d00',
                          fontSize: '9px',
                          color: 'rgba(255,255,255,0.65)',
                          lineHeight: '1.4',
                        }}>
                          {n}
                        </div>
                      ))}
                    </div>
                    <form onSubmit={handleAddNote} style={{ display: 'flex', gap: '4px', marginTop: '6px' }}>
                      <input
                        type="text"
                        value={newNote}
                        onChange={e => setNewNote(e.target.value)}
                        placeholder="Add contextual memory..."
                        style={{
                          flex: 1,
                          background: 'rgba(0,0,0,0.3)',
                          border: '1px solid rgba(0,255,255,0.1)',
                          borderRadius: '4px',
                          color: '#fff',
                          fontSize: '9px',
                          fontFamily: 'inherit',
                          padding: '4px 6px',
                          outline: 'none',
                        }}
                      />
                      <button
                        type="submit"
                        style={{
                          background: 'rgba(0,255,255,0.1)',
                          border: '1px solid rgba(0,255,255,0.25)',
                          borderRadius: '4px',
                          color: '#fff',
                          fontSize: '9px',
                          padding: '0 8px',
                          cursor: 'pointer',
                        }}
                      >
                        +
                      </button>
                    </form>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.25)', fontStyle: 'italic' }}>
                  Loading memory database...
                </div>
              )}
            </div>

            {/* Repair History */}
            <div>
              <h3 style={{
                fontSize: '9px',
                color: 'rgba(0,255,255,0.4)',
                letterSpacing: '2px',
                fontWeight: 700,
                margin: '0 0 12px 0',
                textTransform: 'uppercase'
              }}>
                Repair History
              </h3>
              
              {history.length === 0 ? (
                <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.25)', fontStyle: 'italic' }}>
                  No historical repairs recorded.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {history.map((item, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'rgba(0,0,0,0.25)',
                        border: '1px solid rgba(0,255,255,0.05)',
                        borderRadius: '6px',
                        padding: '8px 10px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span style={{ fontSize: '8px', color: 'rgba(255,255,255,0.3)' }}>{item.repair_id}</span>
                        <span style={{
                          fontSize: '7px',
                          fontWeight: 'bold',
                          color: item.success ? '#00e676' : '#ff4444',
                        }}>
                          {item.success ? 'SUCCESS' : 'FAILED'}
                        </span>
                      </div>
                      
                      <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.7)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {item.type === 'task_failure_diagnosis' 
                          ? `Diagnosed: ${item.agent}` 
                          : `Fixed ${item.issues_fixed}/${item.issues_found} issues`
                        }
                      </div>
                      
                      {item.root_cause && (
                        <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.4)', marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          Cause: {item.root_cause}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

          </aside>

        </div>

      </div>

      {/* Embedded CSS for spin and pulse effects */}
      <style jsx global>{`
        @keyframes spin {
          100% { transform: rotate(360deg); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes thinking-pulse {
          0% { box-shadow: 0 0 0 0 rgba(255, 109, 0, 0.4); opacity: 0.6; }
          70% { box-shadow: 0 0 0 8px rgba(255, 109, 0, 0); opacity: 1; }
          100% { box-shadow: 0 0 0 0 rgba(255, 109, 0, 0); opacity: 0.6; }
        }
      `}</style>
    </div>
  );
}

export default function RepairCenterPage() {
  return (
    <Suspense fallback={
      <div style={{ position: 'fixed', inset: 0, background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', color: 'rgba(0,255,255,0.6)' }}>
        Loading Repair Center...
      </div>
    }>
      <RepairCenterContent />
    </Suspense>
  );
}
