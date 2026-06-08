"""
AERIS Episodic Memory Service
==============================
Provides episodic diagnostic memory by embedding error details and retrieving matching fixes
using the VectorMemoryEngine SQLite/Gemini framework.
"""

import logging
from typing import Optional, Dict, Any
from memory.vector_engine import get_vector_engine

logger = logging.getLogger("aeris.episodic_memory")

async def add_episode(error_msg: str, fix_applied: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Stores an error signature and its resolution in the vector store database.
    """
    if not error_msg or not error_msg.strip():
        return None
    if not fix_applied or not fix_applied.strip():
        return None

    meta = dict(metadata) if metadata else {}
    meta["fix_applied"] = fix_applied

    try:
        engine = get_vector_engine()
        vector_id = await engine.add_vector(
            collection="episodic_errors",
            text=error_msg.strip(),
            metadata=meta
        )
        logger.info(f"[EpisodicMemory] Successfully saved error episode to memory (vector_id={vector_id})")
        return vector_id
    except Exception as e:
        logger.error(f"[EpisodicMemory] Failed to save episode: {e}")
        return None

async def recall_similar_episode(query_error: str, threshold: float = 0.75) -> Optional[Dict[str, Any]]:
    """
    Query-matches past errors using cosine similarity of embeddings.
    If a match is found above the similarity threshold, returns the error/fix dict.
    """
    if not query_error or not query_error.strip():
        return None

    try:
        engine = get_vector_engine()
        results = await engine.search_vectors(
            collection="episodic_errors",
            query=query_error.strip(),
            limit=3
        )
        if not results:
            return None

        # Return the best match if above threshold
        best_match = results[0]
        similarity = best_match.get("similarity", 0.0)
        
        logger.info(f"[EpisodicMemory] Best semantic match similarity: {similarity:.4f} (threshold={threshold})")
        
        if similarity >= threshold:
            metadata = best_match.get("metadata", {})
            return {
                "error_msg": best_match.get("text"),
                "fix_applied": metadata.get("fix_applied", ""),
                "similarity": similarity,
                "metadata": metadata
            }
            
    except Exception as e:
        logger.warning(f"[EpisodicMemory] Embedding or search query failed: {e}. Attempting basic substring fallback.")
        # Substring matching fallback if embeddings/Gemini key are unavailable
        try:
            import sqlite3
            db_path = engine.db_path
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT text, metadata FROM embeddings WHERE collection = 'episodic_errors'"
                )
                rows = cursor.fetchall()
                
            query_lower = query_error.lower()
            best_fallback = None
            max_words_matched = 0
            
            for row in rows:
                text = row["text"]
                text_lower = text.lower()
                # Count overlapping words as a basic similarity heuristic
                query_words = set(query_lower.split())
                text_words = set(text_lower.split())
                overlap = len(query_words.intersection(text_words))
                if overlap > max_words_matched and overlap > 2:
                    max_words_matched = overlap
                    import json
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    best_fallback = {
                        "error_msg": text,
                        "fix_applied": meta.get("fix_applied", ""),
                        "similarity": 0.8,  # Hardcoded fallback similarity
                        "metadata": meta
                    }
            return best_fallback
        except Exception as fallback_err:
            logger.error(f"[EpisodicMemory] Substring fallback also failed: {fallback_err}")
            
    return None
