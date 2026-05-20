"""
AERIS -- Advanced Agentic RAG Voice Engine (v2)
Combines:
  - Local file indexing + semantic search (RAG)
  - AST-aware Python code understanding (function/class extraction)
  - Persistent long-term episodic memory (JSON-backed)
  - Voice command processing with context awareness
  - Agentic decision-making: decide what to do, not just what to say
  - Conversation memory with sliding context window
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import nltk
try:
    nltk.data.find('corpora/stopwords')
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('taggers/averaged_perceptron_tagger_eng')
except LookupError:
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    nltk.download('averaged_perceptron_tagger_eng', quiet=True)
    nltk.download('punkt_tab', quiet=True)
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk import pos_tag

def _extract_keywords(text: str) -> str:
    """Uses NLTK NLP to extract critical noun/verb phrases, stripping stop words."""
    try:
        stop_words = set(stopwords.words('english'))
        words = word_tokenize(text)
        # Keep words that are not stopwords and are alphanumeric
        filtered_words = [w for w in words if w.casefold() not in stop_words and w.isalnum()]
        
        # Further refine using POS tagging to weight Nouns and significant verbs higher
        tagged = pos_tag(filtered_words)
        keywords = []
        for word, tag in tagged:
            if tag.startswith('NN') or tag.startswith('VB') or tag.startswith('JJ'):
                keywords.append(word)
        
        # Fallback if too aggressive
        if len(keywords) == 0:
            return " ".join(filtered_words)
            
        return " ".join(keywords)
    except Exception as e:
        return text


# =====================================================================
#  VECTOR STORE -- minimal local embedding store for RAG
# =====================================================================

def _simple_embed(text: str, dim: int = 768) -> list[float]:
    """
    Multi-tier embedding pipeline:
      1. Cohere embed-english-v3.0  (if COHERE_API_KEY is set)
      2. Gemini text-embedding-004  (if AERIS_REMOTE_EMBEDDINGS=1)
      3. Local trigram hashing       (always available, zero-cost)
    """
    # ── Tier 1: Cohere Embeddings (Primary) ───────────────────────────────────
    cohere_key = os.getenv("COHERE_API_KEY", "").strip()
    if cohere_key:
        try:
            import requests
            resp = requests.post(
                "https://api.cohere.ai/v1/embed",
                headers={
                    "Authorization": f"Bearer {cohere_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "embed-english-v3.0",
                    "texts": [text[:2048]],
                    "input_type": "search_document",
                },
                timeout=5,
            )
            if resp.status_code == 200:
                embeddings = resp.json().get("embeddings", [[]])
                if embeddings and len(embeddings[0]) > 0:
                    return embeddings[0]
        except Exception as e:
            print(f"Cohere Embedding warning: {type(e).__name__}. Falling back to Gemini...")

    # ── Tier 2: Gemini Embeddings (Fallback) ──────────────────────────────────
    if os.getenv("AERIS_REMOTE_EMBEDDINGS", "").strip().lower() in {"1", "true", "yes"}:
        try:
            from dotenv import dotenv_values
            import requests

            env = dotenv_values(".env")
            api_key = env.get("VITE_GEMINI_API_KEY") or env.get("GEMINI_API_KEY")

            if api_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "model": "models/text-embedding-004",
                    "content": {
                        "parts": [{"text": text[:9000]}]  # limit size
                    }
                }

                response = requests.post(url, headers=headers, json=payload, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    return data["embedding"]["values"]
        except Exception as e:
            print(f"Gemini Embedding warning: {type(e).__name__}. Trying hashing...")

    # ── Tier 3: Local trigram hashing fallback ────────────────────────────────
    vector = [0.0] * dim
    text_lower = text.lower()
    for i in range(len(text_lower) - 2):
        trigram = text_lower[i : i + 3]
        h = int(hashlib.md5(trigram.encode()).hexdigest(), 16)
        idx = h % dim
        vector[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]



def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


@dataclass
class Document:
    doc_id: str
    source: str       # file path or URL
    content: str
    chunk_index: int = 0
    embedding: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class VectorStore:
    """In-memory vector store for local RAG."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.documents: list[Document] = []

    def add(self, source: str, content: str, metadata: dict | None = None) -> Document:
        doc = Document(
            doc_id=hashlib.md5(f"{source}:{len(self.documents)}".encode()).hexdigest()[:12],
            source=source,
            content=content,
            chunk_index=len(self.documents),
            embedding=_simple_embed(content, self.dim),
            metadata=metadata or {},
        )
        self.documents.append(doc)
        return doc

    def search(self, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
        query_vec = _simple_embed(query, self.dim)
        scored = [
            (doc, _cosine_similarity(query_vec, doc.embedding))
            for doc in self.documents
        ]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def count(self) -> int:
        return len(self.documents)


async def cohere_rerank(
    query: str,
    documents: list,
    top_k: int = 5,
) -> list:
    """
    Re-rank RAG search results using Cohere Rerank v3.
    Returns (Document, relevance_score) tuples sorted by Cohere's score.
    Falls back to the original cosine-similarity order if Cohere is unavailable.
    """
    import httpx

    api_key = os.getenv("COHERE_API_KEY", "").strip()
    if not api_key or not documents:
        return documents[:top_k]

    # documents is list[tuple[Document, float]] from VectorStore.search()
    docs = [d for d, _ in documents]
    doc_contents = [d.content[:1000] for d in docs]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.cohere.ai/v1/rerank",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "rerank-english-v3.0",
                    "query": query,
                    "documents": doc_contents,
                    "top_n": top_k,
                },
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                reranked = []
                for r in results:
                    idx = r["index"]
                    score = r.get("relevance_score", 0.0)
                    reranked.append((docs[idx], score))
                return reranked
    except Exception as e:
        print(f"Cohere Rerank warning: {type(e).__name__}: {e}")

    # Fallback: return original cosine-scored results
    return documents[:top_k]


@dataclass
class CodeEntity:
    """A function, class, or method extracted from source code."""
    entity_type: str  # "function", "class", "method"
    name: str
    file_path: str
    line_start: int
    line_end: int
    docstring: str = ""
    signature: str = ""
    calls: list[str] = field(default_factory=list)  # functions this entity calls
    decorators: list[str] = field(default_factory=list)
    parent_class: str = ""


class CodeAnalyzer:
    """
    AST-based code analyzer. Instead of just indexing raw text,
    it extracts function/class definitions, their signatures,
    docstrings, and call relationships.
    """

    def __init__(self):
        self._entities: list[CodeEntity] = []
        self._call_graph: dict[str, list[str]] = {}  # function_name → [called_functions]

    def analyze_file(self, file_path: str) -> list[CodeEntity]:
        """Parse a Python file and extract code entities."""
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=file_path)
        except (SyntaxError, UnicodeDecodeError):
            return []

        entities = []
        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                entity = self._extract_function(node, file_path, source_lines)
                entities.append(entity)
                self._entities.append(entity)

            elif isinstance(node, ast.ClassDef):
                entity = self._extract_class(node, file_path, source_lines)
                entities.append(entity)
                self._entities.append(entity)

                # Also extract methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method = self._extract_function(item, file_path, source_lines, parent_class=node.name)
                        entities.append(method)
                        self._entities.append(method)

        # Build call graph
        for entity in entities:
            self._call_graph[entity.name] = entity.calls

        return entities

    def _extract_function(self, node, file_path: str, source_lines: list[str],
                           parent_class: str = "") -> CodeEntity:
        """Extract function/method metadata from AST node."""
        # Build signature
        args = []
        for arg in node.args.args:
            arg_name = arg.arg
            annotation = ""
            if arg.annotation:
                try:
                    annotation = ast.unparse(arg.annotation)
                except Exception:
                    pass
            args.append(f"{arg_name}: {annotation}" if annotation else arg_name)

        signature = f"def {node.name}({', '.join(args)})"

        # Return annotation
        if node.returns:
            try:
                signature += f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass

        # Docstring
        docstring = ast.get_docstring(node) or ""

        # Decorators
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                decorators.append("@unknown")

        # Find function calls within the body
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                try:
                    if isinstance(child.func, ast.Name):
                        calls.append(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        calls.append(child.func.attr)
                except Exception:
                    pass

        return CodeEntity(
            entity_type="method" if parent_class else "function",
            name=node.name,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            docstring=docstring,
            signature=signature,
            calls=list(set(calls)),
            decorators=decorators,
            parent_class=parent_class,
        )

    def _extract_class(self, node: ast.ClassDef, file_path: str, source_lines: list[str]) -> CodeEntity:
        """Extract class metadata from AST node."""
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                pass

        signature = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
        docstring = ast.get_docstring(node) or ""

        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                pass

        return CodeEntity(
            entity_type="class",
            name=node.name,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            docstring=docstring,
            signature=signature,
            decorators=decorators,
        )

    def find_entity(self, name: str) -> list[CodeEntity]:
        """Find entities by name (fuzzy match)."""
        name_lower = name.lower()
        return [
            e for e in self._entities
            if name_lower in e.name.lower() or name_lower in e.signature.lower()
        ]

    def get_callers(self, function_name: str) -> list[str]:
        """Find all functions that CALL the given function."""
        callers = []
        for caller, called_fns in self._call_graph.items():
            if function_name in called_fns:
                callers.append(caller)
        return callers

    def get_callees(self, function_name: str) -> list[str]:
        """Find all functions that ARE CALLED BY the given function."""
        return self._call_graph.get(function_name, [])

    def entity_to_searchable_text(self, entity: CodeEntity) -> str:
        """Convert an entity to a searchable text chunk for the vector store."""
        parts = [
            f"[{entity.entity_type.upper()}] {entity.signature}",
            f"File: {entity.file_path}:{entity.line_start}",
        ]
        if entity.parent_class:
            parts.append(f"Class: {entity.parent_class}")
        if entity.docstring:
            parts.append(f"Docs: {entity.docstring}")
        if entity.calls:
            parts.append(f"Calls: {', '.join(entity.calls[:10])}")
        if entity.decorators:
            parts.append(f"Decorators: {', '.join(entity.decorators)}")
        return "\n".join(parts)

    def get_all_entities(self) -> list[CodeEntity]:
        return self._entities

    def get_summary(self) -> dict:
        """Get a summary of all analyzed code."""
        functions = [e for e in self._entities if e.entity_type == "function"]
        classes = [e for e in self._entities if e.entity_type == "class"]
        methods = [e for e in self._entities if e.entity_type == "method"]
        return {
            "total_entities": len(self._entities),
            "functions": len(functions),
            "classes": len(classes),
            "methods": len(methods),
            "files_analyzed": len(set(e.file_path for e in self._entities)),
        }


# =====================================================================
#  PERSISTENT LONG-TERM MEMORY -- survives restarts
# =====================================================================

class PersistentMemory:
    """
    Long-term episodic memory that persists to disk.
    Stores facts, preferences, and past interactions so AERIS
    remembers things across sessions.
    """

    MEMORY_FILE = Path(__file__).parent / "data" / "long_term_memory.json"

    def __init__(self):
        self._memory: dict = self._load()

    def _load(self) -> dict:
        """Load memory from disk."""
        try:
            if self.MEMORY_FILE.exists():
                return json.loads(self.MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {
            "facts": [],           # [{"fact": str, "category": str, "timestamp": str}]
            "preferences": {},     # {"key": "value"}
            "interaction_stats": {  # aggregate stats
                "total_queries": 0,
                "topics": {},      # {"topic": count}
                "first_interaction": None,
                "last_interaction": None,
            },
            "learned_patterns": [], # [{"pattern": str, "response": str}]
        }

    def _save(self):
        """Persist memory to disk."""
        try:
            self.MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.MEMORY_FILE.write_text(
                json.dumps(self._memory, indent=2, default=str), encoding="utf-8"
            )
        except Exception:
            pass

    def store_fact(self, fact: str, category: str = "general") -> None:
        """Store a fact permanently."""
        # Deduplicate by checking similarity
        for existing in self._memory["facts"]:
            if existing["fact"].lower() == fact.lower():
                return

        self._memory["facts"].append({
            "fact": fact,
            "category": category,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 500 facts
        self._memory["facts"] = self._memory["facts"][-500:]
        self._save()

    def recall_facts(self, query: str = "", category: str = "", limit: int = 10) -> list[dict]:
        """Recall facts, optionally filtered by query or category."""
        facts = self._memory["facts"]
        if category:
            facts = [f for f in facts if f["category"] == category]
        if query:
            q_lower = query.lower()
            facts = [f for f in facts if q_lower in f["fact"].lower()]
        return facts[-limit:]

    def set_preference(self, key: str, value: str) -> None:
        """Store a user preference."""
        self._memory["preferences"][key] = value
        self._save()

    def get_preference(self, key: str, default: str = "") -> str:
        return self._memory["preferences"].get(key, default)

    def get_all_preferences(self) -> dict:
        return dict(self._memory["preferences"])

    def record_interaction(self, query: str) -> None:
        """Record that an interaction happened (for analytics)."""
        stats = self._memory["interaction_stats"]
        stats["total_queries"] = stats.get("total_queries", 0) + 1
        stats["last_interaction"] = datetime.now().isoformat()
        if not stats.get("first_interaction"):
            stats["first_interaction"] = datetime.now().isoformat()

        # Track topic frequency
        words = query.lower().split()
        stop = {"the", "a", "an", "is", "are", "and", "or", "but", "in", "on", "at", "to",
                "for", "of", "what", "how", "why", "can", "do", "i", "you", "me", "my", "please"}
        for w in words:
            if len(w) > 3 and w not in stop:
                stats.setdefault("topics", {})[w] = stats.get("topics", {}).get(w, 0) + 1

        self._save()

    def learn_pattern(self, pattern: str, response: str) -> None:
        """Learn a behavior pattern (e.g., 'user always asks for code in Python')."""
        self._memory["learned_patterns"].append({
            "pattern": pattern,
            "response": response,
            "timestamp": datetime.now().isoformat(),
        })
        self._memory["learned_patterns"] = self._memory["learned_patterns"][-100:]
        self._save()

    def get_summary(self) -> dict:
        """Get a summary of long-term memory."""
        stats = self._memory["interaction_stats"]
        top_topics = sorted(
            stats.get("topics", {}).items(),
            key=lambda x: x[1], reverse=True
        )[:10]
        return {
            "total_facts": len(self._memory["facts"]),
            "total_preferences": len(self._memory["preferences"]),
            "total_interactions": stats.get("total_queries", 0),
            "first_interaction": stats.get("first_interaction"),
            "last_interaction": stats.get("last_interaction"),
            "top_topics": top_topics,
            "learned_patterns": len(self._memory["learned_patterns"]),
        }


# =====================================================================
#  FILE INDEXER -- crawls workspace and indexes files into VectorStore
# =====================================================================

INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".rs", ".go", ".java", ".c", ".cpp", ".h",
    ".sh", ".bat", ".ps1", ".cfg", ".ini", ".env",
}

SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build", ".next"}


class FileIndexer:
    """Indexes local files for RAG retrieval with AST-awareness."""

    def __init__(self, store: VectorStore, code_analyzer: CodeAnalyzer | None = None) -> None:
        self.store = store
        self.code_analyzer = code_analyzer or CodeAnalyzer()
        self._indexed_paths: set[str] = set()

    def index_directory(self, directory: str, max_files: int = 500, chunk_size: int = 800) -> dict:
        root = Path(directory).resolve()
        indexed = 0
        skipped = 0
        code_entities_indexed = 0

        for fpath in root.rglob("*"):
            if indexed >= max_files:
                break
            if not fpath.is_file():
                continue
            if any(skip in fpath.parts for skip in SKIP_DIRS):
                skipped += 1
                continue
            if fpath.suffix.lower() not in INDEXABLE_EXTENSIONS:
                skipped += 1
                continue
            if str(fpath) in self._indexed_paths:
                skipped += 1
                continue
            if fpath.stat().st_size > 1_000_000:  # Skip files > 1MB
                skipped += 1
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")

                # AST-aware indexing for Python files
                if fpath.suffix == ".py":
                    entities = self.code_analyzer.analyze_file(str(fpath))
                    for entity in entities:
                        searchable = self.code_analyzer.entity_to_searchable_text(entity)
                        self.store.add(
                            source=f"{fpath}:{entity.line_start}",
                            content=searchable,
                            metadata={
                                "extension": fpath.suffix,
                                "name": entity.name,
                                "entity_type": entity.entity_type,
                                "has_docstring": bool(entity.docstring),
                            },
                        )
                        code_entities_indexed += 1

                # Also do regular chunked indexing for all files
                chunks = self._chunk_text(content, chunk_size)
                for chunk in chunks:
                    if chunk.strip():
                        self.store.add(
                            source=str(fpath),
                            content=chunk,
                            metadata={"extension": fpath.suffix, "name": fpath.name},
                        )
                self._indexed_paths.add(str(fpath))
                indexed += 1
            except Exception:
                skipped += 1

        return {
            "indexed_files": indexed,
            "skipped": skipped,
            "total_chunks": self.store.count(),
            "code_entities": code_entities_indexed,
            "ast_summary": self.code_analyzer.get_summary(),
            "directory": str(root),
        }

    def _chunk_text(self, text: str, chunk_size: int) -> list[str]:
        lines = text.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for line in lines:
            current.append(line)
            current_len += len(line) + 1
            if current_len >= chunk_size:
                chunks.append("\n".join(current))
                current = []
                current_len = 0

        if current:
            chunks.append("\n".join(current))
        return chunks


# =====================================================================
#  CONVERSATION MEMORY -- sliding context window
# =====================================================================

@dataclass
class MemoryEntry:
    role: str         # "user" | "assistant" | "system"
    content: str
    timestamp: str
    intent: str = ""
    tool_used: str = ""
    rag_context: str = ""


class ConversationMemory:
    """Sliding window conversation memory with RAG context injection."""

    def __init__(self, max_entries: int = 50) -> None:
        self.entries: list[MemoryEntry] = []
        self.max_entries = max_entries

    def add(self, role: str, content: str, intent: str = "", tool_used: str = "", rag_context: str = "") -> None:
        self.entries.append(MemoryEntry(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            intent=intent,
            tool_used=tool_used,
            rag_context=rag_context,
        ))
        # Compact if too large
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def get_context_window(self, last_n: int = 10) -> list[dict]:
        window = self.entries[-last_n:]
        return [
            {"role": e.role, "content": e.content, "intent": e.intent, "tool": e.tool_used}
            for e in window
        ]

    def get_full_context_string(self, last_n: int = 10) -> str:
        window = self.entries[-last_n:]
        lines = []
        for e in window:
            prefix = "User" if e.role == "user" else "AERIS"
            lines.append(f"[{prefix}] {e.content}")
            if e.rag_context:
                lines.append(f"  [Context] {e.rag_context[:200]}")
        return "\n".join(lines)

    def search_memory(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        query_lower = query.lower()
        scored = []
        for entry in self.entries:
            score = sum(1 for word in query_lower.split() if word in entry.content.lower())
            if score > 0:
                scored.append((entry, score))
        scored.sort(key=lambda x: -x[1])
        return [e for e, _ in scored[:limit]]


# =====================================================================
#  RAG VOICE ENGINE -- the agentic brain
# =====================================================================

@dataclass
class RAGVoiceResponse:
    transcript: str
    intent: str
    response: str
    rag_sources: list[str]
    confidence: float
    action_taken: str
    tool_used: Optional[str] = None
    context_used: bool = False

    def to_dict(self) -> dict:
        return {
            "transcript": self.transcript,
            "intent": self.intent,
            "response": self.response,
            "rag_sources": self.rag_sources,
            "confidence": self.confidence,
            "action_taken": self.action_taken,
            "tool_used": self.tool_used,
            "context_used": self.context_used,
        }


class RAGVoiceEngine:
    """
    Advanced agentic RAG voice engine that:
    1. Indexes local workspace files for semantic search (with AST awareness)
    2. Maintains conversation memory + persistent long-term memory
    3. Retrieves relevant context before responding
    4. Makes agentic decisions (execute tools, search files, generate code)
    5. Provides context-aware voice responses
    """

    def __init__(self, workspace: str | None = None) -> None:
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.vector_store = VectorStore()
        self.code_analyzer = CodeAnalyzer()
        self.indexer = FileIndexer(self.vector_store, self.code_analyzer)
        self.memory = ConversationMemory()
        self.long_term_memory = PersistentMemory()
        self._indexed = False

    def ensure_indexed(self, max_files: int = 300) -> dict:
        """Index workspace if not already done."""
        if not self._indexed:
            result = self.indexer.index_directory(str(self.workspace), max_files=max_files)
            self._indexed = True
            return result
        return {"indexed_files": 0, "total_chunks": self.vector_store.count(), "status": "already_indexed"}

    async def process(self, transcript: str) -> RAGVoiceResponse:
        """
        Full agentic RAG pipeline:
          1. Classify intent
          2. Retrieve relevant context from indexed files
          3. Check conversation memory for continuity
          4. Decide action
          5. Generate response
        """
        # Ensure workspace is indexed
        self.ensure_indexed()

        # Record in long-term memory
        self.long_term_memory.record_interaction(transcript)

        # 1. Classify intent
        intent, confidence = self._classify(transcript)

        # 2. NLP Preprocessing: Extract core semantic entities
        rag_query = _extract_keywords(transcript)

        # 3. RAG retrieval using NLTK-optimized query
        rag_results = self.vector_store.search(rag_query, top_k=3)
        rag_sources = [doc.source for doc, score in rag_results if score > 0.1]
        rag_context = "\n".join(
            f"[{doc.source}]: {doc.content[:300]}"
            for doc, score in rag_results
            if score > 0.1
        )

        # 3b. Check for code-specific questions → use AST entities
        if intent == "code_question":
            code_entities = self.code_analyzer.find_entity(rag_query)
            if code_entities:
                entity_info = []
                for e in code_entities[:3]:
                    entity_info.append(self.code_analyzer.entity_to_searchable_text(e))
                    # Also show what calls it and what it calls
                    callers = self.code_analyzer.get_callers(e.name)
                    callees = self.code_analyzer.get_callees(e.name)
                    if callers:
                        entity_info.append(f"Called by: {', '.join(callers[:5])}")
                    if callees:
                        entity_info.append(f"Calls: {', '.join(callees[:5])}")
                rag_context = "\n\n".join(entity_info) + "\n\n" + rag_context

        # 3c. Inject long-term memory context
        ltm_facts = self.long_term_memory.recall_facts(rag_query, limit=3)
        if ltm_facts:
            ltm_context = "\n".join(f"[Memory] {f['fact']}" for f in ltm_facts)
            rag_context = ltm_context + "\n" + rag_context

        # 4. Check memory for conversation continuity
        memory_context = self.memory.get_full_context_string(last_n=5)

        # 5. Decide action + generate response
        response, action, tool_used = self._decide_and_respond(
            transcript, intent, rag_context, memory_context
        )

        # 6. Store in memory
        self.memory.add(
            role="user", content=transcript, intent=intent, rag_context=rag_context[:200],
        )
        self.memory.add(
            role="assistant", content=response, intent=intent, tool_used=tool_used or "",
        )

        return RAGVoiceResponse(
            transcript=transcript,
            intent=intent,
            response=response,
            rag_sources=rag_sources[:5],
            confidence=confidence,
            action_taken=action,
            tool_used=tool_used,
            context_used=bool(rag_context),
        )

    def _classify(self, text: str) -> tuple[str, float]:
        lowered = text.lower()
        intent_map = {
            "code_question": ["how does", "what is", "explain", "show me", "where is", "find the", "what does"],
            "file_search": ["find file", "search for", "locate", "where is the file"],
            "code_generation": ["create", "generate", "build", "make", "write code", "scaffold"],
            "file_operation": ["read", "write", "edit", "delete", "open file"],
            "system_action": ["run", "execute", "install", "start", "stop", "restart"],
            "research": ["research", "investigate", "analyze", "summarize", "compare"],
            "conversion": ["convert", "transform", "export", "change format"],
            "organize": ["organize", "clean up", "sort", "tidy", "arrange"],
        }

        best = "chat"
        best_score = 0
        for intent, keywords in intent_map.items():
            score = sum(1 for kw in keywords if kw in lowered)
            if score > best_score:
                best_score = score
                best = intent
        confidence = min(best_score / 2.0, 1.0) if best_score > 0 else 0.3
        return best, confidence

    def _decide_and_respond(
        self, transcript: str, intent: str, rag_context: str, memory_context: str
    ) -> tuple[str, str, Optional[str]]:
        """Agentic decision-making: what to do and what to say."""

        if intent == "code_question" and rag_context:
            # Answer from indexed codebase
            snippet = rag_context[:500]
            response = f"Based on your codebase, here's what I found:\n\n{snippet}\n\nWould you like me to explain further?"
            return response, "rag_answer", None

        elif intent == "file_search":
            response = "I'll search your workspace for that. Let me check the indexed files."
            return response, "file_search", "grep_search"

        elif intent == "code_generation":
            response = (
                f"I'll generate that for you. Based on the context I have from your project, "
                f"I can create the code and write it to your workspace."
            )
            return response, "code_gen", "write_file"

        elif intent == "conversion":
            response = "I can handle that conversion. Let me use the appropriate tool from the forge."
            return response, "conversion", "tool_forge"

        elif intent == "file_operation":
            response = "I'll handle that file operation for you."
            return response, "file_op", "file_tools"

        elif intent == "system_action":
            response = "Executing that system action now."
            return response, "system_exec", "bash"

        elif intent == "research":
            response = "I'll start researching that topic. This will run as a background task so you can continue working."
            return response, "research", "deep_research"

        elif intent == "organize":
            response = "I'll organize those files for you. Let me scan the directory."
            return response, "organize", "file_organizer"

        else:
            # Conversational with context awareness
            if rag_context:
                response = f"I found some relevant context in your project that might help. What specifically would you like to know?"
                return response, "contextual_chat", None
            else:
                response = f"I understand. How can I help you with that?"
                return response, "chat", None

    def get_stats(self) -> dict:
        return {
            "indexed_chunks": self.vector_store.count(),
            "indexed_files": len(self.indexer._indexed_paths),
            "memory_entries": len(self.memory.entries),
            "workspace": str(self.workspace),
            "code_entities": self.code_analyzer.get_summary(),
            "long_term_memory": self.long_term_memory.get_summary(),
        }

    def search_knowledge(self, query: str, top_k: int = 5) -> list[dict]:
        rag_query = _extract_keywords(query)
        results = self.vector_store.search(rag_query, top_k)
        return [
            {
                "source": doc.source,
                "content": doc.content[:300],
                "score": round(score, 4),
                "metadata": doc.metadata,
                "extracted_entities": rag_query,
            }
            for doc, score in results
        ]

    def search_code(self, query: str) -> list[dict]:
        """Search code entities by name or description."""
        entities = self.code_analyzer.find_entity(query)
        return [
            {
                "name": e.name,
                "type": e.entity_type,
                "file": e.file_path,
                "line": e.line_start,
                "signature": e.signature,
                "docstring": e.docstring[:200],
                "calls": e.calls[:10],
                "callers": self.code_analyzer.get_callers(e.name)[:5],
            }
            for e in entities[:10]
        ]
