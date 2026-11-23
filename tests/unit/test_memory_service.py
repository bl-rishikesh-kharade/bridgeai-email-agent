"""Unit tests for the PostgreSQL pgvector MemoryService."""

from unittest.mock import MagicMock, patch
import pytest

from app.services.memory_service import MemoryService


def test_memory_service_disabled_without_db_url():
    """Service safely operates as no-op when DATABASE_URL is not set."""
    mem_service = MemoryService(database_url="")
    assert mem_service.record_turn("user@test.com", "Hello", "Hi there") is False
    assert mem_service.retrieve_relevant_memories("user@test.com", "any query") == []
    assert mem_service.clear_memories("user@test.com") == 0


def test_memory_service_skips_empty_turns():
    """Empty queries or responses are not stored."""
    mem_service = MemoryService(database_url="postgresql://fake:fake@localhost/fake")
    assert mem_service.record_turn("user@test.com", "", "response") is False
    assert mem_service.record_turn("user@test.com", "query", "") is False


@patch("app.services.memory_service.psycopg2.connect")
def test_memory_service_record_and_retrieve_mocked(mock_connect):
    """Verify insertion and cosine similarity retrieval logic."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    mem_service = MemoryService(database_url="postgresql://fake:fake@localhost/fake")
    mem_service.generate_embedding = MagicMock(return_value=[0.1] * 768)

    # Test record_turn
    success = mem_service.record_turn(
        user_email="alex@company.com",
        user_message="Find invoices from Vendor",
        agent_response="Found 2 invoices from Vendor.",
    )
    assert success is True
    assert mock_cur.execute.called

    # Test retrieve_relevant_memories
    mock_cur.fetchall.return_value = [
        ("Find invoices from Vendor", "Found 2 invoices from Vendor.", None, 0.88),
    ]
    results = mem_service.retrieve_relevant_memories("alex@company.com", "vendor invoices")
    assert len(results) == 1
    assert results[0]["similarity"] == 0.88
    assert "invoices" in results[0]["user_message"]


@patch("app.services.memory_service.psycopg2.connect")
def test_memory_service_clear_memories(mock_connect):
    """Verify clearing memories for a specific user."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.rowcount = 5

    mem_service = MemoryService(database_url="postgresql://fake:fake@localhost/fake")
    cleared = mem_service.clear_memories("alex@company.com")
    assert cleared == 5
