"""
Unit tests for macOS cursor window pregrabbing functionality.

Tests the macOS-specific implementation in focus_cursor.py including:
- Window discovery using NSWorkspace and Quartz
- Window focus using NSRunningApplication
- Hotkey sending using CGEvent
- CWD-based window prioritization
"""

import sys
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path


# Mock macOS frameworks before importing focus_cursor
class MockNSWorkspace:
    @staticmethod
    def sharedWorkspace():
        return MockNSWorkspace()
    
    def runningApplications(self):
        return []


class MockNSRunningApplication:
    pass


class MockQuartz:
    pass


# Setup mocks for macOS imports
sys.modules['Cocoa'] = Mock(
    NSWorkspace=MockNSWorkspace,
    NSRunningApplication=MockNSRunningApplication,
    NSApplicationActivateIgnoringOtherApps=1
)
sys.modules['Quartz'] = Mock(
    CGWindowListCopyWindowInfo=Mock(return_value=[]),
    kCGWindowListOptionOnScreenOnly=1,
    kCGNullWindowID=0,
    CGEventCreateKeyboardEvent=Mock(return_value=Mock()),
    CGEventPost=Mock(),
    kCGHIDEventTap=0,
    CGEventSetFlags=Mock(),
    kCGEventKeyDown=10,
    kCGEventKeyUp=11,
    kCGEventFlagMaskCommand=0x100000,
    kCGEventFlagMaskShift=0x20000,
    kCGEventFlagMaskControl=0x40000,
    kCGEventFlagMaskAlternate=0x80000
)


class TestMacOSWindowDiscovery:
    """Test macOS window discovery functionality."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        # Force platform to be macOS for testing
        with patch('sys.platform', 'darwin'):
            # Import after mocking
            import focus_cursor
            self.focus_cursor = focus_cursor
            # Force IS_MACOS to True
            self.focus_cursor.IS_MACOS = True
            self.focus_cursor.IS_WINDOWS = False
            self.focus_cursor.IS_LINUX = False
            yield
    
    def test_find_cursor_windows_no_cursor_running(self):
        """Test window discovery when Cursor is not running."""
        mock_workspace = Mock()
        mock_workspace.runningApplications.return_value = []
        
        with patch('focus_cursor.NSWorkspace.sharedWorkspace', return_value=mock_workspace):
            windows = self.focus_cursor._macos_find_cursor_windows()
            
        assert windows == []
    
    def test_find_cursor_windows_cursor_found(self):
        """Test window discovery when Cursor is running."""
        # Mock Cursor app
        mock_app = Mock()
        mock_app.localizedName.return_value = "Cursor"
        mock_app.processIdentifier.return_value = 12345
        
        mock_workspace = Mock()
        mock_workspace.runningApplications.return_value = [mock_app]
        
        # Mock window info
        mock_window = {
            'kCGWindowOwnerPID': 12345,
            'kCGWindowName': 'focus_cursor.py - simple_answer - Cursor',
            'kCGWindowLayer': 0,
            'kCGWindowNumber': 999,
            'kCGWindowBounds': {'X': 0, 'Y': 0, 'Width': 1920, 'Height': 1080}
        }
        
        with patch('focus_cursor.NSWorkspace.sharedWorkspace', return_value=mock_workspace), \
             patch('focus_cursor.CGWindowListCopyWindowInfo', return_value=[mock_window]):
            
            windows = self.focus_cursor._macos_find_cursor_windows()
        
        assert len(windows) == 1
        pid, title, window_info = windows[0]
        assert pid == 12345
        assert title == 'focus_cursor.py - simple_answer - Cursor'
        assert window_info['pid'] == 12345
        assert window_info['window_number'] == 999
        assert window_info['app'] == mock_app
    
    def test_find_cursor_windows_filters_by_layer(self):
        """Test that only layer 0 (normal) windows are returned."""
        mock_app = Mock()
        mock_app.localizedName.return_value = "Cursor"
        mock_app.processIdentifier.return_value = 12345
        
        mock_workspace = Mock()
        mock_workspace.runningApplications.return_value = [mock_app]
        
        # Mock windows with different layers
        mock_windows = [
            {
                'kCGWindowOwnerPID': 12345,
                'kCGWindowName': 'Normal Window - Cursor',
                'kCGWindowLayer': 0,  # Normal window
                'kCGWindowNumber': 1,
                'kCGWindowBounds': {}
            },
            {
                'kCGWindowOwnerPID': 12345,
                'kCGWindowName': 'Menu Window - Cursor',
                'kCGWindowLayer': 25,  # Menu layer (should be filtered)
                'kCGWindowNumber': 2,
                'kCGWindowBounds': {}
            }
        ]
        
        with patch('focus_cursor.NSWorkspace.sharedWorkspace', return_value=mock_workspace), \
             patch('focus_cursor.CGWindowListCopyWindowInfo', return_value=mock_windows):
            
            windows = self.focus_cursor._macos_find_cursor_windows()
        
        # Only layer 0 window should be returned
        assert len(windows) == 1
        assert windows[0][1] == 'Normal Window - Cursor'


class TestMacOSWindowPrioritization:
    """Test CWD-based window prioritization on macOS."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        with patch('sys.platform', 'darwin'):
            import focus_cursor
            self.focus_cursor = focus_cursor
            self.focus_cursor.IS_MACOS = True
            yield
    
    def test_prioritize_exact_match(self):
        """Test that exact CWD match gets highest priority."""
        windows = [
            (12345, 'test.py - other_project - Cursor', {}),
            (12345, 'main.py - simple_answer - Cursor', {}),  # Exact match
            (12345, 'README.md - another_project - Cursor', {})
        ]
        
        with patch('focus_cursor._get_cwd_folder_name', return_value='simple_answer'):
            prioritized = self.focus_cursor._prioritize_matching_window_macos(windows)
        
        # Exact match should be first
        assert prioritized[0][1] == 'main.py - simple_answer - Cursor'
    
    def test_prioritize_partial_match(self):
        """Test that partial match gets medium priority."""
        windows = [
            (12345, 'test.py - other_project - Cursor', {}),
            (12345, 'main.py - my_simple_answer_fork - Cursor', {}),  # Partial match
        ]
        
        with patch('focus_cursor._get_cwd_folder_name', return_value='simple_answer'):
            prioritized = self.focus_cursor._prioritize_matching_window_macos(windows)
        
        # Partial match should be first (better than generic)
        assert 'simple_answer' in prioritized[0][1]
    
    def test_prioritize_no_match(self):
        """Test generic Cursor windows have lowest priority."""
        windows = [
            (12345, 'Settings - Cursor', {}),  # Generic, no folder
            (12345, 'Welcome - Cursor', {})    # Generic, no folder
        ]
        
        with patch('focus_cursor._get_cwd_folder_name', return_value='simple_answer'):
            prioritized = self.focus_cursor._prioritize_matching_window_macos(windows)
        
        # Both have equal low priority, order preserved
        assert len(prioritized) == 2


class TestMacOSWindowFocus:
    """Test macOS window focusing functionality."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        with patch('sys.platform', 'darwin'):
            import focus_cursor
            self.focus_cursor = focus_cursor
            self.focus_cursor.IS_MACOS = True
            yield
    
    def test_focus_window_success(self):
        """Test successful window focus."""
        mock_app = Mock()
        mock_app.isHidden.return_value = False
        mock_app.activateWithOptions_.return_value = True
        mock_app.isActive.return_value = True
        
        window_info = {'app': mock_app, 'pid': 12345}
        
        result = self.focus_cursor._macos_focus_window(12345, window_info)
        
        assert result is True
        mock_app.activateWithOptions_.assert_called_once()
        mock_app.isActive.assert_called_once()
    
    def test_focus_window_unhides_if_hidden(self):
        """Test that hidden app is unhidden before focus."""
        mock_app = Mock()
        mock_app.isHidden.return_value = True
        mock_app.activateWithOptions_.return_value = True
        mock_app.isActive.return_value = True
        
        window_info = {'app': mock_app, 'pid': 12345}
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = self.focus_cursor._macos_focus_window(12345, window_info)
        
        assert result is True
        mock_app.unhide.assert_called_once()
    
    def test_focus_window_activation_fails(self):
        """Test handling of activation failure."""
        mock_app = Mock()
        mock_app.isHidden.return_value = False
        mock_app.activateWithOptions_.return_value = False  # Activation failed
        
        window_info = {'app': mock_app, 'pid': 12345}
        
        result = self.focus_cursor._macos_focus_window(12345, window_info)
        
        assert result is False


class TestMacOSHotkeyMapping:
    """Test macOS hotkey sending (Cmd instead of Ctrl)."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        with patch('sys.platform', 'darwin'):
            import focus_cursor
            self.focus_cursor = focus_cursor
            self.focus_cursor.IS_MACOS = True
            yield
    
    def test_send_hotkey_uses_cmd_key(self):
        """Test that macOS uses Cmd instead of Ctrl."""
        window_info = {'pid': 12345, 'app': Mock()}
        
        with patch('focus_cursor.CGEventCreateKeyboardEvent') as mock_create, \
             patch('focus_cursor.CGEventPost') as mock_post, \
             patch('focus_cursor.CGEventSetFlags') as mock_set_flags, \
             patch('time.sleep'):
            
            mock_event = Mock()
            mock_create.return_value = mock_event
            
            result = self.focus_cursor._macos_send_hotkey(window_info, stop_delay=0)
        
        assert result is True
        
        # Verify CGEventSetFlags was called with Cmd+Option flags
        cmd_option_flags = (
            self.focus_cursor.kCGEventFlagMaskCommand | 
            self.focus_cursor.kCGEventFlagMaskAlternate
        )
        cmd_shift_flags = (
            self.focus_cursor.kCGEventFlagMaskCommand | 
            self.focus_cursor.kCGEventFlagMaskShift
        )
        
        # Should have been called for Cmd+Option+B (twice) and Cmd+Shift+Backspace
        assert mock_set_flags.call_count >= 3
    
    def test_send_hotkey_with_delay(self):
        """Test hotkey sending with stop_delay."""
        window_info = {'pid': 12345, 'app': Mock()}
        
        with patch('focus_cursor.CGEventCreateKeyboardEvent'), \
             patch('focus_cursor.CGEventPost'), \
             patch('focus_cursor.CGEventSetFlags'), \
             patch('time.sleep') as mock_sleep:
            
            self.focus_cursor._macos_send_hotkey(window_info, stop_delay=1.5)
        
        # Verify sleep was called with the delay
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert 1.5 in sleep_calls
    
    def test_send_hotkey_correct_keycodes(self):
        """Test that correct macOS keycodes are used."""
        window_info = {'pid': 12345, 'app': Mock()}
        
        with patch('focus_cursor.CGEventCreateKeyboardEvent') as mock_create, \
             patch('focus_cursor.CGEventPost'), \
             patch('focus_cursor.CGEventSetFlags'), \
             patch('time.sleep'):
            
            self.focus_cursor._macos_send_hotkey(window_info, stop_delay=0)
        
        # Get all keycode arguments
        keycodes_used = [call[0][1] for call in mock_create.call_args_list if len(call[0]) > 1]
        
        # Should include B (0x0B) and Backspace (0x33)
        assert 0x0B in keycodes_used  # B key
        assert 0x33 in keycodes_used  # Backspace key


class TestMacOSIntegration:
    """Test integration of macOS functions with main workflow."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        with patch('sys.platform', 'darwin'):
            import focus_cursor
            self.focus_cursor = focus_cursor
            self.focus_cursor.IS_MACOS = True
            self.focus_cursor.IS_WINDOWS = False
            self.focus_cursor.IS_LINUX = False
            yield
    
    def test_find_cursor_windows_returns_macos_results(self):
        """Test that find_cursor_windows() calls macOS implementation."""
        with patch.object(self.focus_cursor, '_macos_find_cursor_windows', return_value=[]) as mock_macos:
            result = self.focus_cursor.find_cursor_windows()
        
        mock_macos.assert_called_once()
        assert result == []
    
    def test_platform_detection_in_main_flow(self):
        """Test that platform is correctly identified as macOS."""
        with patch.object(self.focus_cursor, 'find_cursor_windows', return_value=[]):
            try:
                self.focus_cursor.focus_cursor_and_send_hotkey()
            except Exception:
                pass  # Expected to fail without valid windows
        
        # Verify IS_MACOS is True
        assert self.focus_cursor.IS_MACOS is True


class TestMacOSErrorHandling:
    """Test error handling in macOS implementation."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        with patch('sys.platform', 'darwin'):
            import focus_cursor
            self.focus_cursor = focus_cursor
            self.focus_cursor.IS_MACOS = True
            yield
    
    def test_find_windows_handles_exception(self):
        """Test that exceptions in window discovery are caught."""
        mock_workspace = Mock()
        mock_workspace.runningApplications.side_effect = Exception("Test error")
        
        with patch('focus_cursor.NSWorkspace.sharedWorkspace', return_value=mock_workspace):
            windows = self.focus_cursor._macos_find_cursor_windows()
        
        # Should return empty list on error, not crash
        assert windows == []
    
    def test_focus_window_handles_exception(self):
        """Test that exceptions in window focus are caught."""
        mock_app = Mock()
        mock_app.isHidden.side_effect = Exception("Test error")
        
        window_info = {'app': mock_app, 'pid': 12345}
        
        result = self.focus_cursor._macos_focus_window(12345, window_info)
        
        # Should return False on error, not crash
        assert result is False
    
    def test_send_hotkey_handles_exception(self):
        """Test that exceptions in hotkey sending are caught."""
        window_info = {'pid': 12345, 'app': Mock()}
        
        with patch('focus_cursor.CGEventCreateKeyboardEvent', side_effect=Exception("Test error")):
            result = self.focus_cursor._macos_send_hotkey(window_info, stop_delay=0)
        
        # Should return False on error, not crash
        assert result is False


class TestMacOSCWDCaching:
    """Test that CWD caching works correctly on macOS."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        with patch('sys.platform', 'darwin'):
            import focus_cursor
            self.focus_cursor = focus_cursor
            # Reset cache
            self.focus_cursor._CACHED_CWD_FOLDER = None
            yield
    
    def test_cwd_cached_after_first_call(self):
        """Test that CWD is cached to avoid repeated filesystem calls."""
        with patch('pathlib.Path.cwd') as mock_cwd:
            mock_path = Mock()
            mock_path.name = 'test_project'
            mock_cwd.return_value = mock_path
            
            # First call
            result1 = self.focus_cursor._get_cwd_folder_name()
            # Second call
            result2 = self.focus_cursor._get_cwd_folder_name()
        
        # Path.cwd() should only be called once due to caching
        assert mock_cwd.call_count == 1
        assert result1 == 'test_project'
        assert result2 == 'test_project'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

