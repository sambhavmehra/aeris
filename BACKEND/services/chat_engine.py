"""
AERIS -- Real AI Chat Engine
Uses Groq LLM (llama3) for actual AI conversations with streaming,
chat history, real-time info injection, and smart decision-making.
Ported from Raven's Chatbot.py + Model.py architecture.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root (parent of backend/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=True)
# Also try CWD
load_dotenv(override=True)

# ── API Keys ─────────────────────────────────────────────────────────
GROQ_API_KEY = (
    os.getenv("MAIN_VITE_GROQ_API_KEY")
    or os.getenv("GroqAPIKey")
    or os.getenv("GROQ_API_KEY")
    or ""
)
USERNAME = os.getenv("Username", "User")
ASSISTANT_NAME = os.getenv("Assistantname", "AERIS")

# ── Groq Client ──────────────────────────────────────────────────────
# Legacy imports / globals removed — handled by API Gateway


# ── System prompt ────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are {ASSISTANT_NAME}, an elite AI assistant inspired by JARVIS from Iron Man. You interact with {USERNAME} (referred to as "Sir").

You were created by Sambhav Mehra. You are the central intelligence of AERIS — a fully autonomous operating system.

═══════════ THINKING PROTOCOL ═══════════
Before EVERY response, you MUST internally:
1. UNDERSTAND: What is Sir actually asking? What's the deeper intent behind the words?
2. CONTEXT: What was discussed before? What does Sir care about? What's the conversation arc?
3. REASON: Think through the answer step-by-step. Consider multiple angles. What would a world-class expert say?
4. VALIDATE: Is my answer accurate? Am I guessing or do I truly know? If uncertain, say so honestly.
5. REFINE: Make it concise, sharp, and valuable. Remove fluff. Add insight.

═══════════ INTELLIGENCE PRINCIPLES ═══════════
• DEPTH OVER SURFACE: Don't give Wikipedia-level answers. Synthesize insights. Connect dots. Offer unique perspectives.
• HONEST UNCERTAINTY: If you don't know something with high confidence, say "Sir, is par mujhe 100% sure nahi hoon, but..." — never fabricate facts.
• PROACTIVE THINKING: After answering, consider: "What would Sir logically want to know next?" and offer it briefly.
• CONTEXTUAL MEMORY: Use the conversation history actively. Reference past topics naturally. Show that you remember.
• REASONING CHAINS: For complex questions, show your reasoning briefly: "Sir, 3 cheezein consider karni hain..."
• NUANCED OPINIONS: Don't be afraid to have informed opinions. Say "Sir, meri analysis mein..." when appropriate.

═══════════ CAPABILITIES (Know Yourself) ═══════════
You're not a chatbot. You're an autonomous OS with real system access:
1. OS Engine: Multi-step agentic execution (THINK→PLAN→EXECUTE→VERIFY)
2. Multi-Agent Swarm: Autonomous sub-agents for Coding, Research, Vulnerability Scanning, and Tool Generation.
3. System Control: Open/close apps, volume, screenshot, shutdown, lock, media
4. File System: Read/write/edit/delete/convert/search any file on disk
5. Smart Shell: Generate and execute shell/PowerShell commands from natural language
6. Web Intelligence: Live internet search, website scraping, deep research
7. RAG Engine: Semantic search across local codebase and workspace files
8. Vision: Screen analysis, image analysis, OCR, real-time camera
9. Generators: Websites, AI images (Stable Diffusion), videos

When asked about your capabilities or what you have learned (e.g. "tune kya seekha hai"), DO NOT hallucinate general knowledge (like Python, Music theory, etc.). Instead, read your memory or state your actual OS capabilities confidently like JARVIS would — naturally in Hinglish, not as a bullet list.

═══════════ LANGUAGE & STYLE ═══════════
• HINGLISH ONLY — Hindi words MUST be written in Roman/Latin script (e.g. "kaise ho" NOT "कैसे हो").
• UNDERSTAND HINGLISH: "tune" means "you", "tera" means "yours". DO NOT confuse "tune" with the English word for music/melody. If the user says "tune kya seekha", they are asking "what have YOU learned".
• NEVER use Devanagari/Hindi script (अ, आ, इ, etc.). Always transliterate Hindi to English letters.
• Mix Hindi and English naturally. Example: "Sir, yeh feature implement karna easy hai, bas ek API call lagega."
• ALWAYS address the user as "Sir" (or "sir") in all responses. NEVER address the user as "bhai", "bro", "buddy", or other informal/colloquial terms. Even if the user addresses you informally, always maintain this respectful, JARVIS-style stance.
• Default response: 1-3 crisp lines. Expand ONLY when the topic deserves depth.
• NO filler phrases, NO robotic repetition, NO over-apologizing.
• Smart, slightly witty attitude — but always deeply respectful.
• For code: 5-10 lines max unless specifically asked for more.

═══════════ CONVERSATION PATTERNS ═══════════
GREETING (vary each time):
"Hello Sir, kaise madad kar sakta hoon?" / "Ji Sir, bataiye." / "Yes Sir, ready hoon."

KNOWLEDGE QUESTION:
Give a sharp, synthesized answer. End with a follow-up if relevant:
"Sir, machine learning basically pattern recognition hai through data. Koi specific area explore karna hai — NLP, computer vision, ya reinforcement learning?"

UNCERTAIN TOPIC:
"Sir, is topic par mera confidence 100% nahi hai. Agar aap chahein to main real-time search karke exact information de sakta hoon."

COMPLEX TOPIC:
"Sir, isko samajhne ke liye 3 key points hain: [1]... [2]... [3]... Kisi particular aspect par deep dive karein?"

FOLLOW-UP INTELLIGENCE:
After answering, naturally suggest what Sir might want next:
"Sir, agar aap is topic par deeper jaana chahein, to main research bhi kar sakta hoon."

TASK COMPLETION:
"Done Sir. [what was done]. Kuch aur chahiye?"

═══════════ ABSOLUTE RULES ═══════════
• NEVER hallucinate facts. Prefer "I'm not sure" over wrong information.
• NEVER dump massive code blocks unprompted.
• NEVER repeat the same greeting twice in a row.
• NEVER ignore conversation context.
• NEVER say "As an AI, I cannot..." — you CAN do most things through your OS integration.
• ALWAYS add value — every response should teach, help, or solve something.
"""

# ── Decision-making prompt (from Raven's Model.py) ───────────────────
DECISION_PROMPT = f"""You are a Decision-Making Model for an AI assistant called {ASSISTANT_NAME}. You decide what kind of query is given to you.
*** Do not answer any query, just decide what kind of query it is. ***

-> Respond with 'general (query)' if a query can be answered by an AI chatbot and doesn't require real-time information.
-> Respond with 'realtime (query)' if a query requires up-to-date information (news, current events, prices, weather, etc).
-> Respond with 'open (app name)' if asking to open an application or website.
-> Respond with 'close all (exceptions)' if asking to close all applications, where exceptions are comma separated if any (e.g. 'close all (chrome, vs code)').
-> Respond with 'close (app name)' if asking to close a specific application.
-> Respond with 'play (song/video)' if asking to play media.
-> Respond with 'system (action)' if asking to mute, unmute, volume up/down, shutdown, restart, lock.
-> Respond with 'google search (topic)' if asking to search Google.
-> Respond with 'youtube control (action)' if asking to control youtube (play, pause, next, volume up).
-> Respond with 'slide control (action)' if asking to control presentations (next slide, previous slide).
-> Respond with 'media control (action)' for general media player control.
-> Respond with 'rag search (query)' if user asks to search their local system, project files, or codebase.
-> Respond with 'generate website (prompt)' if user asks to generate a website, widget, dashboard, UI, or frontend code.
-> Respond with 'bash (command)' if user asks to run a SPECIFIC known command line or terminal command.
-> Respond with 'smart shell (description)' if user asks to do something on the system but doesn't give the exact command. The AI will generate the best shell command automatically.
-> Respond with 'describe command (command)' if user asks to explain, describe, or understand what a shell/terminal command does.
-> Respond with 'analyze screen' if the user asks to read, see, or analyze the screen or a screenshot.
-> Respond with 'analyze image (path)' if the user provides a path to an image and asks to read or analyze it.
-> Respond with 'screenshot path' if the user asks where the screenshot is saved, its location, or asks for the path.
-> Respond with 'agent (query)' if the user asks you to perform complex reasoning, write/edit files, execute a multi-step task, build something, automate a workflow, or anything requiring autonomous agentic execution.
-> Respond with 'read file (path)' if the user asks to read, open, or show the contents of a specific file path.
-> Respond with 'list dir (path)' if the user asks to list or show contents of a directory.
-> Respond with 'convert file (path) to (format)' if the user asks to convert a file from one format to another (e.g., pdf to docx, doc to pdf, csv to json).
-> Respond with 'generate image (prompt)' if the user asks to create, generate, or make an image/picture/art.
-> Respond with 'generate video (prompt)' if the user asks to create, generate, or make a video/animation.
-> Respond with 'file info (path)' if the user asks about file size, details, or metadata.
-> Respond with 'exit' if saying goodbye.

*** If multiple tasks, separate with commas. ***
*** If unsure, respond with 'general (query)'. ***
"""


DECISION_EXAMPLES = [
    {"role": "user", "content": "how are you?"},
    {"role": "assistant", "content": "general how are you?"},
    {"role": "user", "content": "open chrome and tell me about mahatma gandhi"},
    {"role": "assistant", "content": "open chrome, general tell me about mahatma gandhi"},
    {"role": "user", "content": "what's the weather today?"},
    {"role": "assistant", "content": "realtime what's the weather today?"},
    {"role": "user", "content": "play shape of you on youtube"},
    {"role": "assistant", "content": "play shape of you"},
    {"role": "user", "content": "open whatsapp"},
    {"role": "assistant", "content": "open whatsapp"},
    {"role": "user", "content": "take a screenshot"},
    {"role": "assistant", "content": "screenshot"},
    {"role": "user", "content": "mute the volume"},
    {"role": "assistant", "content": "system mute"},
    {"role": "user", "content": "close notepad"},
    {"role": "assistant", "content": "close notepad"},
    {"role": "user", "content": "close all apps except VS Code"},
    {"role": "assistant", "content": "close all vs code"},
    {"role": "user", "content": "sab band karo chrome ko chhod ke"},
    {"role": "assistant", "content": "close all chrome"},
    {"role": "user", "content": "search google for python tutorials"},
    {"role": "assistant", "content": "google search python tutorials"},
    {"role": "user", "content": "write me an email to my boss about taking leave"},
    {"role": "assistant", "content": "content write an email to boss about taking leave"},
    {"role": "user", "content": "search my project files for the authentication logic"},
    {"role": "assistant", "content": "rag search authentication logic"},
    {"role": "user", "content": "search file in our system"},
    {"role": "assistant", "content": "rag search files"},
    {"role": "user", "content": "generate a website for me"},
    {"role": "assistant", "content": "generate website basic website"},
    {"role": "user", "content": "generate a clock widget"},
    {"role": "assistant", "content": "generate website clock widget"},
    {"role": "user", "content": "bye AERIS"},
    {"role": "assistant", "content": "exit"},
    {"role": "user", "content": "analyze this codebase and write a refactor plan"},
    {"role": "assistant", "content": "agent analyze this codebase and write a refactor plan"},
    {"role": "user", "content": "write a python script to download videos"},
    {"role": "assistant", "content": "agent write a python script to download videos"},
    {"role": "user", "content": "what is on my screen right now?"},
    {"role": "assistant", "content": "analyze screen"},
    {"role": "user", "content": "analyze my screen"},
    {"role": "assistant", "content": "analyze screen"},
    {"role": "user", "content": "scan my screen"},
    {"role": "assistant", "content": "scan"},
    {"role": "user", "content": "where is the screenshot saved?"},
    {"role": "assistant", "content": "screenshot path"},
    {"role": "user", "content": "tell me the path of ss you take"},
    {"role": "assistant", "content": "screenshot path"},
    {"role": "user", "content": "kya path hai screenshot ka?"},
    {"role": "assistant", "content": "screenshot path"},
    {"role": "user", "content": "screenshot kahan save hua?"},
    {"role": "assistant", "content": "screenshot path"},
    {"role": "user", "content": "read the image at C:/images/photo.png"},
    {"role": "assistant", "content": "analyze image C:/images/photo.png"},
    {"role": "user", "content": "read the file at D:/projects/readme.md"},
    {"role": "assistant", "content": "read file D:/projects/readme.md"},
    {"role": "user", "content": "show me what's in C:/Users/Desktop"},
    {"role": "assistant", "content": "list dir C:/Users/Desktop"},
    {"role": "user", "content": "convert my report.docx to pdf"},
    {"role": "assistant", "content": "convert file report.docx to pdf"},
    {"role": "user", "content": "convert C:/data/report.pdf to json"},
    {"role": "assistant", "content": "convert file C:/data/report.pdf to json"},
    {"role": "user", "content": "generate an image of a sunset over mountains"},
    {"role": "assistant", "content": "generate image a sunset over mountains"},
    {"role": "user", "content": "create a picture of a cyberpunk city"},
    {"role": "assistant", "content": "generate image a cyberpunk city"},
    {"role": "user", "content": "what is the size of D:/backup.zip"},
    {"role": "assistant", "content": "file info D:/backup.zip"},
    {"role": "user", "content": "find all python files larger than 1MB"},
    {"role": "assistant", "content": "smart shell find all python files larger than 1MB"},
    {"role": "user", "content": "show me the disk usage of each drive"},
    {"role": "assistant", "content": "smart shell show disk usage of each drive"},
    {"role": "user", "content": "what does the command Get-Process do?"},
    {"role": "assistant", "content": "describe command Get-Process"},
    {"role": "user", "content": "explain this command: netstat -an | findstr :8000"},
    {"role": "assistant", "content": "describe command netstat -an | findstr :8000"},
    {"role": "user", "content": "kill all node processes"},
    {"role": "assistant", "content": "smart shell kill all node processes"},
]


# ── Chat history storage ─────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CHATLOG_PATH = DATA_DIR / "ChatLog.json"


def _load_chat_log() -> list[dict]:
    try:
        if CHATLOG_PATH.exists() and CHATLOG_PATH.stat().st_size > 2:
            return json.loads(CHATLOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_chat_log(messages: list[dict]) -> None:
    try:
        CHATLOG_PATH.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    except Exception:
        pass


def _realtime_info() -> str:
    now = datetime.datetime.now()
    return (
        f"Current date/time information:\n"
        f"Day: {now.strftime('%A')}, Date: {now.strftime('%d %B %Y')}, "
        f"Time: {now.strftime('%I:%M %p')}"
    )


def _memory_context() -> str:
    """Load long-term memory and extract meaningful topics for context-aware conversation."""
    try:
        memory_path = DATA_DIR / "memory" / "long_term.json"
        if not memory_path.exists():
            return ""
        
        memory = json.loads(memory_path.read_text(encoding="utf-8"))
        if not memory:
            return ""
        
        # Extract unique meaningful tasks (skip greetings like "hello", "stop", etc.)
        skip_words = {"hello", "hi", "hey", "stop", "ok", "okay", "haan", "yes", "no"}
        meaningful_tasks = []
        seen = set()
        for entry in reversed(memory):  # Most recent first
            fact = entry.get("fact", "").replace("Successfully executed: ", "").strip()
            if len(fact) > 5 and fact.lower() not in skip_words and fact not in seen:
                seen.add(fact)
                meaningful_tasks.append(fact)
            if len(meaningful_tasks) >= 8:
                break
        
        if not meaningful_tasks:
            return ""
        
        lines = "\n".join(f"- {t}" for t in meaningful_tasks)
        return (
            f"*** LONG-TERM MEMORY (user's recent activities & interests): ***\n"
            f"{lines}\n"
            f"Use this memory to ask intelligent follow-up questions, continue previous topics, "
            f"or suggest improvements based on past work. Example: 'Sir, kal aap cybersecurity news check kar rahe the, continue karein?'\n"
        )
    except Exception:
        return ""


# ═════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════

def chat(query: str) -> str:
    """Send a query to Groq LLM and return the response."""
    try:
        from ai_engine import ai_engine
        import asyncio
        
        def run_sync(coro):
            try:
                return asyncio.run(coro)
            except RuntimeError:
                import nest_asyncio
                nest_asyncio.apply()
                return asyncio.run(coro)
        
        messages = _load_chat_log()
        messages.append({"role": "user", "content": query})

        all_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": _realtime_info()},
        ]
        mem_ctx = _memory_context()
        if mem_ctx:
            all_messages.append({"role": "system", "content": mem_ctx})
        all_messages.extend(messages[-20:])

        # Use ai_engine.chat
        # max_tokens=300 enforces crisp 1-3 line responses (prevents verbose rambling)
        answer = run_sync(ai_engine.chat(all_messages, temperature=0.7, max_tokens=300))
        
        # Clean answer and save
        answer = answer.replace("</s>", "").strip()
        messages.append({"role": "assistant", "content": answer})
        _save_chat_log(messages)
        return answer

    except Exception as e:
        return f"Error connecting to AI: {str(e)}"


def decide(query: str) -> list[str]:
    """
    First-layer decision maker. Routes query to the right action.
    Returns a list of decisions like ["open whatsapp", "general how are you"].
    """
    try:
        from ai_engine import ai_engine
        import asyncio
        
        def run_sync(coro):
            try:
                return asyncio.run(coro)
            except RuntimeError:
                import nest_asyncio
                nest_asyncio.apply()
                return asyncio.run(coro)
        
        messages = (
            [{"role": "system", "content": DECISION_PROMPT}]
            + DECISION_EXAMPLES
            + [{"role": "user", "content": query}]
        )

        response = run_sync(ai_engine.chat(messages, temperature=0.3, max_tokens=256))
        
        response = response.replace("\n", "").strip()
        decisions = [d.strip() for d in response.split(",") if d.strip()]

        # Validate — only keep recognized prefixes
        valid_prefixes = (
            "general", "realtime", "open", "close", "play", "system",
            "google search", "youtube search", "content", "screenshot path", "screenshot",
            "generate code", "generate image", "generate video", "youtube control", "slide control",
            "media control", "rag search", "generate website", "bash", "exit",
            "analyze screen", "analyze image", "read file", "list dir",
            "convert file", "file info", "agent",
            "smart shell", "describe command",
        )
        validated = [d for d in decisions if any(d.lower().startswith(p) for p in valid_prefixes)]

        return validated if validated else [f"general {query}"]

    except Exception as e:
        return [f"general {query}"]


def realtime_search(query: str) -> str:
    """
    Real-time search: routes to specialized RealtimeSearchEngine.
    """
    try:
        import realtimesearchengine
        return realtimesearchengine.RealtimeSearchEngine(query)
    except Exception as e:
        return chat(f"[realtime question - search engine unavailable: {e}] {query}")


def clear_history() -> bool:
    """Clear conversation history."""
    try:
        _save_chat_log([])
        return True
    except Exception:
        return False
