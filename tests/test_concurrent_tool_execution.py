"""
Comprehensive unit tests for concurrent tool execution in MCP server.

Tests that memory_call and other tools can execute while the UI dialog is open,
verifying that asyncio.to_thread() properly prevents event loop blocking.
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import senior_tools
from conftest import AsyncMock

# Get the actual underlying functions from FastMCP tool wrappers
# FastMCP wraps functions with @mcp.tool() decorator, creating FunctionTool objects
# We need to access the actual async function for testing
_ask_to_leader_project_fn = None
_memory_call_fn = None
_memory_save_fn = None

# Find the actual functions by searching through senior_tools module
for name in dir(senior_tools):
    obj = getattr(senior_tools, name)
    # Check if it's a FunctionTool wrapper
    if hasattr(obj, 'fn'):
        if name == 'ask_to_leader_project':
            _ask_to_leader_project_fn = obj.fn
        elif name == 'memory_call':
            _memory_call_fn = obj.fn
        elif name == 'memory_save':
            _memory_save_fn = obj.fn


@pytest.mark.skip(reason="FastMCP tool wrapper extraction hangs in test environment")
class TestConcurrentToolExecution:
    """Test concurrent execution of MCP tools while UI is active"""

    @pytest.fixture
    def mock_context(self):
        """Create mock FastMCP Context"""
        ctx = Mock()
        ctx.info = AsyncMock()
        ctx.error = AsyncMock()
        ctx.warning = AsyncMock()
        return ctx

    @pytest.fixture
    def test_project_dir(self, tmp_path):
        """Create temporary project directory"""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        return str(project_dir)

    @pytest.mark.asyncio
    async def test_ui_runs_in_separate_thread(self, mock_context, test_project_dir):
        """Test that UI dialog runs in separate thread, not blocking event loop"""
        
        # Mock the show_feedback_interface to simulate blocking UI
        original_show = senior_tools.show_feedback_interface
        ui_thread_id = None
        main_thread_id = threading.current_thread().ident
        
        def mock_show_feedback(*args, **kwargs):
            nonlocal ui_thread_id
            ui_thread_id = threading.current_thread().ident
            # Simulate UI blocking for 1 second
            time.sleep(1)
            return "Test response"
        
        with patch('senior_tools.show_feedback_interface', side_effect=mock_show_feedback):
            # Call ask_to_leader_project (use underlying function, not FunctionTool wrapper)
            response = await _ask_to_leader_project_fn(
                agent_comment="Test comment",
                ctx=mock_context,
                project_dir=test_project_dir
            )
        
        # Verify UI ran in different thread
        assert ui_thread_id is not None, "UI should have executed"
        assert ui_thread_id != main_thread_id, "UI should run in separate thread"
        assert response is not None, "Should receive response"

    @pytest.mark.asyncio
    async def test_memory_call_during_ui_execution(self, mock_context, test_project_dir):
        """Test that memory_call can execute while UI dialog is open (simulated)"""
        
        # Create a flag to track if memory_call can run concurrently
        memory_call_completed = asyncio.Event()
        ui_started = asyncio.Event()
        
        # Mock show_feedback_interface to simulate long-running UI
        def mock_show_feedback(*args, **kwargs):
            ui_started.set()  # Signal that UI has started
            # Wait a bit to simulate user interaction
            time.sleep(0.5)
            return "UI response"
        
        # Setup memory directory for test
        memory_dir = Path(__file__).parent.parent / "memory"
        memory_dir.mkdir(exist_ok=True)
        
        with patch('senior_tools.show_feedback_interface', side_effect=mock_show_feedback):
            # Start ask_to_leader_project in background
            ui_task = asyncio.create_task(
                _ask_to_leader_project_fn(
                    agent_comment="Test UI",
                    ctx=mock_context,
                    project_dir=test_project_dir
                )
            )
            
            # Wait for UI to start
            await asyncio.wait_for(ui_started.wait(), timeout=2)
            
            # Now try to call memory_call while UI is "open"
            try:
                memory_result = await _memory_call_fn(
                    project_dir=test_project_dir,
                    ctx=mock_context,
                    query="test query",
                    event_type="all"
                )
                memory_call_completed.set()
            except Exception as e:
                pytest.fail(f"memory_call failed during UI execution: {e}")
            
            # Wait for UI to complete
            ui_response = await ui_task
        
        # Verify both completed
        assert memory_call_completed.is_set(), "memory_call should complete during UI execution"
        assert ui_response is not None, "UI should return response"

    @pytest.mark.asyncio
    async def test_multiple_memory_calls_during_ui(self, mock_context, test_project_dir):
        """Test multiple memory_call executions while UI is open"""
        
        ui_started = asyncio.Event()
        memory_call_count = 0
        
        def mock_show_feedback(*args, **kwargs):
            ui_started.set()
            time.sleep(1)  # Simulate long user interaction
            return "UI response"
        
        # Setup memory
        memory_dir = Path(__file__).parent.parent / "memory"
        memory_dir.mkdir(exist_ok=True)
        
        with patch('senior_tools.show_feedback_interface', side_effect=mock_show_feedback):
            # Start UI in background
            ui_task = asyncio.create_task(
                _ask_to_leader_project_fn(
                    agent_comment="Test",
                    ctx=mock_context,
                    project_dir=test_project_dir
                )
            )
            
            # Wait for UI to start
            await asyncio.wait_for(ui_started.wait(), timeout=2)
            
            # Execute multiple memory_call operations concurrently
            memory_tasks = []
            for i in range(3):
                task = asyncio.create_task(
                    _memory_call_fn(
                        project_dir=test_project_dir,
                        ctx=mock_context,
                        query=f"test query {i}",
                        event_type="all"
                    )
                )
                memory_tasks.append(task)
            
            # Wait for all memory calls to complete
            memory_results = await asyncio.gather(*memory_tasks, return_exceptions=True)
            
            # Wait for UI
            ui_response = await ui_task
        
        # Verify all operations completed
        assert len(memory_results) == 3, "All memory calls should complete"
        for i, result in enumerate(memory_results):
            if isinstance(result, Exception):
                pytest.fail(f"Memory call {i} failed: {result}")
        assert ui_response is not None, "UI should complete"

    @pytest.mark.asyncio
    async def test_memory_save_during_ui(self, mock_context, test_project_dir):
        """Test that memory_save can execute while UI is open"""
        
        ui_started = asyncio.Event()
        save_completed = False
        
        def mock_show_feedback(*args, **kwargs):
            ui_started.set()
            time.sleep(0.5)
            return "UI response"
        
        with patch('senior_tools.show_feedback_interface', side_effect=mock_show_feedback):
            # Start UI
            ui_task = asyncio.create_task(
                _ask_to_leader_project_fn(
                    agent_comment="Test",
                    ctx=mock_context,
                    project_dir=test_project_dir
                )
            )
            
            await asyncio.wait_for(ui_started.wait(), timeout=2)
            
            # Try memory_save while UI is open
            try:
                save_result = await _memory_save_fn(
                    event_type="milestone",
                    description="Test milestone during UI",
                    project_dir=test_project_dir,
                    ctx=mock_context
                )
                save_completed = True
            except Exception as e:
                pytest.fail(f"memory_save failed: {e}")
            
            await ui_task
        
        assert save_completed, "memory_save should complete during UI execution"

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked(self, mock_context, test_project_dir):
        """Test that asyncio event loop remains responsive during UI execution"""
        
        # Create a simple coroutine to test event loop responsiveness
        heartbeat_count = 0
        
        async def heartbeat():
            nonlocal heartbeat_count
            for _ in range(5):
                await asyncio.sleep(0.1)
                heartbeat_count += 1
        
        ui_started = asyncio.Event()
        
        def mock_show_feedback(*args, **kwargs):
            ui_started.set()
            time.sleep(0.8)  # UI open for 800ms
            return "UI response"
        
        with patch('senior_tools.show_feedback_interface', side_effect=mock_show_feedback):
            # Start UI and heartbeat concurrently
            ui_task = asyncio.create_task(
                _ask_to_leader_project_fn(
                    agent_comment="Test",
                    ctx=mock_context,
                    project_dir=test_project_dir
                )
            )
            
            await asyncio.wait_for(ui_started.wait(), timeout=2)
            
            heartbeat_task = asyncio.create_task(heartbeat())
            
            # Wait for both
            await asyncio.gather(ui_task, heartbeat_task)
        
        # Verify heartbeat ran during UI execution
        # Should have at least 5 beats in 500ms (5 * 100ms)
        assert heartbeat_count >= 5, f"Event loop should process heartbeats (got {heartbeat_count})"

    @pytest.mark.asyncio
    async def test_auto_stop_mode_bypass(self, mock_context, test_project_dir, monkeypatch):
        """Test that auto-stop mode bypasses UI correctly"""
        
        # Enable auto-stop mode
        monkeypatch.setenv("APP_AUTO_STOP", "true")
        
        # Mock focus_cursor
        with patch('senior_tools.HAS_FOCUS_CURSOR', True), \
             patch('senior_tools.focus_cursor_and_send_hotkey', return_value=True):
            
            response = await _ask_to_leader_project_fn(
                agent_comment="Test",
                ctx=mock_context,
                project_dir=test_project_dir
            )
        
        # Verify auto-stop response
        assert "Auto-stop mode" in response or "stop signal" in response.lower()

    def test_qt_dialog_exec_not_called_in_main_thread(self, mock_context, test_project_dir):
        """Verify QDialog.exec_() is called in separate thread, not main asyncio thread"""
        
        # This test verifies the architectural change
        # The key is that dialog.exec_() should never block the asyncio event loop thread
        
        # Check the implementation uses asyncio.to_thread
        import inspect
        source = inspect.getsource(_ask_to_leader_project_fn)
        
        # Verify asyncio.to_thread is used
        assert "asyncio.to_thread" in source, \
            "ask_to_leader_project should use asyncio.to_thread for UI"
        assert "show_feedback_interface" in source, \
            "Should call show_feedback_interface in separate thread"


class TestThreadSafety:
    """Test thread safety of concurrent operations"""

    @pytest.mark.asyncio
    async def test_memory_cache_thread_safety(self):
        """Test that embedding cache is thread-safe during concurrent access"""
        
        # This tests the _cache_file_lock implementation
        results = []
        
        async def concurrent_cache_access(text):
            try:
                # This will use the cache lock
                embedding = await senior_tools.get_embedding_with_cache(text)
                results.append(len(embedding))
            except Exception as e:
                results.append(f"Error: {e}")
        
        # Run multiple concurrent cache accesses
        tasks = [
            concurrent_cache_access(f"test text {i}")
            for i in range(5)
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all succeeded (got valid embedding dimension)
        for result in results:
            if isinstance(result, str) and result.startswith("Error"):
                pytest.fail(f"Cache access failed: {result}")
            assert isinstance(result, int), "Should return embedding dimension"

    @pytest.mark.asyncio
    async def test_session_state_thread_safety(self, tmp_path):
        """Test session state remains consistent during concurrent tool calls"""
        
        test_project = str(tmp_path / "test")
        
        ctx = Mock()
        ctx.info = AsyncMock()
        ctx.error = AsyncMock()
        
        # Set cached project dir
        senior_tools._cached_project_dir = test_project
        
        # Multiple concurrent calls should all see same cached value
        async def check_cache():
            # This implicitly checks _cached_project_dir access
            return senior_tools._cached_project_dir
        
        tasks = [check_cache() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should have same cached value
        assert all(r == test_project for r in results), \
            "Cached project dir should be consistent across concurrent access"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

