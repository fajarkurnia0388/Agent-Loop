"""
Pytest configuration for simple_answer tests.

This module handles COM initialization on Windows to prevent threading mode conflicts
between pytest and pywinauto/comtypes.

The issue: pytest-asyncio initializes COM with APARTMENTTHREADED mode, but pywinauto/comtypes
requires MULTITHREADED mode. Windows COM doesn't allow changing threading model after initialization.

Solution: Run these tests directly with Python instead of pytest when COM conflicts occur.
"""

import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication
from unittest.mock import Mock


# Set environment variable to prevent comtypes from auto-initializing COM
# This MUST happen before any imports of comtypes or pywinauto
os.environ.setdefault('COMTYPES_NO_COINIT', '1')


class AsyncMock(Mock):
    """Helper for mocking async functions in tests.
    
    This centralizes the AsyncMock implementation to avoid duplication across test files.
    Used for mocking FastMCP Context methods and other async functions.
    """
    async def __call__(self, *args, **kwargs):
        # Handle side_effect properly for async functions
        if self.side_effect is not None:
            if callable(self.side_effect):
                result = self.side_effect(*args, **kwargs)
                # If side_effect is an async function, await it
                if hasattr(result, '__await__'):
                    return await result
                return result
            else:
                # If side_effect is an exception or iterable, let parent handle it
                return super(AsyncMock, self).__call__(*args, **kwargs)
        return super(AsyncMock, self).__call__(*args, **kwargs)


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for Qt widget tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def pytest_collection_modifyitems(config, items):
    """
    Mark tests that require pywinauto/COM or macOS frameworks with custom markers.
    
    Windows: Tests requiring pywinauto/COM will be skipped due to COM threading conflicts
    with pytest-asyncio plugin.
    
    Windows: macOS-specific tests will be skipped since they require macOS frameworks.
    """
    if sys.platform.startswith("win"):
        skip_cursor_marker = pytest.mark.skip(
            reason="COM threading conflict with pytest-asyncio. "
                   "Run this test directly with Python: "
                   "python tests/test_cursor_performance_auto.py"
        )
        
        skip_macos_marker = pytest.mark.skip(
            reason="macOS-specific test requiring Cocoa/Quartz frameworks. "
                   "Only runs on macOS platform."
        )
        
        for item in items:
            # Skip cursor performance tests that use pywinauto
            if "cursor_performance" in str(item.fspath):
                item.add_marker(skip_cursor_marker)
            
            # Skip macOS-specific tests on Windows
            if "macos_cursor_focus" in str(item.fspath):
                item.add_marker(skip_macos_marker)

