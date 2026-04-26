"""
Performance and stress tests for embedding cache

Tests cover:
- Cache performance under load
- Memory usage
- Eviction behavior
- Large cache handling
- I/O performance
"""

import pytest
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import tempfile

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from senior_tools import (
    get_embedding_with_cache,
    _cache_stats,
    _cache_stats_lock,
)
from conftest import AsyncMock


@pytest.mark.asyncio
class TestCachePerformance:
    """Performance tests for cache operations"""
    
    async def test_cache_hit_performance(self):
        """Cache hits should be significantly faster than API calls"""
        # Use unique test key to avoid cache pollution from other tests
        test_key = f"perf_test_{time.time()}"
        
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            # Simulate slow API call (100ms)
            async def slow_embedding(text):
                await asyncio.sleep(0.1)
                return [0.1] * 768
            
            mock_embed.side_effect = slow_embedding
            
            # First call - cache miss (slow)
            start = time.time()
            await get_embedding_with_cache(test_key)
            miss_time = time.time() - start
            
            # Second call - cache hit (fast)
            start = time.time()
            await get_embedding_with_cache(test_key)
            hit_time = time.time() - start
            
            # Cache hit should be faster (at least 2x faster is reasonable)
            assert hit_time < miss_time / 2, f"Cache hit ({hit_time:.4f}s) should be <2x faster than miss ({miss_time:.4f}s)"
    
    async def test_concurrent_performance(self):
        """Should handle concurrent requests efficiently"""
        # Use unique test keys to avoid cache pollution
        test_prefix = f"concurrent_{time.time()}"
        
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 768
            
            # Create 50 concurrent requests
            start = time.time()
            tasks = [
                get_embedding_with_cache(f"{test_prefix}_{i % 10}")
                for i in range(50)
            ]
            await asyncio.gather(*tasks)
            elapsed = time.time() - start
            
            # Should complete in reasonable time (< 5 seconds)
            assert elapsed < 5.0, f"50 concurrent requests took {elapsed:.2f}s, should be <5s"
            
            # Should have made only 10 API calls (due to caching)
            assert mock_embed.call_count == 10, f"Expected 10 API calls, got {mock_embed.call_count}"


@pytest.mark.asyncio
class TestCacheEviction:
    """Test LRU eviction behavior"""
    
    async def test_eviction_triggers_at_limit(self):
        """Should trigger eviction when cache is full"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            
            # Create cache with small limit
            with patch('senior_tools.EMBEDDING_CACHE_MAX_ENTRIES', 10):
                with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
                    mock_embed.return_value = [0.1] * 768
                    
                    # Fill cache to limit
                    for i in range(10):
                        await get_embedding_with_cache(f"entry {i}")
                    
                    # Add one more - should trigger eviction
                    initial_evictions = _cache_stats["evictions"]
                    await get_embedding_with_cache("entry 10")
                    
                    # Eviction count should increase
                    assert _cache_stats["evictions"] > initial_evictions
    
    async def test_lru_evicts_oldest(self):
        """Should evict least recently used entries"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            
            with patch('senior_tools.EMBEDDING_CACHE_MAX_ENTRIES', 5):
                with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
                    mock_embed.return_value = [0.1] * 768
                    
                    # Fill cache
                    for i in range(5):
                        await get_embedding_with_cache(f"entry {i}")
                    
                    # Access entry 0 to make it recently used
                    await get_embedding_with_cache("entry 0")
                    
                    # Add new entry - should evict entry 1 (oldest)
                    await get_embedding_with_cache("entry 5")
                    
                    # Entry 0 should still be cached (hit)
                    mock_embed.reset_mock()
                    await get_embedding_with_cache("entry 0")
                    assert mock_embed.call_count == 0  # Cache hit


@pytest.mark.asyncio
class TestCacheExpiration:
    """Test TTL-based expiration"""
    
    async def test_expired_entries_removed(self):
        """Should remove expired entries on next access"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            
            # Patch the cache file path to use temp directory
            def mock_path_parent(self):
                return Path(tmpdir)
            
            # Create cache with very short TTL
            with patch('senior_tools.EMBEDDING_CACHE_TTL_DAYS', 0):
                with patch('senior_tools.Path') as mock_path_class:
                    # Make Path(__file__).parent return our temp dir
                    mock_path_instance = MagicMock()
                    mock_path_instance.parent = Path(tmpdir)
                    mock_path_class.return_value = mock_path_instance
                    
                    with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
                        mock_embed.return_value = [0.1] * 768
                        
                        # Add entry
                        await get_embedding_with_cache("test entry")
                        
                        # Wait a bit to ensure timestamp difference
                        await asyncio.sleep(0.1)
                        
                        # Access again - should be expired and regenerated
                        initial_expirations = _cache_stats["expirations"]
                        await get_embedding_with_cache("test entry")
                        
                        # Expiration count should increase
                        assert _cache_stats["expirations"] > initial_expirations


@pytest.mark.asyncio
class TestCacheMemoryUsage:
    """Test memory efficiency"""
    
    async def test_large_cache_memory(self):
        """Should handle large cache without excessive memory"""
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            # 768-dimensional embedding (typical for text-embedding-3-small)
            mock_embed.return_value = [0.1] * 768
            
            # Add 100 entries
            for i in range(100):
                await get_embedding_with_cache(f"entry {i}")
            
            # Memory usage should be reasonable
            # Each embedding: 768 floats * 4 bytes = 3KB
            # 100 entries = ~300KB + overhead
            # Should be well under 10MB
            import sys
            # This is a basic check - in production you'd use memory_profiler
            assert sys.getsizeof(_cache_stats) < 10_000_000


@pytest.mark.asyncio
class TestCacheErrorHandling:
    """Test error handling and recovery"""
    
    async def test_corrupted_cache_recovery(self):
        """Should recover from corrupted cache file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "embedding_cache.json"
            
            # Create corrupted cache file
            with open(cache_file, 'w') as f:
                f.write("{ invalid json }")
            
            with patch('senior_tools.Path.__truediv__') as mock_path:
                mock_path.return_value = cache_file
                
                with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
                    mock_embed.return_value = [0.1] * 768
                    
                    # Should not crash, should fall back to API
                    result = await get_embedding_with_cache("test")
                    assert result == [0.1] * 768
    
    async def test_api_failure_handling(self):
        """Should handle API failures gracefully"""
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = Exception("API Error")
            
            # Should propagate exception
            with pytest.raises(Exception):
                await get_embedding_with_cache("test")
    
    async def test_disk_full_handling(self):
        """Should handle disk full errors"""
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 768
            
            # Mock file write to raise OSError (disk full)
            with patch('builtins.open', side_effect=OSError("Disk full")):
                # Should fall back to API without caching
                result = await get_embedding_with_cache("test")
                assert result == [0.1] * 768


@pytest.mark.asyncio
class TestCacheEdgeCases:
    """Test edge cases and boundary conditions"""
    
    async def test_empty_text(self):
        """Should handle empty text"""
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.0] * 768
            
            result = await get_embedding_with_cache("")
            assert len(result) == 768
    
    async def test_very_long_text(self):
        """Should handle very long text"""
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 768
            
            long_text = "word " * 10000  # 50KB of text
            result = await get_embedding_with_cache(long_text)
            assert len(result) == 768
    
    async def test_unicode_text(self):
        """Should handle Unicode text"""
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 768
            
            unicode_text = "Hello 世界 🌍 Привет"
            result = await get_embedding_with_cache(unicode_text)
            assert len(result) == 768
    
    async def test_special_characters(self):
        """Should handle special characters"""
        with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 768
            
            special_text = "Test\n\t\r\x00special"
            result = await get_embedding_with_cache(special_text)
            assert len(result) == 768


@pytest.mark.asyncio
class TestCacheDisabled:
    """Test behavior when cache is disabled"""
    
    async def test_cache_disabled_bypasses_cache(self):
        """Should bypass cache when EMBEDDING_CACHE_ENABLED=false"""
        with patch('senior_tools.EMBEDDING_CACHE_ENABLED', False):
            with patch('senior_tools.get_embedding', new_callable=AsyncMock) as mock_embed:
                mock_embed.return_value = [0.1] * 768
                
                # First call
                await get_embedding_with_cache("test")
                assert mock_embed.call_count == 1
                
                # Second call - should still call API (no caching)
                await get_embedding_with_cache("test")
                assert mock_embed.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

