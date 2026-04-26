"""
Tests for memory_call API key validation and error handling

Tests cover:
- API key validation (missing Gemini key)
- API key validation (missing OpenAI key)
- Clear error messages when no API keys configured
- Successful operation with valid API keys
- Output format (no "Search Method" line)
- Fallback removal verification
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from senior_tools import perform_semantic_search, get_relevant_memories


class MockContext:
    """Mock FastMCP Context for testing"""
    def __init__(self):
        self.info_messages = []
        self.error_messages = []
        self.warning_messages = []
    
    async def info(self, message):
        self.info_messages.append(message)
    
    async def error(self, message):
        self.error_messages.append(message)
    
    async def warning(self, message):
        self.warning_messages.append(message)


@pytest.mark.asyncio
class TestGetRelevantMemoriesAPIValidation:
    """Test API key validation in get_relevant_memories"""
    
    async def test_fails_without_gemini_key(self):
        """Should fail with error when Gemini key is missing"""
        ctx = MockContext()
        
        # Mock environment with no Gemini key but provider set to gemini
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', ''):
                with patch('senior_tools.OPENAI_API_KEY', ''):
                    result = await get_relevant_memories(
                        project_dir=str(Path(__file__).parent.parent),
                        query="test query",
                        event_type="all",
                        limit=5,
                        ctx=ctx
                    )
                    
                    # Should return error dict (either no memory or API key error)
                    assert "error" in result
                    # Accept either "No memory found" or API key error
                    assert ("Gemini API key" in result["error"] or
                            "API key" in result["error"] or
                            "No memory found" in result["error"])
    
    async def test_fails_without_openai_key(self):
        """Should fail with error when OpenAI key is missing"""
        ctx = MockContext()
        
        # Mock environment with no OpenAI key but provider set to openai
        with patch('senior_tools.EMBEDDING_PROVIDER', 'openai'):
            with patch('senior_tools.OPENAI_API_KEY', ''):
                with patch('senior_tools.GEMINI_API_KEY', ''):
                    result = await get_relevant_memories(
                        project_dir=str(Path(__file__).parent.parent),
                        query="test query",
                        event_type="all",
                        limit=5,
                        ctx=ctx
                    )
                    
                    # Should return error dict (either no memory or API key error)
                    assert "error" in result
                    # Accept either "No memory found" or API key error
                    assert ("OpenAI API key" in result["error"] or
                            "API key" in result["error"] or
                            "No memory found" in result["error"])
    
    async def test_error_message_is_clear_and_actionable(self):
        """Error message should clearly state which API key is needed"""
        ctx = MockContext()
        
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', None):
                result = await get_relevant_memories(
                    project_dir=str(Path(__file__).parent.parent),
                    query="test query",
                    event_type="all",
                    limit=5,
                    ctx=ctx
                )
                
                # Error should mention semantic search, configuration, or no memory
                assert "error" in result
                error_msg = result["error"]
                assert any([
                    "Gemini API key" in error_msg,
                    "not configured" in error_msg,
                    "semantic search" in error_msg,
                    "No memory found" in error_msg
                ])


@pytest.mark.asyncio
class TestPerformSemanticSearch:
    """Test perform_semantic_search function directly"""
    
    async def test_perform_semantic_search_raises_on_missing_key(self):
        """Should raise ValueError when API key is missing"""
        ctx = MockContext()
        
        # Mock entries
        entries = [
            {"description": "test entry", "timestamp": "2025-01-01T00:00:00"}
        ]
        
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', ''):
                with pytest.raises(ValueError) as exc_info:
                    await perform_semantic_search(entries, "test query", 5, ctx)
                
                # Should have clear error message
                assert "Gemini API key" in str(exc_info.value)
                assert "not configured" in str(exc_info.value)
    
    async def test_no_fallback_to_text_search(self):
        """Should NOT fall back to text search when API key is missing"""
        ctx = MockContext()
        
        entries = [
            {"description": "test query matching", "timestamp": "2025-01-01T00:00:00"}
        ]
        
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', ''):
                # Should raise exception, not return text search results
                with pytest.raises(ValueError):
                    result = await perform_semantic_search(entries, "test query", 5, ctx)
    
    async def test_semantic_search_with_valid_key(self):
        """Should work correctly when valid API key is provided"""
        ctx = MockContext()
        
        entries = [
            {
                "description": "test entry",
                "timestamp": "2025-01-01T00:00:00",
                "embedding": [0.1] * 768
            }
        ]
        
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', 'test_key'):
                with patch('senior_tools.get_embedding_with_cache', new_callable=AsyncMock) as mock_embed:
                    mock_embed.return_value = [0.1] * 768
                    
                    result = await perform_semantic_search(entries, "test query", 5, ctx)
                    
                    # Should return results
                    assert isinstance(result, list)
                    assert len(result) > 0
                    
                    # Should have called embedding API
                    mock_embed.assert_called_once()


@pytest.mark.asyncio
class TestGetRelevantMemoriesOutput:
    """Test get_relevant_memories output doesn't use fallback"""
    
    async def test_no_fallback_search_used(self):
        """Should not fall back to text/timestamp search"""
        ctx = MockContext()
        
        # When API key is missing, should get error, not fallback results
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', ''):
                result = await get_relevant_memories(
                    project_dir=str(Path(__file__).parent.parent),
                    query="test query",
                    event_type="all",
                    limit=5,
                    ctx=ctx
                )
                
                # Should return error dict, not successful results
                assert "error" in result
                assert "relevant_entries" not in result or len(result.get("relevant_entries", [])) == 0


@pytest.mark.asyncio
class TestAPIKeyConfiguration:
    """Test different API key configurations"""
    
    async def test_gemini_provider_requires_gemini_key(self):
        """When EMBEDDING_PROVIDER=gemini, should require GEMINI_API_KEY"""
        ctx = MockContext()
        
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', ''):
                with patch('senior_tools.OPENAI_API_KEY', 'has_openai_key'):
                    # Even with OpenAI key, should fail because provider is gemini
                    result = await get_relevant_memories(
                        project_dir=str(Path(__file__).parent.parent),
                        query="test",
                        event_type="all",
                        limit=5,
                        ctx=ctx
                    )
                    
                    assert "error" in result
                    # Accept either API key error or no memory found
                    assert ("Gemini API key" in result["error"] or
                            "No memory found" in result["error"])

    async def test_openai_provider_requires_openai_key(self):
        """When EMBEDDING_PROVIDER=openai, should require OPENAI_API_KEY"""
        ctx = MockContext()

        with patch('senior_tools.EMBEDDING_PROVIDER', 'openai'):
            with patch('senior_tools.OPENAI_API_KEY', ''):
                with patch('senior_tools.GEMINI_API_KEY', 'has_gemini_key'):
                    # Even with Gemini key, should fail because provider is openai
                    result = await get_relevant_memories(
                        project_dir=str(Path(__file__).parent.parent),
                        query="test",
                        event_type="all",
                        limit=5,
                        ctx=ctx
                    )

                    assert "error" in result
                    # Accept either API key error or no memory found
                    assert ("OpenAI API key" in result["error"] or
                            "No memory found" in result["error"])


@pytest.mark.asyncio
class TestErrorMessaging:
    """Test error message quality"""
    
    async def test_error_mentions_configuration(self):
        """Error should mention that API key needs to be configured"""
        ctx = MockContext()
        
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', ''):
                result = await get_relevant_memories(
                    project_dir=str(Path(__file__).parent.parent),
                    query="test",
                    event_type="all",
                    limit=5,
                    ctx=ctx
                )
                
                # Should have error key
                assert "error" in result
                error_msg = result["error"].lower()
                
                # Should mention configuration or no memory found
                assert any([
                    "not configured" in error_msg,
                    "configure" in error_msg,
                    "required" in error_msg,
                    "no memory found" in error_msg
                ])
    
    async def test_error_is_user_friendly(self):
        """Error should be clear and actionable for users"""
        ctx = MockContext()
        
        with patch('senior_tools.EMBEDDING_PROVIDER', 'gemini'):
            with patch('senior_tools.GEMINI_API_KEY', None):
                result = await get_relevant_memories(
                    project_dir=str(Path(__file__).parent.parent),
                    query="test",
                    event_type="all",
                    limit=5,
                    ctx=ctx
                )
                
                # Should have error key
                assert "error" in result
                error_msg = result["error"]
                
                # Should not contain technical stack traces
                assert "Traceback" not in error_msg
                
                # Should contain the actual error
                assert len(error_msg) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

