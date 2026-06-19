"""
AERIS — Folder Intelligence Engine
═══════════════════════════════════════════════════════════════════════
Smart folder resolution system that understands vague, colloquial,
and Hinglish folder references. Features:
  • Known-folders registry (AERIS project + system dirs)
  • Rich alias map (English + Hindi/Hinglish, 50+ entries)
  • Fuzzy token-based matching with confidence scoring
  • Conversational context tracking (last browsed folder)
  • Hinglish suffix/prefix stripping ("wala folder", "ka folder")
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("aeris.folder_intelligence")


@dataclass
class FolderMatch:
    """A resolved folder path with confidence metadata."""
    path: str
    confidence: float        # 0.0 – 1.0
    match_type: str          # "exact_alias" | "fuzzy" | "context" | "drive" | "known_folder"
    matched_alias: str = ""  # Which alias/token triggered the match

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "confidence": round(self.confidence, 2),
            "match_type": self.match_type,
            "matched_alias": self.matched_alias,
        }


# ═══════════════════════════════════════════════════════════════════
#  Hinglish noise words to strip before matching
# ═══════════════════════════════════════════════════════════════════

_HINGLISH_NOISE = [
    # Suffixes / postpositions
    "wala folder", "wali folder", "wala", "wali",
    "ka folder", "ki folder", "ke folder",
    "ka", "ki", "ke",
    "mein", "me", "mai",
    "pe", "par", "pr",
    "se", "ko",
    # Action verbs (strip if present)
    "kholo", "khol do", "khol de", "open karo", "open kr",
    "dikhao", "dikha do", "dikha de", "show karo", "show kr",
    "list karo", "list kr", "dekhao", "dekha do",
    "kya hai", "kya hain", "kya files hai", "kya files hain",
    # Filler
    "folder", "directory", "dir", "path",
    "mera", "meri", "mere", "apna", "apni", "apne",
    "wo", "woh", "us", "uska", "uski", "uske",
    "is", "iska", "iski", "iske", "ye", "yeh",
    "jo", "hai", "hain", "tha", "the", "thi",
    "karo", "kr", "kar", "do", "de",
]

# Sort by length descending so longer phrases are stripped first
_HINGLISH_NOISE.sort(key=len, reverse=True)


def _clean_query(raw: str) -> str:
    """Strip Hinglish noise words, action verbs, and normalize the query."""
    text = raw.strip().lower()
    # Remove common Hinglish suffixes/noise (longest first)
    for noise in _HINGLISH_NOISE:
        # Use word-boundary-ish matching to avoid partial word replacement
        pattern = r'\b' + re.escape(noise) + r'\b'
        text = re.sub(pattern, ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _tokenize(text: str) -> List[str]:
    """Split cleaned text into meaningful tokens."""
    return [t for t in text.lower().split() if len(t) >= 2]


def _token_similarity(query_tokens: List[str], candidate: str) -> float:
    """
    Compute how well query tokens match a candidate folder name.
    Returns 0.0 – 1.0.
    """
    if not query_tokens:
        return 0.0
    
    candidate_lower = candidate.lower().replace(" ", "").replace("_", "").replace("-", "")
    candidate_tokens = _tokenize(candidate.lower().replace("_", " ").replace("-", " "))
    
    score = 0.0
    total_weight = len(query_tokens)
    
    for qt in query_tokens:
        qt_clean = qt.replace("_", "").replace("-", "")
        
        # Exact token match
        if qt in candidate_tokens:
            score += 1.0
        # Substring match (query token appears in candidate)
        elif qt_clean in candidate_lower:
            score += 0.8
        # Candidate token starts with query token (prefix match)
        elif any(ct.startswith(qt_clean) for ct in candidate_tokens):
            score += 0.7
        # Query token starts with candidate token
        elif any(qt_clean.startswith(ct) for ct in candidate_tokens if len(ct) >= 3):
            score += 0.5
    
    return min(score / total_weight, 1.0) if total_weight > 0 else 0.0


class FolderIntelligence:
    """
    Smart folder resolution engine for AERIS.
    
    Usage:
        fi = get_folder_intelligence()
        match = fi.resolve("backend wala folder")
        # FolderMatch(path="d:\\Sambhav Projects\\AERIS\\BACKEND", confidence=0.95, ...)
    """

    def __init__(self):
        self._known_folders: Dict[str, str] = {}   # alias → absolute path
        self._folder_index: Dict[str, str] = {}    # folder_name_lower → absolute path
        self._last_context_folder: Optional[str] = None
        self._last_context_time: float = 0.0
        self._context_ttl: float = 300.0  # 5 minutes
        self._initialized = False

    def initialize(self):
        """Build the known-folders registry. Called lazily on first resolve()."""
        if self._initialized:
            return
        
        self._build_known_folders()
        self._initialized = True
        logger.info(f"[FolderIntelligence] Initialized with {len(self._known_folders)} aliases, "
                     f"{len(self._folder_index)} indexed folders.")

    # ─────────────────────────── Known Folders ────────────────────────────

    def _build_known_folders(self):
        """Populate the known-folders registry with AERIS project dirs + system dirs."""
        
        # ── AERIS Project Directories ──
        try:
            from config import settings
            aeris_root = settings.BASE_DIR.parent  # d:\Sambhav Projects\AERIS
            backend = settings.BASE_DIR             # d:\Sambhav Projects\AERIS\BACKEND
            workspace = settings.WORKSPACE_DIR      # d:\Sambhav Projects\AERIS\workspace
        except Exception:
            aeris_root = Path("d:/Sambhav Projects/AERIS")
            backend = aeris_root / "BACKEND"
            workspace = aeris_root / "workspace"

        frontend = aeris_root / "FRONTEND"
        data_root = aeris_root / "data"

        # Register AERIS project structure with rich aliases
        aeris_aliases = {
            # Root
            "aeris": str(aeris_root),
            "aeris project": str(aeris_root),
            "aeris root": str(aeris_root),
            "project root": str(aeris_root),
            "main project": str(aeris_root),
            "project": str(aeris_root),
            "root": str(aeris_root),

            # Backend
            "backend": str(backend),
            "back end": str(backend),
            "server": str(backend),
            "backend code": str(backend),
            "python code": str(backend),

            # Frontend
            "frontend": str(frontend),
            "front end": str(frontend),
            "ui": str(frontend),
            "frontend code": str(frontend),
            "react": str(frontend),
            "next": str(frontend),
            "nextjs": str(frontend),

            # Workspace
            "workspace": str(workspace),
            "work space": str(workspace),
            "generated projects": str(workspace),

            # Backend subdirectories
            "agents": str(backend / "agents"),
            "agent": str(backend / "agents"),
            "sub agents": str(backend / "agents" / "sub_agents"),
            "subagents": str(backend / "agents" / "sub_agents"),
            "automation": str(backend / "automation"),
            "services": str(backend / "services"),
            "service": str(backend / "services"),
            "tools": str(backend / "tools"),
            "tool": str(backend / "tools"),
            "intelligence": str(backend / "intelligence"),
            "intel": str(backend / "intelligence"),
            "memory": str(backend / "memory"),
            "neural": str(backend / "neural"),
            "engine": str(backend / "engine"),
            "plugins": str(backend / "plugins"),
            "plugin": str(backend / "plugins"),
            "utils": str(backend / "utils"),
            "utility": str(backend / "utils"),
            "generation": str(backend / "generation"),
            "data": str(backend / "data"),
            "backend data": str(backend / "data"),
            "screenshots": str(backend / "Screenshots"),
            "scratch": str(backend / "scratch"),
            "calculator": str(backend / "calculator"),
            "generated sites": str(backend / "generated_sites"),
            "drana": str(backend / "Drana features"),
            "drana features": str(backend / "Drana features"),

            # Root-level data/models
            "root data": str(data_root),
            "project data": str(data_root),
            "models": str(data_root / "models"),
            "generated images": str(data_root / "generated_images"),
            "generated videos": str(data_root / "generated_videos"),
            "audit": str(data_root / "audit"),
            "workflows": str(data_root / "workflows"),

            # Frontend subdirectories
            "src": str(frontend / "src"),
            "source": str(frontend / "src"),
            "public": str(frontend / "public"),
            "components": str(frontend / "src" / "components") if (frontend / "src" / "components").exists() else str(frontend / "src"),
        }

        # ── System Directories ──
        home = Path.home()
        
        # Detect OneDrive paths
        onedrive_desktop = home / "OneDrive" / "Desktop"
        onedrive_docs = home / "OneDrive" / "Documents"
        desktop = onedrive_desktop if onedrive_desktop.is_dir() else home / "Desktop"
        documents = onedrive_docs if onedrive_docs.is_dir() else home / "Documents"

        system_aliases = {
            # Standard user folders
            "downloads": str(home / "Downloads"),
            "download": str(home / "Downloads"),
            "download folder": str(home / "Downloads"),
            "mera download": str(home / "Downloads"),
            
            "desktop": str(desktop),
            "desk": str(desktop),
            "mera desktop": str(desktop),
            
            "documents": str(documents),
            "document": str(documents),
            "docs": str(documents),
            "my documents": str(documents),
            "mera document": str(documents),
            
            "pictures": str(home / "Pictures"),
            "photos": str(home / "Pictures"),
            "images": str(home / "Pictures"),
            "meri photos": str(home / "Pictures"),
            
            "videos": str(home / "Videos"),
            "video": str(home / "Videos"),
            "meri videos": str(home / "Videos"),
            
            "music": str(home / "Music"),
            "songs": str(home / "Music"),
            "gaane": str(home / "Music"),
            
            "home": str(home),
            "user folder": str(home),
            "home directory": str(home),
            "mera folder": str(home),
            
            # AppData
            "appdata": str(home / "AppData"),
            "app data": str(home / "AppData"),
            "local appdata": str(home / "AppData" / "Local"),
            "roaming": str(home / "AppData" / "Roaming"),
            "temp": str(home / "AppData" / "Local" / "Temp"),
            "temporary": str(home / "AppData" / "Local" / "Temp"),
            
            # Program Files
            "program files": str(Path("C:/Program Files")),
            "programs": str(Path("C:/Program Files")),
            
            # Startup
            "startup": str(home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"),
        }

        # ── Drive Letters ──
        drive_aliases = {}
        for letter in "CDEFGHIJ":
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drive_aliases[f"{letter.lower()} drive"] = drive_path
                drive_aliases[f"{letter.lower()}"] = drive_path
                drive_aliases[f"{letter.lower()} wali drive"] = drive_path
                drive_aliases[f"{letter.lower()} wala drive"] = drive_path
                drive_aliases[f"drive {letter.lower()}"] = drive_path

        # Merge all
        self._known_folders = {**aeris_aliases, **system_aliases, **drive_aliases}

        # ── Build folder name index (for fuzzy matching) ──
        # Index actual directory names that exist on disk
        self._folder_index = {}
        for alias, path in self._known_folders.items():
            if os.path.isdir(path):
                folder_name = os.path.basename(path).lower()
                if folder_name and folder_name not in self._folder_index:
                    self._folder_index[folder_name] = path

        # Also index immediate children of key directories for deeper matching
        for scan_dir in [str(backend), str(frontend), str(aeris_root), str(aeris_root.parent)]:
            try:
                if os.path.isdir(scan_dir):
                    for entry in os.scandir(scan_dir):
                        if entry.is_dir() and not entry.name.startswith('.'):
                            name_lower = entry.name.lower()
                            if name_lower not in self._folder_index:
                                self._folder_index[name_lower] = entry.path
            except (PermissionError, OSError):
                pass

    # ─────────────────────────── Context Tracking ─────────────────────────

    def set_context(self, folder_path: str):
        """Record the last folder the user interacted with."""
        if os.path.isdir(folder_path):
            self._last_context_folder = folder_path
            self._last_context_time = time.time()
            logger.debug(f"[FolderIntelligence] Context set to: {folder_path}")

    def get_context(self) -> Optional[str]:
        """Get the last folder context, if still fresh."""
        if self._last_context_folder and (time.time() - self._last_context_time) < self._context_ttl:
            return self._last_context_folder
        return None

    def clear_context(self):
        """Clear the folder context."""
        self._last_context_folder = None

    # ─────────────────────────── Core Resolution ──────────────────────────

    def resolve(self, raw_query: str, conversation_history: Optional[List[dict]] = None) -> Optional[FolderMatch]:
        """
        Resolve a natural language folder reference to an absolute path.
        
        Args:
            raw_query: User's raw input (can be Hinglish, vague, colloquial)
            conversation_history: Recent conversation messages for pronoun resolution
            
        Returns:
            FolderMatch with path and confidence, or None if no match found.
        """
        self.initialize()
        
        query = raw_query.strip().lower()
        if not query:
            return None

        # ── Step 1: Exact alias match (highest priority) ──
        match = self._try_exact_alias(query)
        if match:
            return match

        # ── Step 2: Clean Hinglish noise and try alias again ──
        cleaned = _clean_query(query)
        if cleaned and cleaned != query:
            match = self._try_exact_alias(cleaned)
            if match:
                return match

        # ── Step 3: Drive letter detection ──
        match = self._try_drive_match(query)
        if match:
            return match

        # ── Step 4: Pronoun/context resolution ──
        if self._is_pronoun_reference(query):
            ctx = self.get_context()
            if ctx:
                return FolderMatch(
                    path=ctx,
                    confidence=0.75,
                    match_type="context",
                    matched_alias=f"pronoun → {os.path.basename(ctx)}",
                )

        # ── Step 5: Fuzzy match against known folders ──
        match = self._try_fuzzy_match(cleaned or query)
        if match:
            return match

        # ── Step 6: Fuzzy match against folder name index ──
        match = self._try_index_fuzzy(cleaned or query)
        if match:
            return match

        # ── Step 7: Try as literal path ──
        match = self._try_literal_path(raw_query)
        if match:
            return match

        logger.debug(f"[FolderIntelligence] No match for: '{raw_query}' (cleaned: '{cleaned}')")
        return None

    def _try_exact_alias(self, query: str) -> Optional[FolderMatch]:
        """Check if query matches a known alias exactly."""
        path = self._known_folders.get(query)
        if path and os.path.isdir(path):
            return FolderMatch(
                path=path,
                confidence=1.0,
                match_type="exact_alias",
                matched_alias=query,
            )
        return None

    def _try_drive_match(self, query: str) -> Optional[FolderMatch]:
        """Detect drive letter references like 'd drive', 'D:', 'd wali drive'."""
        # Pattern: single letter + optional noise
        m = re.match(r'^([a-z])\s*(?:drive|wali\s*drive|wala\s*drive|:)?$', query.strip())
        if m:
            letter = m.group(1).upper()
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                return FolderMatch(
                    path=drive_path,
                    confidence=0.95,
                    match_type="drive",
                    matched_alias=f"{letter} drive",
                )
        # Also check "d pe kya hai", "d mein"
        m = re.match(r'^([a-z])\s*(?:pe|par|pr|mein|me|mai|drive\s*(?:pe|par|mein|me))', query.strip())
        if m:
            letter = m.group(1).upper()
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                return FolderMatch(
                    path=drive_path,
                    confidence=0.90,
                    match_type="drive",
                    matched_alias=f"{letter} drive",
                )
        return None

    def _is_pronoun_reference(self, query: str) -> bool:
        """Check if the query is referring to a previously mentioned folder via pronouns."""
        pronoun_patterns = [
            r'\b(wo|woh|us|uska|uski|uske|isko|usko)\b',
            r'\b(isme|usme|usme|yahi|wahi|same)\b',
            r'\b(that|this|it|the same|previous|last)\b',
            r'\b(pichla|pichle|wala|wali)\s*folder\b',
        ]
        for pattern in pronoun_patterns:
            if re.search(pattern, query):
                return True
        return False

    def _try_fuzzy_match(self, query: str) -> Optional[FolderMatch]:
        """Fuzzy match query tokens against known folder aliases."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return None

        best_match: Optional[FolderMatch] = None
        best_score = 0.0

        for alias, path in self._known_folders.items():
            if not os.path.isdir(path):
                continue
            
            alias_tokens = _tokenize(alias)
            if not alias_tokens:
                continue

            # Score: how well query tokens match this alias
            score = _token_similarity(query_tokens, alias)
            
            # Bonus: if the query contains the full alias as substring
            if alias in query.lower():
                score = max(score, 0.9)

            if score > best_score and score >= 0.6:
                best_score = score
                best_match = FolderMatch(
                    path=path,
                    confidence=min(score, 0.95),  # Cap at 0.95 for fuzzy
                    match_type="fuzzy",
                    matched_alias=alias,
                )

        return best_match

    def _try_index_fuzzy(self, query: str) -> Optional[FolderMatch]:
        """Fuzzy match against the indexed folder names (actual directory names on disk)."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return None

        best_match: Optional[FolderMatch] = None
        best_score = 0.0

        for folder_name, path in self._folder_index.items():
            score = _token_similarity(query_tokens, folder_name)

            if score > best_score and score >= 0.6:
                best_score = score
                best_match = FolderMatch(
                    path=path,
                    confidence=min(score * 0.9, 0.85),  # Slightly lower confidence for index matches
                    match_type="known_folder",
                    matched_alias=folder_name,
                )

        return best_match

    def _try_literal_path(self, raw_query: str) -> Optional[FolderMatch]:
        """Try interpreting the query as a literal file path."""
        expanded = os.path.expanduser(os.path.expandvars(raw_query.strip()))
        if os.path.isdir(expanded):
            return FolderMatch(
                path=str(Path(expanded).resolve()),
                confidence=1.0,
                match_type="exact_alias",
                matched_alias="literal_path",
            )
        return None

    # ─────────────────────────── Utilities ─────────────────────────────────

    def get_known_folders_summary(self, max_entries: int = 20) -> str:
        """Format known folders as a compact string for LLM prompt injection."""
        self.initialize()
        
        # Group by path to avoid duplication, pick shortest alias per path
        path_to_aliases: Dict[str, List[str]] = {}
        for alias, path in self._known_folders.items():
            if os.path.isdir(path):
                path_to_aliases.setdefault(path, []).append(alias)
        
        lines = []
        for path, aliases in sorted(path_to_aliases.items()):
            # Pick the shortest/most common alias as the display name
            display = min(aliases, key=len)
            lines.append(f"- \"{display}\" → {path}")
            if len(lines) >= max_entries:
                break
        
        return "\n".join(lines)

    def get_all_aliases(self) -> Dict[str, str]:
        """Return all known aliases (for testing/debugging)."""
        self.initialize()
        return dict(self._known_folders)


# ═══════════════════════════════════════════════════════════════════
#  Global Singleton
# ═══════════════════════════════════════════════════════════════════

_folder_intelligence: Optional[FolderIntelligence] = None


def get_folder_intelligence() -> FolderIntelligence:
    """Get or create the global FolderIntelligence singleton."""
    global _folder_intelligence
    if _folder_intelligence is None:
        _folder_intelligence = FolderIntelligence()
    return _folder_intelligence
