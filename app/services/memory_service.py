"""Background Long-Term Memory Service using PostgreSQL and pgvector on Neon.tech.

Provides unified relational conversation history + semantic vector search
across sessions without hardcoded queries.
"""

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Any

from app.core.config import settings
from app.core.logger import log_event, logger

try:
    import psycopg2
    from pgvector.psycopg2 import register_vector
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    logger.warning("psycopg2 or pgvector not installed. Background PostgreSQL memory disabled.")

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

EMBEDDING_DIM = 768
EMBEDDING_MODEL = "gemini-embedding-001"


class MemoryService:
    """Manages conversational memory persistence and semantic vector retrieval in PostgreSQL."""

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url if database_url is not None else settings.database_url
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem_worker")
        self._initialized = False
        self._client: Any = None
        if self.database_url and HAS_POSTGRES:
            self._ensure_schema()

    def _get_genai_client(self):
        if self._client is None and HAS_GENAI:
            api_key = settings.gemini_api_key
            self._client = genai.Client(api_key=api_key) if api_key else genai.Client()
        return self._client

    def _get_connection(self):
        if not self.database_url or not HAS_POSTGRES:
            return None
        conn = psycopg2.connect(self.database_url)
        try:
            register_vector(conn)
        except Exception:
            pass
        return conn

    def _ensure_schema(self) -> None:
        """Create extension, tables, and indexes if they do not exist."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS chat_memories (
                            id BIGSERIAL PRIMARY KEY,
                            user_email VARCHAR(255) NOT NULL,
                            role VARCHAR(50) NOT NULL,
                            user_message TEXT,
                            agent_response TEXT,
                            summary TEXT,
                            embedding vector({EMBEDDING_DIM}),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_chat_memories_user_email ON chat_memories(user_email);
                        CREATE INDEX IF NOT EXISTS idx_chat_memories_created_at ON chat_memories(created_at DESC);
                    """)
                conn.commit()
            self._initialized = True
            log_event("memory.schema.initialized", database="neon_pgvector")
        except Exception as exc:
            logger.warning("Could not initialize memory schema in PostgreSQL: %s", exc)

    def generate_embedding(self, text: str) -> list[float] | None:
        """Generate a 768-dimensional embedding vector using Gemini."""
        if not text or not text.strip():
            return None
        client = self._get_genai_client()
        if not client:
            return None
        try:
            res = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text.strip()[:2000],
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
            )
            if res and res.embeddings:
                return res.embeddings[0].values
        except Exception as exc:
            logger.debug("Failed to generate embedding for memory text: %s", exc)
        return None

    def record_turn_async(
        self,
        user_email: str,
        user_message: str,
        agent_response: str,
        summary: str | None = None,
    ) -> None:
        """Enqueue background insertion of conversation turn so user response is instantaneous."""
        if not self.database_url or not HAS_POSTGRES:
            return
        self._executor.submit(
            self.record_turn,
            user_email=user_email,
            user_message=user_message,
            agent_response=agent_response,
            summary=summary,
        )

    def record_turn(
        self,
        user_email: str,
        user_message: str,
        agent_response: str,
        summary: str | None = None,
    ) -> bool:
        """Persist a conversation turn and its semantic embedding."""
        if not self.database_url or not HAS_POSTGRES:
            return False
        clean_user_msg = (user_message or "").strip()
        clean_agent_resp = (agent_response or "").strip()
        if not clean_user_msg or not clean_agent_resp:
            return False

        # Build text to embed: combination of user intent and agent outcome
        content_to_embed = f"User asked: {clean_user_msg}\nAssistant response: {clean_agent_resp[:500]}"
        embedding = self.generate_embedding(content_to_embed)

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO chat_memories
                        (user_email, role, user_message, agent_response, summary, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s);
                        """,
                        (
                            user_email,
                            "turn",
                            clean_user_msg,
                            clean_agent_resp,
                            summary,
                            embedding,
                        ),
                    )
                conn.commit()
            log_event("memory.turn.recorded", user_email=user_email, has_vector=bool(embedding))
            return True
        except Exception as exc:
            logger.warning("Failed to record conversation memory in PostgreSQL: %s", exc)
            return False

    def retrieve_relevant_memories(
        self,
        user_email: str,
        query: str,
        limit: int = 3,
        min_similarity: float = 0.55,
    ) -> list[dict[str, Any]]:
        """Find past memories semantically relevant to the current user query."""
        if not self.database_url or not HAS_POSTGRES or not query or not query.strip():
            return []

        query_vec = self.generate_embedding(query.strip())
        if not query_vec:
            return []

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT user_message, agent_response, summary,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM chat_memories
                        WHERE user_email = %s AND embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT %s;
                        """,
                        (query_vec, user_email, query_vec, limit),
                    )
                    rows = cur.fetchall()

            memories = []
            for row in rows:
                u_msg, a_resp, summ, sim = row
                if sim >= min_similarity:
                    memories.append({
                        "user_message": u_msg,
                        "agent_response": a_resp,
                        "summary": summ,
                        "similarity": float(sim),
                    })
            if memories:
                log_event("memory.retrieved", user_email=user_email, count=len(memories))
            return memories
        except Exception as exc:
            logger.warning("Failed to retrieve memories from PostgreSQL: %s", exc)
            return []

    def clear_memories(self, user_email: str) -> int:
        """Clear long-term memory for a specific user."""
        if not self.database_url or not HAS_POSTGRES:
            return 0
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chat_memories WHERE user_email = %s;", (user_email,))
                    deleted = cur.rowcount
                conn.commit()
            log_event("memory.cleared", user_email=user_email, deleted_count=deleted)
            return deleted
        except Exception as exc:
            logger.warning("Failed to clear memories for %s: %s", user_email, exc)
            return 0


# Default singleton instance
memory_service = MemoryService()
