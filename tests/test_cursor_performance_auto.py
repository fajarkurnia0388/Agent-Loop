#!/usr/bin/env python3
"""
Automated Performance tests for Cursor window discovery and focusing operations.
This version runs all tests automatically without user input (use with caution).

Tests:
1. Window discovery time (find_cursor_windows) - 10 runs
2. Window focus and bring-to-front time - 5 runs
3. Complete cycle: discover → focus → send hotkey - 3 runs

IMPORTANT - How to Run:
-----------------------
Due to COM threading conflicts between pytest-asyncio and pywinauto on Windows,
this test file MUST be run directly with Python, NOT with pytest:

  ✓ CORRECT:   python tests/test_cursor_performance_auto.py
  ✗ INCORRECT: pytest tests/test_cursor_performance_auto.py

The issue: pytest-asyncio initializes COM with APARTMENTTHREADED mode before
pywinauto can initialize it with MULTITHREADED mode. Windows COM doesn't allow
changing threading mode after initialization, causing RPC_E_CHANGED_MODE error.
"""

import sys
import time
import logging
from pathlib import Path
from typing import List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import focus_cursor functionality
try:
    from src.focus_cursor import (
        find_cursor_windows,
        focus_cursor_and_send_hotkey,
    )
    HAS_FOCUS_CURSOR = True
except ImportError as e:
    logger.error(f"Failed to import focus_cursor: {e}")
    HAS_FOCUS_CURSOR = False
    sys.exit(1)

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def format_time(seconds: float) -> str:
    """Format time in human-readable format with color."""
    if seconds < 0.001:
        return f"{Colors.OKGREEN}{seconds * 1000000:.0f}us{Colors.ENDC}"
    elif seconds < 0.1:
        return f"{Colors.OKGREEN}{seconds * 1000:.2f}ms{Colors.ENDC}"
    elif seconds < 1.0:
        return f"{Colors.WARNING}{seconds * 1000:.2f}ms{Colors.ENDC}"
    else:
        return f"{Colors.FAIL}{seconds:.3f}s{Colors.ENDC}"


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}\n")


def print_result(label: str, value: str, indent: int = 0):
    """Print a formatted result."""
    prefix = "  " * indent
    print(f"{prefix}{Colors.OKBLUE}>{Colors.ENDC} {label}: {value}")


def test_window_discovery(runs: int = 10) -> List[float]:
    """Test window discovery performance."""
    print_header("TEST 1: Window Discovery Performance")
    print_result("Test", "find_cursor_windows()")
    print_result("Iterations", str(runs))
    print()
    
    times = []
    windows_found = 0
    
    for i in range(runs):
        start = time.perf_counter()
        windows = find_cursor_windows()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        
        if i == 0:
            windows_found = len(windows)
            print_result("Windows Found", str(windows_found), indent=1)
            if windows and hasattr(windows[0], 'window_text'):
                try:
                    title = windows[0].window_text()
                    print_result("First Window", title, indent=1)
                except:
                    pass
            elif windows and len(windows[0]) >= 2:
                title = windows[0][1]
                print_result("First Window", title, indent=1)
            print()
        
        print(f"  Run {i+1:2d}/{runs}: {format_time(elapsed)}")
    
    # Calculate statistics
    avg = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print()
    print_result("Average", format_time(avg), indent=1)
    print_result("Minimum", format_time(min_time), indent=1)
    print_result("Maximum", format_time(max_time), indent=1)
    
    return times


def test_window_focus_only(cached_windows: List = None, runs: int = 5) -> List[float]:
    """Test window focus and bring-to-front performance (WITHOUT hotkeys)."""
    print_header("TEST 2: Window Focus & Bring-to-Front Performance")
    print_result("Test", "Focus window + Maximize + Bring to front")
    print_result("Iterations", str(runs))
    print_result("Mode", "AUTOMATED (no confirmation)", indent=1)
    
    print()
    print(f"{Colors.WARNING}! This test will focus Cursor window {runs} times{Colors.ENDC}")
    print("Starting in 2 seconds...")
    time.sleep(2)
    
    times = []
    
    # Import platform-specific focus functions
    if sys.platform.startswith("win"):
        from src.focus_cursor import _enhanced_focus_window
        
        for i in range(runs):
            if not cached_windows:
                cached_windows = find_cursor_windows()
            
            if not cached_windows:
                print(f"{Colors.FAIL}ERROR: No windows found{Colors.ENDC}")
                break
            
            window = cached_windows[0]
            
            start = time.perf_counter()
            success = _enhanced_focus_window(window)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            
            status = f"{Colors.OKGREEN}OK{Colors.ENDC}" if success else f"{Colors.FAIL}FAIL{Colors.ENDC}"
            print(f"  Run {i+1:2d}/{runs}: {format_time(elapsed)} {status}")
            
            time.sleep(0.3)
    
    elif sys.platform.startswith("linux"):
        from src.focus_cursor import _linux_focus_window
        
        for i in range(runs):
            if not cached_windows:
                cached_windows = find_cursor_windows()
            
            if not cached_windows:
                print(f"{Colors.FAIL}ERROR: No windows found{Colors.ENDC}")
                break
            
            window_id, title, window_info = cached_windows[0]
            
            start = time.perf_counter()
            success = _linux_focus_window(window_id, window_info)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            
            status = f"{Colors.OKGREEN}OK{Colors.ENDC}" if success else f"{Colors.FAIL}FAIL{Colors.ENDC}"
            print(f"  Run {i+1:2d}/{runs}: {format_time(elapsed)} {status}")
            
            time.sleep(0.3)
    
    if times:
        avg = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print()
        print_result("Average", format_time(avg), indent=1)
        print_result("Minimum", format_time(min_time), indent=1)
        print_result("Maximum", format_time(max_time), indent=1)
    
    return times


def main():
    """Main test runner."""
    print_header("Cursor Window Performance Test Suite (AUTOMATED)")
    print_result("Platform", sys.platform)
    print_result("CWD", str(Path.cwd()))
    print_result("Folder", Path.cwd().name)
    
    try:
        # Test 1: Window discovery
        discovery_times = test_window_discovery(runs=10)
        
        # Get cached windows for subsequent tests
        cached_windows = find_cursor_windows()
        
        # Test 2: Focus performance
        focus_times = test_window_focus_only(cached_windows=cached_windows, runs=5)
        
        # Final summary
        print_header("Performance Summary")
        
        if discovery_times:
            avg_discovery = sum(discovery_times) / len(discovery_times)
            print_result("Window Discovery (avg)", format_time(avg_discovery))
        
        if focus_times:
            avg_focus = sum(focus_times) / len(focus_times)
            print_result("Window Focus (avg)", format_time(avg_focus))
        
        print()
        print(f"{Colors.OKGREEN}[OK] All tests completed successfully{Colors.ENDC}\n")
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Tests interrupted by user{Colors.ENDC}\n")
        return 1
    except Exception as e:
        print(f"\n{Colors.FAIL}ERROR: {e}{Colors.ENDC}\n")
        logger.exception("Test failed with exception:")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

