"""
Test logging path resolution to ensure logs are saved in MCP server directory
regardless of the current working directory when the MCP server is invoked.
"""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add parent directory to path to import senior_tools
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_logging_uses_absolute_path():
    """Test that logging configuration uses absolute path based on module location"""
    import senior_tools
    import logging

    # Get the expected log directory (should be in MCP server directory)
    expected_mcp_server_dir = Path(senior_tools.__file__).parent.absolute()
    expected_log_dir = expected_mcp_server_dir / "logs"
    expected_log_file = expected_log_dir / "senior_tools.log"

    # Get the root logger (where handlers are attached)
    root_logger = logging.getLogger()

    # Check that at least one handler is a FileHandler
    file_handlers = [h for h in root_logger.handlers if hasattr(h, 'baseFilename')]
    assert len(file_handlers) > 0, "No FileHandler found in root logger"

    # Find the senior_tools.log handler (there may be multiple handlers from different modules)
    senior_tools_handler = None
    for handler in file_handlers:
        handler_path = Path(handler.baseFilename)
        if handler_path.name == "senior_tools.log":
            senior_tools_handler = handler
            break

    assert senior_tools_handler is not None, "senior_tools.log FileHandler not found"

    # Get the actual log file path from the FileHandler
    actual_log_file = Path(senior_tools_handler.baseFilename)

    # Verify it matches the expected path
    assert actual_log_file == expected_log_file, \
        f"Log file path mismatch: expected {expected_log_file}, got {actual_log_file}"

    # Verify the log file exists
    assert expected_log_file.exists(), f"Log file does not exist: {expected_log_file}"

    print(f"✓ Logging correctly configured to: {actual_log_file}")


def test_logging_independent_of_cwd():
    """Test that logging works correctly regardless of current working directory"""
    import senior_tools
    import logging

    # Save original CWD
    original_cwd = Path.cwd()

    # Create a temporary directory (don't use context manager to avoid Windows file locking issues)
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    try:
        os.chdir(temp_path)

        # Verify we're in a different directory
        assert Path.cwd() == temp_path
        assert Path.cwd() != Path(senior_tools.__file__).parent

        # Get the log file path from the root logger
        root_logger = logging.getLogger()
        file_handlers = [h for h in root_logger.handlers if hasattr(h, 'baseFilename')]

        # Find the senior_tools.log handler
        senior_tools_handler = None
        for handler in file_handlers:
            handler_path = Path(handler.baseFilename)
            if handler_path.name == "senior_tools.log":
                senior_tools_handler = handler
                break

        assert senior_tools_handler is not None, "senior_tools.log FileHandler not found"
        actual_log_file = Path(senior_tools_handler.baseFilename)

        # Verify the log file is still in the MCP server directory, not the temp directory
        expected_mcp_server_dir = Path(senior_tools.__file__).parent.absolute()
        assert actual_log_file.parent.parent == expected_mcp_server_dir, \
            f"Log file should be in MCP server directory {expected_mcp_server_dir}, not {actual_log_file.parent.parent}"

        # Write a test log message
        test_message = f"Test log from CWD: {temp_path}"
        senior_tools.logger.info(test_message)

        # Verify the log was written to the correct file
        assert actual_log_file.exists(), f"Log file does not exist: {actual_log_file}"

        # Read the log file and verify our message is there
        with open(actual_log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
            assert test_message in log_content, "Test message not found in log file"

        print(f"✓ Logging works correctly from different CWD: {temp_path}")
        print(f"✓ Log file correctly saved to: {actual_log_file}")

    finally:
        # Restore original CWD
        os.chdir(original_cwd)
        # Clean up temp directory (ignore errors on Windows)
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def test_env_file_uses_absolute_path():
    """Test that .env file loading uses absolute path based on module location"""
    import senior_tools
    
    # Get the expected .env file path (should be in MCP server directory)
    expected_mcp_server_dir = Path(senior_tools.__file__).parent.absolute()
    expected_env_file = expected_mcp_server_dir / ".env"
    
    # Verify the _env_file_path variable is set correctly
    assert hasattr(senior_tools, '_env_file_path'), "Module should have _env_file_path variable"
    actual_env_file = senior_tools._env_file_path
    
    assert actual_env_file == expected_env_file, \
        f".env file path mismatch: expected {expected_env_file}, got {actual_env_file}"
    
    print(f"✓ .env file correctly configured to: {actual_env_file}")


def test_focus_cursor_logging_path():
    """Test that focus_cursor module also uses absolute path for logging"""
    try:
        from src import focus_cursor
        
        # Get the expected log directory (should be in src/logs/)
        expected_src_dir = Path(focus_cursor.__file__).parent.absolute()
        expected_log_dir = expected_src_dir / "logs"
        expected_log_file = expected_log_dir / "focus_cursor.log"
        
        # Verify the log file path is constructed correctly
        # The focus_cursor module constructs the path at module level
        import logging
        focus_logger = logging.getLogger('src.focus_cursor')
        
        # Check that at least one handler is a FileHandler
        file_handlers = [h for h in focus_logger.handlers if hasattr(h, 'baseFilename')]
        
        if len(file_handlers) > 0:
            actual_log_file = Path(file_handlers[0].baseFilename)
            
            # Verify it matches the expected path
            assert actual_log_file == expected_log_file, \
                f"focus_cursor log file path mismatch: expected {expected_log_file}, got {actual_log_file}"
            
            print(f"✓ focus_cursor logging correctly configured to: {actual_log_file}")
        else:
            print("⚠ focus_cursor module has no FileHandler (may be expected)")
    
    except ImportError:
        print("⚠ focus_cursor module not available (may be expected on non-Windows systems)")


if __name__ == "__main__":
    print("Testing logging path resolution...")
    print("=" * 80)
    
    test_logging_uses_absolute_path()
    print()
    
    test_logging_independent_of_cwd()
    print()
    
    test_env_file_uses_absolute_path()
    print()
    
    test_focus_cursor_logging_path()
    print()
    
    print("=" * 80)
    print("✅ All logging path tests passed!")

