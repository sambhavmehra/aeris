'use client';
import { create } from 'zustand';

/* ── Types ─────────────────────────────────────────── */

export type AgentStatus = 'offline' | 'initializing' | 'online' | 'error' | 'working';
export type AgentCategory = 'core' | 'control' | 'swarm' | 'special';
export type AssemblyPhase = 'idle' | 'assembling' | 'assembled' | 'disassembling';

export interface Agent {
  id: string;
  codename: string;
  role: string;
  category: AgentCategory;
  status: AgentStatus;
  introduction: string;
  voiceId: string;
  icon: string;
  color: string;
  description: string;
}

export interface LoadingStep {
  label: string;
  progress: number; // 0-100
  complete: boolean;
}

export interface AgentStore {
  // State
  phase: AssemblyPhase;
  agents: Agent[];
  currentAgentIndex: number;
  loadingSteps: LoadingStep[];
  syncSteps: LoadingStep[];
  syncProgress: number;
  activeAgentId: string | null;

  // Computed-like
  onlineAgents: () => Agent[];
  onlineCount: () => number;
  totalAgents: number;
  getAgentById: (id: string) => Agent | undefined;
  getAgentsByCategory: (cat: AgentCategory) => Agent[];

  // Actions
  triggerAssembly: () => void;
  triggerDisassembly: () => void;
  setPhase: (phase: AssemblyPhase) => void;
  setAgentStatus: (id: string, status: AgentStatus) => void;
  setCurrentAgentIndex: (i: number) => void;
  setLoadingStepProgress: (index: number, progress: number) => void;
  completeLoadingStep: (index: number) => void;
  setSyncStepProgress: (index: number, progress: number) => void;
  completeSyncStep: (index: number) => void;
  setSyncProgress: (p: number) => void;
  setActiveAgent: (id: string | null) => void;
  setAllOnline: () => void;
  setAllOffline: () => void;
  restoreAssembled: () => void;
}

/* ── Agent Definitions ─────────────────────────────── */

const CORE_AGENTS: Agent[] = [
  { id: 'aurora', codename: 'AURORA', role: 'ChatAgent', category: 'core', status: 'offline', introduction: 'Aurora online hai, Sir. Aapki saari chat aur system assistance ke liye ready hoon.', voiceId: 'en-IN-NeerjaNeural', icon: '💬', color: '#00e5ff', description: 'Conversational AI assistant' },
  { id: 'raven', codename: 'RAVEN', role: 'SecurityAgent', category: 'core', status: 'offline', introduction: 'Raven active hai, Sir. Security protocols check kar liye hain, perimeter secure hai.', voiceId: 'en-IN-PrabhatNeural', icon: '🛡️', color: '#ff1744', description: 'Cyber defense and threat analysis' },
  { id: 'titan', codename: 'TITAN', role: 'SystemAgent', category: 'core', status: 'offline', introduction: 'Titan online hai, Sir. Compute resources aur power load balance optimize ho gaya hai.', voiceId: 'hi-IN-MadhurNeural', icon: '⚙️', color: '#76ff03', description: 'System control and management' },
  { id: 'oracle', codename: 'ORACLE', role: 'ResearchAgent', category: 'core', status: 'offline', introduction: 'Oracle active hai. Data patterns aur security files index kar li hain.', voiceId: 'hi-IN-SwaraNeural', icon: '🔍', color: '#e040fb', description: 'Research and intelligence gathering' },
  { id: 'argus', codename: 'ARGUS', role: 'SearchAgent', category: 'core', status: 'offline', introduction: 'Argus active hai, Sir. Live web data aur system activity monitoring online hai.', voiceId: 'en-IN-PrabhatNeural', icon: '📡', color: '#ffab00', description: 'Live data search and retrieval' },
  { id: 'vulcan', codename: 'VULCAN', role: 'CodingAgent', category: 'core', status: 'offline', introduction: 'Vulcan active hai. Development environments aur project structures fully ready hain.', voiceId: 'hi-IN-MadhurNeural', icon: '💻', color: '#00bfa5', description: 'Software development and code generation' },
  { id: 'phantom', codename: 'PHANTOM', role: 'ImageAgent', category: 'core', status: 'offline', introduction: 'Phantom online hai, Sir. Neural visual generation aur canvas elements active hain.', voiceId: 'en-IN-NeerjaNeural', icon: '🎨', color: '#f50057', description: 'Image generation and visual design' },
  { id: 'spectre', codename: 'SPECTRE', role: 'AnalyzerAgent', category: 'core', status: 'offline', introduction: 'Spectre online hai. Log traces aur forensic files load kar liye hain.', voiceId: 'hi-IN-SwaraNeural', icon: '🔬', color: '#651fff', description: 'Data analysis and forensic examination' },
  { id: 'shadow', codename: 'SHADOW', role: 'OSINTAgent', category: 'core', status: 'offline', introduction: 'Shadow ready hai, Sir. Log cleaning aur tracking disable kar di gayi hai. Silent mode active hai.', voiceId: 'en-IN-PrabhatNeural', icon: '🕵️', color: '#546e7a', description: 'Open-source intelligence operations' },
  { id: 'mercury', codename: 'MERCURY', role: 'EmailAgent', category: 'core', status: 'offline', introduction: 'Mercury online hai, Sir. Communication queues aur emails manage karne ke liye taiyar.', voiceId: 'en-IN-NeerjaNeural', icon: '📧', color: '#00b0ff', description: 'Email and communication management' },
  { id: 'chronos', codename: 'CHRONOS', role: 'SchedulerAgent', category: 'core', status: 'offline', introduction: 'Chronos active hai. Schedulers aur system timers sync ho chuke hain.', voiceId: 'hi-IN-MadhurNeural', icon: '⏱️', color: '#ffd600', description: 'Scheduling and time management' },
  { id: 'drana', codename: 'DRANA', role: 'DranaAgent', category: 'core', status: 'offline', introduction: 'Drana active hai, Sir. Firewall subversion aur vulnerability exploits load ho chuke hain.', voiceId: 'hi-IN-SwaraNeural', icon: '☠️', color: '#d50000', description: 'Advanced penetration and security testing' },
];

const CONTROL_AGENTS: Agent[] = [
  { id: 'judge', codename: 'JUDGE', role: 'AuditAgent', category: 'control', status: 'offline', introduction: 'Judge active hai. System audits aur compliance logs trace ho rahe hain.', voiceId: 'en-IN-PrabhatNeural', icon: '⚖️', color: '#ff6d00', description: 'Audit trail and compliance monitoring' },
  { id: 'watcher', codename: 'WATCHER', role: 'ObserverAgent', category: 'control', status: 'offline', introduction: 'Watcher active hai. Process behaviours aur security anomalies check kar raha hoon.', voiceId: 'en-IN-NeerjaNeural', icon: '👁️', color: '#aa00ff', description: 'System observation and monitoring' },
  { id: 'genesis', codename: 'GENESIS', role: 'ProjectBuilder', category: 'control', status: 'offline', introduction: 'Genesis online hai. New project frameworks aur workspaces initialize ho gaye hain.', voiceId: 'hi-IN-MadhurNeural', icon: '🏗️', color: '#64dd17', description: 'Automated project creation and scaffolding' },
  { id: 'vigil', codename: 'VIGIL', role: 'ProactiveAgent', category: 'control', status: 'offline', introduction: 'Vigil active hai. Alert thresholds aur anomaly metrics check kar liye hain.', voiceId: 'hi-IN-SwaraNeural', icon: '🔔', color: '#ff9100', description: 'Proactive alerting and autonomous monitoring' },
];

const SWARM_AGENTS: Agent[] = [
  { id: 'nexus', codename: 'NEXUS', role: 'AnalysisAgent', category: 'swarm', status: 'offline', introduction: 'Nexus swarm node active hai. Memory sync aur cluster load balance configuration completed.', voiceId: 'en-IN-NeerjaNeural', icon: '🧬', color: '#18ffff', description: 'Distributed analysis processing' },
  { id: 'archon', codename: 'ARCHON', role: 'ArchitectureAgent', category: 'swarm', status: 'offline', introduction: 'Archon online hai. System microservices aur API bounds load ho gaye hain.', voiceId: 'en-IN-PrabhatNeural', icon: '📐', color: '#b388ff', description: 'System architecture design' },
  { id: 'forge', codename: 'FORGE', role: 'SwarmCodingAgent', category: 'swarm', status: 'offline', introduction: 'Forge active hai. Distributed workspace files build aur compile hone ke liye ready hain.', voiceId: 'hi-IN-MadhurNeural', icon: '🔨', color: '#ff6e40', description: 'Distributed code generation' },
  { id: 'insight', codename: 'INSIGHT', role: 'SwarmResearchAgent', category: 'swarm', status: 'offline', introduction: 'Insight active hai. Internal documentation aur research archives sync ho gaye hain.', voiceId: 'hi-IN-SwaraNeural', icon: '💡', color: '#eeff41', description: 'Deep research and knowledge synthesis' },
  { id: 'scribe', codename: 'SCRIBE', role: 'DocumentationAgent', category: 'swarm', status: 'offline', introduction: 'Scribe online hai, Sir. System commands aur output logging templates write ho chuke hain.', voiceId: 'en-IN-NeerjaNeural', icon: '📝', color: '#84ffff', description: 'Automated documentation generation' },
  { id: 'sentinel', codename: 'SENTINEL', role: 'VulnerabilityAgent', category: 'swarm', status: 'offline', introduction: 'Sentinel ready hai. Vulnerability lists aur exposed ports analysis load kar liya hai.', voiceId: 'en-IN-PrabhatNeural', icon: '🔐', color: '#ff5252', description: 'Vulnerability detection and assessment' },
  { id: 'pulse', codename: 'PULSE', role: 'RuntimeAgent', category: 'swarm', status: 'offline', introduction: 'Pulse online. Multiprocessing threads aur event loops properly check ho gaye hain.', voiceId: 'hi-IN-MadhurNeural', icon: '💓', color: '#69f0ae', description: 'Runtime execution and testing' },
  { id: 'atlas', codename: 'ATLAS', role: 'ToolManagerAgent', category: 'swarm', status: 'offline', introduction: 'Atlas active hai. Integration APIs aur third-party wrapper tools ready hain.', voiceId: 'hi-IN-SwaraNeural', icon: '🗺️', color: '#40c4ff', description: 'Dynamic tool management and orchestration' },
  { id: 'command', codename: 'COMMAND', role: 'DelegatorAgent', category: 'swarm', status: 'offline', introduction: 'Command node online hai. Work tasks delegate aur assign karne ke liye taiyar.', voiceId: 'en-IN-NeerjaNeural', icon: '🎯', color: '#ffe57f', description: 'Intelligent task delegation and routing' },
];

const SPECIAL_AGENTS: Agent[] = [
  { id: 'hunter', codename: 'HUNTER', role: 'DorkingAgent', category: 'special', status: 'offline', introduction: 'Hunter active hai. Google OSINT dorks aur search payloads execute ho rahe hain.', voiceId: 'en-IN-PrabhatNeural', icon: '🏹', color: '#ff3d00', description: 'Google dorking and search exploitation' },
  { id: 'reaper', codename: 'REAPER', role: 'PentestAgent', category: 'special', status: 'offline', introduction: 'Reaper ready hai. Metasploit interfaces aur target probes bind kar liye hain.', voiceId: 'hi-IN-MadhurNeural', icon: '💀', color: '#b71c1c', description: 'Automated penetration testing' },
  { id: 'ghost', codename: 'GHOST', role: 'PhantomAgent', category: 'special', status: 'offline', introduction: 'Ghost online hai, Sir. Track logs clean ho rahe hain aur routing camouflage ready hai.', voiceId: 'en-IN-PrabhatNeural', icon: '👻', color: '#e0e0e0', description: 'Phantom trace and stealth analytics' },
  { id: 'webweaver', codename: 'WEBWEAVER', role: 'LeakGraphAgent', category: 'special', status: 'offline', introduction: 'Webweaver ready hai. Leak analysis mappings aur network traces sync ho rahe hain.', voiceId: 'hi-IN-SwaraNeural', icon: '🕸️', color: '#7c4dff', description: 'Data leak detection and graph analysis' },
  { id: 'strategos', codename: 'STRATEGOS', role: 'PlannerAgent', category: 'special', status: 'offline', introduction: 'Strategos active hai, Sir. Target scan objectives aur alternate routes map kar liye hain.', voiceId: 'hi-IN-MadhurNeural', icon: '♟️', color: '#ffc400', description: 'Strategic planning and execution' },
  { id: 'validator', codename: 'VALIDATOR', role: 'VerifierAgent', category: 'special', status: 'offline', introduction: 'Validator online. Checksums aur compile metrics complete ho chuke hain.', voiceId: 'en-IN-NeerjaNeural', icon: '✅', color: '#00e676', description: 'Code verification and validation' },
  { id: 'blueprint', codename: 'BLUEPRINT', role: 'DiagramAgent', category: 'special', status: 'offline', introduction: 'Blueprint active hai, Sir. Vector architecture diagrams render ho rahe hain.', voiceId: 'hi-IN-SwaraNeural', icon: '📊', color: '#448aff', description: 'System diagram and architecture visualization' },
];

const ALL_AGENTS: Agent[] = [...CORE_AGENTS, ...CONTROL_AGENTS, ...SWARM_AGENTS, ...SPECIAL_AGENTS];

const INITIAL_LOADING_STEPS: LoadingStep[] = [
  { label: 'Neural Systems', progress: 0, complete: false },
  { label: 'Agent Registry', progress: 0, complete: false },
  { label: 'Voice Profiles', progress: 0, complete: false },
  { label: 'Memory Layer', progress: 0, complete: false },
  { label: 'Tool Framework', progress: 0, complete: false },
  { label: 'Swarm Network', progress: 0, complete: false },
  { label: 'Security Layer', progress: 0, complete: false },
];

const INITIAL_SYNC_STEPS: LoadingStep[] = [
  { label: 'Voice Synchronization', progress: 0, complete: false },
  { label: 'Memory Synchronization', progress: 0, complete: false },
  { label: 'Capability Mapping', progress: 0, complete: false },
  { label: 'Tool Registration', progress: 0, complete: false },
  { label: 'Swarm Coordination', progress: 0, complete: false },
  { label: 'Security Validation', progress: 0, complete: false },
];

/* ── Store ──────────────────────────────────────────── */

const SESSION_KEY = 'aeris-assembly-state';

export const useAgentStore = create<AgentStore>((set, get) => ({
  phase: 'idle',
  agents: ALL_AGENTS.map(a => ({ ...a })),
  currentAgentIndex: -1,
  loadingSteps: INITIAL_LOADING_STEPS.map(s => ({ ...s })),
  syncSteps: INITIAL_SYNC_STEPS.map(s => ({ ...s })),
  syncProgress: 0,
  activeAgentId: null,
  totalAgents: ALL_AGENTS.length,

  // Computed
  onlineAgents: () => get().agents.filter(a => a.status === 'online'),
  onlineCount: () => get().agents.filter(a => a.status === 'online').length,
  getAgentById: (id: string) => get().agents.find(a => a.id === id),
  getAgentsByCategory: (cat: AgentCategory) => get().agents.filter(a => a.category === cat),

  // Actions
  triggerAssembly: () => {
    set({
      phase: 'assembling',
      agents: ALL_AGENTS.map(a => ({ ...a, status: 'offline' as AgentStatus })),
      currentAgentIndex: -1,
      loadingSteps: INITIAL_LOADING_STEPS.map(s => ({ ...s })),
      syncSteps: INITIAL_SYNC_STEPS.map(s => ({ ...s })),
      syncProgress: 0,
      activeAgentId: null,
    });
  },

  triggerDisassembly: () => {
    set({ phase: 'disassembling' });
    sessionStorage.removeItem(SESSION_KEY);
  },

  setPhase: (phase) => {
    set({ phase });
    if (phase === 'assembled') {
      sessionStorage.setItem(SESSION_KEY, 'assembled');
    } else if (phase === 'idle') {
      sessionStorage.removeItem(SESSION_KEY);
    }
  },

  setAgentStatus: (id, status) => {
    set(state => ({
      agents: state.agents.map(a => a.id === id ? { ...a, status } : a),
    }));
  },

  setCurrentAgentIndex: (i) => set({ currentAgentIndex: i }),

  setLoadingStepProgress: (index, progress) => {
    set(state => ({
      loadingSteps: state.loadingSteps.map((s, i) =>
        i === index ? { ...s, progress: Math.min(100, progress) } : s
      ),
    }));
  },

  completeLoadingStep: (index) => {
    set(state => ({
      loadingSteps: state.loadingSteps.map((s, i) =>
        i === index ? { ...s, progress: 100, complete: true } : s
      ),
    }));
  },

  setSyncStepProgress: (index, progress) => {
    set(state => ({
      syncSteps: state.syncSteps.map((s, i) =>
        i === index ? { ...s, progress: Math.min(100, progress) } : s
      ),
    }));
  },

  completeSyncStep: (index) => {
    set(state => ({
      syncSteps: state.syncSteps.map((s, i) =>
        i === index ? { ...s, progress: 100, complete: true } : s
      ),
    }));
  },

  setSyncProgress: (p) => set({ syncProgress: p }),

  setActiveAgent: (id) => set({ activeAgentId: id }),

  setAllOnline: () => {
    set(state => ({
      agents: state.agents.map(a => ({ ...a, status: 'online' as AgentStatus })),
    }));
  },

  setAllOffline: () => {
    set(state => ({
      agents: state.agents.map(a => ({ ...a, status: 'offline' as AgentStatus })),
      phase: 'idle' as AssemblyPhase,
      currentAgentIndex: -1,
      activeAgentId: null,
    }));
    sessionStorage.removeItem(SESSION_KEY);
  },

  restoreAssembled: () => {
    set({
      phase: 'assembled',
      agents: ALL_AGENTS.map(a => ({ ...a, status: 'online' as AgentStatus })),
      currentAgentIndex: ALL_AGENTS.length - 1,
      syncProgress: 100,
      loadingSteps: INITIAL_LOADING_STEPS.map(s => ({ ...s, progress: 100, complete: true })),
      syncSteps: INITIAL_SYNC_STEPS.map(s => ({ ...s, progress: 100, complete: true })),
    });
  },
}));

/* ── Exports for convenience ───────────────────────── */

export const AGENT_CATEGORIES: { key: AgentCategory; label: string; color: string }[] = [
  { key: 'core', label: 'CORE AGENTS', color: '#00e5ff' },
  { key: 'control', label: 'CONTROL AGENTS', color: '#ff9100' },
  { key: 'swarm', label: 'SWARM AGENTS', color: '#a855f7' },
  { key: 'special', label: 'SPECIAL AGENTS', color: '#ff3366' },
];

export const AGENT_CODENAMES: Record<string, string> = {};
ALL_AGENTS.forEach(a => { AGENT_CODENAMES[a.id] = a.codename; });
