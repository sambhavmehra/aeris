import json
import sqlite3
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import numpy as np

from config import settings

logger = logging.getLogger("aeris.vector_engine")

class VectorMemoryEngine:
    def __init__(self):
        self.db_path = settings.DATA_DIR / "vector_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite database and creates the embeddings table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS embeddings (
                        id TEXT PRIMARY KEY,
                        collection TEXT,
                        text TEXT,
                        metadata TEXT,
                        embedding BLOB,
                        timestamp TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_collection ON embeddings (collection)")
                conn.commit()
            logger.info("Vector database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize vector database: {e}")

    async def get_embedding(self, text: str) -> List[float]:
        """Generates embedding vector (768 dimensions) via Gemini client."""
        if not settings.has_gemini:
            raise RuntimeError("Gemini API key is not configured; cannot generate embeddings.")

        from google import genai
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = await client.aio.models.embed_content(
                model="models/gemini-embedding-2",
                contents=text
            )
            if not response.embeddings:
                raise ValueError("Empty embedding returned from Gemini API")
            return response.embeddings[0].values
        except Exception as e:
            logger.error(f"Gemini embedding API call failed: {e}")
            raise
        finally:
            try:
                if 'client' in locals() and hasattr(client, "_api_client") and hasattr(client._api_client, "_async_httpx_client"):
                    async_client = client._api_client._async_httpx_client
                    if async_client:
                        await async_client.aclose()
            except Exception as e:
                logger.warning(f"Failed to close internal async client: {e}")

    async def add_vector(self, collection: str, text: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """Generates embedding for a piece of text and stores it in the database."""
        if not text or not text.strip():
            return None

        # Clean text
        text = text.strip()
        vector_id = f"vec_{hash(text) & 0xffffffff}_{int(time.time())}"

        try:
            embedding = await self.get_embedding(text)
            embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
            metadata_str = json.dumps(metadata) if metadata else None
            timestamp = datetime.now(timezone.utc).isoformat()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO embeddings (id, collection, text, metadata, embedding, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (vector_id, collection, text, metadata_str, embedding_blob, timestamp))
                conn.commit()
            
            logger.debug(f"Stored vector for text: '{text[:40]}...' in collection '{collection}'")
            return vector_id
        except Exception as e:
            logger.error(f"Failed to store vector for '{text[:40]}...': {e}")
            return None

    def delete_vector_by_text(self, collection: str, text: str) -> bool:
        """Deletes a vector from the database by matching text content."""
        if not text:
            return False
        text_clean = text.strip()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM embeddings WHERE collection = ? AND text = ?",
                    (collection, text_clean)
                )
                deleted = cursor.rowcount > 0
                conn.commit()
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete vector matching text: {e}")
            return False

    def delete_vector_by_id(self, vector_id: str) -> bool:
        """Deletes a vector from the database by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM embeddings WHERE id = ?", (vector_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete vector {vector_id}: {e}")
            return False

    def clear_collection(self, collection: str) -> bool:
        """Clears all vectors in a specific collection."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM embeddings WHERE collection = ?", (collection,))
                conn.commit()
            logger.info(f"Cleared all vectors in collection '{collection}'")
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection '{collection}': {e}")
            return False

    async def search_vectors(self, collection: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Performs semantic search using Cosine Similarity of Gemini Embeddings."""
        if not query or not query.strip():
            return []

        try:
            query_vector = await self.get_embedding(query.strip())
        except Exception as e:
            logger.warning(f"Embedding query failed, falling back: {e}")
            # Raise to let caller trigger legacy matching
            raise

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, text, metadata, embedding FROM embeddings WHERE collection = ?",
                    (collection,)
                )
                rows = cursor.fetchall()
            
            if not rows:
                return []

            ids = []
            texts = []
            metadatas = []
            embeddings = []

            for row in rows:
                ids.append(row[0])
                texts.append(row[1])
                metadatas.append(json.loads(row[2]) if row[2] else {})
                
                # Reconstruct float array
                blob = row[3]
                emb_arr = np.frombuffer(blob, dtype=np.float32)
                embeddings.append(emb_arr)

            # Cosine similarity calculations
            matrix = np.array(embeddings, dtype=np.float32)
            query_arr = np.array(query_vector, dtype=np.float32)

            dot_products = np.dot(matrix, query_arr)
            matrix_norms = np.linalg.norm(matrix, axis=1)
            query_norm = np.linalg.norm(query_arr)

            norms = matrix_norms * query_norm
            norms[norms == 0] = 1e-9  # division guard

            similarities = dot_products / norms

            # Sort indices in descending order
            top_indices = np.argsort(similarities)[::-1][:limit]

            results = []
            for idx in top_indices:
                # Include items above a reasonable threshold or just return top matches
                results.append({
                    "id": ids[idx],
                    "text": texts[idx],
                    "metadata": metadatas[idx],
                    "similarity": float(similarities[idx])
                })
            
            return results
        except Exception as e:
            logger.error(f"Search vectors failed: {e}")
            raise


# Global singleton
_vector_engine: Optional[VectorMemoryEngine] = None

def get_vector_engine() -> VectorMemoryEngine:
    global _vector_engine
    if _vector_engine is None:
        _vector_engine = VectorMemoryEngine()
    return _vector_engine
