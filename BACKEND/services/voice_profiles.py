# -*- coding: utf-8 -*-
"""
AERIS Voice Profiles Registry
Defines the Edge-TTS voice mapping and speech parameters for all 35 AERIS agents.
Introductions are tuned to natural, agentic Hinglish.
"""

# Default voice profile for the overall AERIS system
DEFAULT_VOICE = "hi-IN-MadhurNeural"

# Full registry of all 35 agents with their voice configurations and speech tuning
VOICE_PROFILES = {
    "aurora": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "+0%",
        "pitch": "+5Hz",
        "codename": "AURORA",
        "role": "Friendly Assistant",
        "intro": "Aurora online hai, Sir. Aapki saari chat aur system assistance ke liye ready hoon."
    },
    "raven": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "-10%",
        "pitch": "-8Hz",
        "codename": "RAVEN",
        "role": "Tactical Operations",
        "intro": "Raven active hai, Sir. Security protocols check kar liye hain, perimeter secure hai."
    },
    "titan": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "-15%",
        "pitch": "-12Hz",
        "codename": "TITAN",
        "role": "Heavy Infrastructure",
        "intro": "Titan online hai, Sir. Compute resources aur power load balance optimize ho gaya hai."
    },
    "oracle": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "-5%",
        "pitch": "+0Hz",
        "codename": "ORACLE",
        "role": "Calm Analyst",
        "intro": "Oracle active hai. Data patterns aur security files index kar li hain."
    },
    "argus": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "+15%",
        "pitch": "+3Hz",
        "codename": "ARGUS",
        "role": "Fast Intelligence",
        "intro": "Argus active hai, Sir. Live web data aur system activity monitoring online hai."
    },
    "vulcan": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+0%",
        "pitch": "-3Hz",
        "codename": "VULCAN",
        "role": "Technical Engineer",
        "intro": "Vulcan active hai. Development environments aur project structures fully ready hain."
    },
    "phantom": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "+5%",
        "pitch": "+8Hz",
        "codename": "PHANTOM",
        "role": "Creative Synthesizer",
        "intro": "Phantom online hai, Sir. Neural visual generation aur canvas elements active hain."
    },
    "spectre": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "-5%",
        "pitch": "-5Hz",
        "codename": "SPECTRE",
        "role": "Forensic Analyst",
        "intro": "Spectre online hai. Log traces aur forensic files load kar liye hain."
    },
    "shadow": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "-8%",
        "pitch": "-6Hz",
        "codename": "SHADOW",
        "role": "Intelligence Operative",
        "intro": "Shadow ready hai, Sir. Log cleaning aur tracking disable kar di gayi hai. Silent mode active hai."
    },
    "mercury": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "+0%",
        "pitch": "+2Hz",
        "codename": "MERCURY",
        "role": "Professional Assistant",
        "intro": "Mercury online hai, Sir. Communication queues aur emails manage karne ke liye taiyar."
    },
    "chronos": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "-10%",
        "pitch": "+0Hz",
        "codename": "CHRONOS",
        "role": "Temporal Scheduler",
        "intro": "Chronos active hai. Schedulers aur system timers sync ho chuke hain."
    },
    "drana": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+10%",
        "pitch": "-4Hz",
        "codename": "DRANA",
        "role": "Elite Hacker",
        "intro": "Drana active hai, Sir. Firewall subversion aur vulnerability exploits load ho chuke hain."
    },
    "judge": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "-5%",
        "pitch": "-7Hz",
        "codename": "JUDGE",
        "role": "Authoritative Evaluator",
        "intro": "Judge active hai. System audits aur compliance logs trace ho rahe hain."
    },
    "watcher": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "-3%",
        "pitch": "+3Hz",
        "codename": "WATCHER",
        "role": "Observant Sentinel",
        "intro": "Watcher active hai. Process behaviours aur security anomalies check kar raha hoon."
    },
    "genesis": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "codename": "GENESIS",
        "role": "System Builder",
        "intro": "Genesis online hai. New project frameworks aur workspaces initialize ho gaye hain."
    },
    "vigil": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+5%",
        "pitch": "+4Hz",
        "codename": "VIGIL",
        "role": "Proactive Monitor",
        "intro": "Vigil active hai. Alert thresholds aur anomaly metrics check kar liye hain."
    },
    "nexus": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "codename": "NEXUS",
        "role": "Distributed Analysis",
        "intro": "Nexus swarm node active hai. Memory sync aur cluster load balance configuration completed."
    },
    "archon": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "-5%",
        "pitch": "+2Hz",
        "codename": "ARCHON",
        "role": "Architecture Coordinator",
        "intro": "Archon online hai. System microservices aur API bounds load ho gaye hain."
    },
    "forge": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+5%",
        "pitch": "-3Hz",
        "codename": "FORGE",
        "role": "Code Synthesizer",
        "intro": "Forge active hai. Distributed workspace files build aur compile hone ke liye ready hain."
    },
    "insight": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "-5%",
        "pitch": "+5Hz",
        "codename": "INSIGHT",
        "role": "Deep Research",
        "intro": "Insight active hai. Internal documentation aur research archives sync ho gaye hain."
    },
    "scribe": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "+0%",
        "pitch": "+3Hz",
        "codename": "SCRIBE",
        "role": "Documentation Engine",
        "intro": "Scribe online hai, Sir. System commands aur output logging templates write ho chuke hain."
    },
    "sentinel": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "-8%",
        "pitch": "-5Hz",
        "codename": "SENTINEL",
        "role": "Vulnerability Scanner",
        "intro": "Sentinel ready hai. Vulnerability lists aur exposed ports analysis load kar liya hai."
    },
    "pulse": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+10%",
        "pitch": "+0Hz",
        "codename": "PULSE",
        "role": "Runtime Orchestrator",
        "intro": "Pulse online. Multiprocessing threads aur event loops properly check ho gaye hain."
    },
    "atlas": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+0%",
        "pitch": "+2Hz",
        "codename": "ATLAS",
        "role": "Tool Manager",
        "intro": "Atlas active hai. Integration APIs aur third-party wrapper tools ready hain."
    },
    "command": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "-3%",
        "pitch": "+0Hz",
        "codename": "COMMAND",
        "role": "Sub-Task Delegator",
        "intro": "Command node online hai. Work tasks delegate aur assign karne ke liye taiyar."
    },
    "hunter": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "+5%",
        "pitch": "-10Hz",
        "codename": "HUNTER",
        "role": "Google Dorker",
        "intro": "Hunter active hai. Google OSINT dorks aur search payloads execute ho rahe hain."
    },
    "reaper": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "-12%",
        "pitch": "-8Hz",
        "codename": "REAPER",
        "role": "Pentest Automation",
        "intro": "Reaper ready hai. Metasploit interfaces aur target probes bind kar liye hain."
    },
    "ghost": {
        "voice": "en-IN-PrabhatNeural",
        "rate": "-5%",
        "pitch": "+5Hz",
        "codename": "GHOST",
        "role": "Phantom Tracer",
        "intro": "Ghost online hai, Sir. Track logs clean ho rahe hain aur routing camouflage ready hai."
    },
    "webweaver": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "-8%",
        "pitch": "-3Hz",
        "codename": "WEBWEAVER",
        "role": "Leak Graph Analyst",
        "intro": "Webweaver ready hai. Leak analysis mappings aur network traces sync ho rahe hain."
    },
    "strategos": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "-5%",
        "pitch": "-5Hz",
        "codename": "STRATEGOS",
        "role": "Strategic Planner",
        "intro": "Strategos active hai, Sir. Target scan objectives aur alternate routes map kar liye hain."
    },
    "validator": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "+5%",
        "pitch": "+0Hz",
        "codename": "VALIDATOR",
        "role": "Runtime Verifier",
        "intro": "Validator online. Checksums aur compile metrics complete ho chuke hain."
    },
    "blueprint": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+0%",
        "pitch": "+3Hz",
        "codename": "BLUEPRINT",
        "role": "Diagram Architect",
        "intro": "Blueprint active hai, Sir. Vector architecture diagrams render ho rahe hain."
    },
    "diagnostician": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+0%",
        "pitch": "+3Hz",
        "codename": "DIAGNOSTICIAN",
        "role": "DiagnosisAgent",
        "intro": "Diagnostician active hai, Sir. System layers, environment configs, aur code files fully diagnose karne ke liye taiyar."
    },
    "antigravity": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "codename": "ANTIGRAVITY",
        "role": "AntigravityAgent",
        "intro": "Antigravity agent online hai, Sir. Autonomously swarm agents ko command aur track karne ke liye system synchronized hai."
    },
    "medic": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "codename": "MEDIC",
        "role": "RepairAgent",
        "intro": "Medic online hai, Sir. Self-healing protocols aur auto-repair systems fully armed hain."
    }
}

# Derived dicts for easy access
AGENT_CODENAMES = {k: v["codename"] for k, v in VOICE_PROFILES.items()}
AGENT_INTRODUCTIONS = {k: v["intro"] for k, v in VOICE_PROFILES.items()}

def get_voice_profile(agent_id: str) -> dict:
    """Returns the voice profile details for the given agent_id, or default values."""
    cleaned_id = agent_id.lower().strip()
    if cleaned_id in VOICE_PROFILES:
        return VOICE_PROFILES[cleaned_id]
    return {
        "voice": DEFAULT_VOICE,
        "rate": "+0%",
        "pitch": "+0Hz",
        "codename": agent_id.upper(),
        "role": "AERIS Agent",
        "intro": f"Agent {agent_id} active aur online hai."
    }

def get_all_agent_ids() -> list:
    """Returns a list of all 35 agent IDs in the system."""
    return list(VOICE_PROFILES.keys())
