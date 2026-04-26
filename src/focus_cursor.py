import sys
import time
import re
import logging
import platform
from pathlib import Path
from typing import List, Set, Optional, Union, Tuple, Any, Callable

# Platform-specific imports
if sys.platform.startswith("win"):
    import ctypes
elif sys.platform.startswith("linux"):
    try:
        from Xlib import X, display, Xatom #type: ignore
        from Xlib.ext import xtest #type: ignore
        from Xlib.protocol import event #type: ignore
        from Xlib.XK import string_to_keysym #type: ignore
    except ImportError:
        print("Error: python-xlib is required for Linux. Install it with: pip install python-xlib")
        sys.exit(1)
elif sys.platform == "darwin":
    try:
        from Cocoa import NSWorkspace, NSRunningApplication, NSApplicationActivateIgnoringOtherApps #type: ignore
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID #type: ignore
        from Quartz import CGEventCreateKeyboardEvent, CGEventPost, kCGHIDEventTap, CGEventSetFlags #type: ignore
        from Quartz import kCGEventKeyDown, kCGEventKeyUp, kCGEventFlagMaskCommand, kCGEventFlagMaskShift #type: ignore
        from Quartz import kCGEventFlagMaskControl, kCGEventFlagMaskAlternate #type: ignore
    except ImportError:
        print("Error: PyObjC is required for macOS. Install it with: pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz")
        sys.exit(1)

# Configure logging for debugging window focus issues to file
import os
log_file = os.path.join(os.path.dirname(__file__), "logs", "focus_cursor.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()  # Keep console for direct script execution
    ]
)
logger = logging.getLogger(__name__)

# Window focus operation configuration - Enhanced for better reliability
FOCUS_STABILIZATION_DELAY_SEC = 0.1  # Increased for better stability
FOCUS_VERIFICATION_TIMEOUT_SEC = 2.0  # Increased timeout for verification
FOCUS_RETRY_ATTEMPTS = 3  # More retry attempts for better success rate

# Timing delays for keyboard operations (prevent stuck modifier keys)
HOTKEY_DELAY_SEC = 0.05  # Fast button presses (50ms)
RETRY_DELAY_SEC = 0.2  # Increased retry delay
RESTORE_DELAY_SEC = 0.3  # Increased restore delay
VERIFICATION_LOOP_DELAY_SEC = 0.05  # Faster verification checks
MODIFIER_RELEASE_DELAY_SEC = 0.05  # Fast button presses (50ms)

# Platform detection
IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

# Cache CWD folder name to avoid repeated filesystem calls
_CACHED_CWD_FOLDER = None

def _get_cwd_folder_name() -> str:
	"""Get current working directory folder name (cached)."""
	global _CACHED_CWD_FOLDER
	if _CACHED_CWD_FOLDER is None:
		_CACHED_CWD_FOLDER = Path.cwd().name
		logger.info(f"Cached CWD folder name: {_CACHED_CWD_FOLDER}")
	return _CACHED_CWD_FOLDER


def _score_window_title(title: str, folder_name: str) -> int:
	"""Score a window title based on CWD folder match.
	
	Returns:
		100: Exact match with folder name
		50: Partial match (folder in title)
		1: Generic Cursor window
		0: Non-standard or invalid
	"""
	try:
		# Pattern: "[tab_info] - [folder_name] - Cursor"
		parts = title.split(" - ")
		
		if len(parts) >= 3 and parts[-1].strip().lower() == "cursor":
			title_folder = parts[-2].strip()
			
			if title_folder.lower() == folder_name.lower():
				return 100  # Exact match
			elif folder_name.lower() in title_folder.lower():
				return 50  # Partial match
			else:
				return 1  # Generic Cursor window
		else:
			return 1  # Non-standard Cursor window
	except Exception:
		return 0


def _clear_keyboard_state():
	"""Clear all modifier keys to prevent stuck keys"""
	if IS_WINDOWS:
		try:
			from pywinauto import keyboard
			keyboard.send_keys('{VK_CONTROL up}{VK_SHIFT up}{VK_MENU up}{VK_LWIN up}')
			time.sleep(0.05)
		except Exception:
			pass
	elif IS_LINUX:
		try:
			d = display.Display()
			root = d.screen().root
			# Release all modifier keys
			for mask in [X.ControlMask, X.ShiftMask, X.Mod1Mask, X.Mod4Mask]:
				root.ungrab_key(X.AnyKey, mask)
			d.sync()
			d.close()
		except Exception:
			pass
	elif IS_MACOS:
		# On macOS, releasing modifiers is handled by CGEvent automatically
		# No explicit clearing needed
		pass


# Linux-specific functions
def _linux_find_cursor_windows() -> List[Tuple[int, str, dict]]:
	"""Find Cursor windows on Linux using X11.
	Returns list of tuples: (window_id, window_title, window_info)
	"""
	cursor_windows = []
	title_rx = re.compile("cursor", re.IGNORECASE)
	
	try:
		d = display.Display()
		root = d.screen().root
		
		# Get window tree
		tree = root.query_tree()
		wins = tree.children
		
		# Iterate through all windows
		for w in wins:
			try:
				# Get window name
				net_wm_name = d.intern_atom('_NET_WM_NAME')
				utf8_string = d.intern_atom('UTF8_STRING')
				
				prop = w.get_full_property(net_wm_name, utf8_string)
				if not prop:
					# Fallback to WM_NAME
					prop = w.get_wm_name()
					if prop:
						window_title = prop
					else:
						continue
				else:
					window_title = prop.value.decode('utf-8', errors='ignore')
				
				# Check if it's a Cursor window
				if title_rx.search(window_title):
					# Get window geometry
					geom = w.get_geometry()
					
					# Get window attributes
					attrs = w.get_attributes()
					
					# Only add if window is viewable
					if attrs.map_state == X.IsViewable:
						window_info = {
							'x': geom.x,
							'y': geom.y,
							'width': geom.width,
							'height': geom.height,
							'display': d,
							'window': w
						}
						cursor_windows.append((w.id, window_title, window_info))
			except Exception as e:
				continue
		
		d.close()
	except Exception as e:
		logger.error(f"Error finding Cursor windows on Linux: {e}")
	
	# Intelligent prioritization: Match current working directory with window title
	if cursor_windows:
		cursor_windows = _prioritize_matching_window_linux(cursor_windows)
	
	return cursor_windows


def _prioritize_matching_window_linux(windows: List[Tuple[int, str, dict]]) -> List[Tuple[int, str, dict]]:
	"""Prioritize the Cursor window matching the current working directory for Linux."""
	try:
		folder_name = _get_cwd_folder_name()
		
		# Score each window using shared scoring logic
		scored_windows = []
		for window_id, title, window_info in windows:
			score = _score_window_title(title, folder_name)
			scored_windows.append((score, (window_id, title, window_info)))
		
		# Sort by score (highest first) and return just the window tuples
		scored_windows.sort(key=lambda x: x[0], reverse=True)
		
		if scored_windows and scored_windows[0][0] >= 100:
			logger.debug(f"Exact match found (score={scored_windows[0][0]})")
		elif scored_windows and scored_windows[0][0] >= 50:
			logger.debug(f"Partial match found (score={scored_windows[0][0]})")
		
		return [win_tuple for score, win_tuple in scored_windows]
		
	except Exception as e:
		logger.error(f"Error in window prioritization: {e}")
		return windows


def _linux_focus_window(window_id: int, window_info: dict) -> bool:
	"""Focus a window on Linux using X11."""
	try:
		d = window_info['display']
		w = window_info['window']
		
		# Get root window
		root = d.screen().root
		
		# Check if window is minimized (iconic)
		wm_state = d.intern_atom('WM_STATE')
		prop = w.get_full_property(wm_state, Xatom.WM_STATE)
		
		# Map window if needed (restore from minimized)
		if prop and len(prop.value) > 0 and prop.value[0] == 3:  # IconicState
			w.map()
			d.sync()
			time.sleep(RESTORE_DELAY_SEC)
		
		# Use EWMH to activate window (most compatible method)
		net_active_window = d.intern_atom('_NET_ACTIVE_WINDOW')
		
		# Send client message to activate window
		event_mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
		cm = event.ClientMessage(
			window=w,
			client_type=net_active_window,
			data=(32, [2, X.CurrentTime, 0, 0, 0])
		)
		root.send_event(cm, event_mask=event_mask)
		
		# Also raise and focus the window
		w.raise_window()
		w.set_input_focus(X.RevertToParent, X.CurrentTime)
		
		d.sync()
		time.sleep(FOCUS_STABILIZATION_DELAY_SEC)
		
		# Verify focus
		focus = d.get_input_focus()
		return focus.focus.id == window_id
		
	except Exception as e:
		logger.error(f"Error focusing window on Linux: {e}")
		return False


def _linux_send_hotkey(window_info: dict, stop_delay: float = 0.0) -> bool:
	"""Send hotkey combination on Linux using X11 with configurable delay.
	
	Sequence:
	1. Send Ctrl+Alt+B twice IMMEDIATELY to prepare Cursor
	2. Wait for stop_delay seconds for Cursor to start streaming
	3. Send Ctrl+Shift+Backspace for final stop signal
	"""
	try:
		d = window_info['display']
		w = window_info['window']
		
		# Ensure window has focus
		w.set_input_focus(X.RevertToParent, X.CurrentTime)
		d.sync()
		
		# Get keycodes
		ctrl_keycode = d.keysym_to_keycode(string_to_keysym('Control_L'))
		alt_keycode = d.keysym_to_keycode(string_to_keysym('Alt_L'))
		shift_keycode = d.keysym_to_keycode(string_to_keysym('Shift_L'))
		b_keycode = d.keysym_to_keycode(string_to_keysym('b'))
		backspace_keycode = d.keysym_to_keycode(string_to_keysym('BackSpace'))
		
		# STEP 1: Send Ctrl+Alt+B twice IMMEDIATELY to prepare Cursor
		logger.info("Sending Ctrl+Alt+B twice to prepare Cursor (Linux)...")
		for _ in range(2):
			# Press Ctrl+Alt
			xtest.fake_input(d, X.KeyPress, ctrl_keycode)
			xtest.fake_input(d, X.KeyPress, alt_keycode)
			d.sync()
			time.sleep(HOTKEY_DELAY_SEC)
			
			# Press B
			xtest.fake_input(d, X.KeyPress, b_keycode)
			d.sync()
			time.sleep(HOTKEY_DELAY_SEC)
			
			# Release B
			xtest.fake_input(d, X.KeyRelease, b_keycode)
			d.sync()
			time.sleep(HOTKEY_DELAY_SEC)
			
			# Release Alt+Ctrl
			xtest.fake_input(d, X.KeyRelease, alt_keycode)
			xtest.fake_input(d, X.KeyRelease, ctrl_keycode)
			d.sync()
			time.sleep(MODIFIER_RELEASE_DELAY_SEC)
		
		# STEP 2: Wait for configured delay (for Cursor to start streaming)
		if stop_delay > 0:
			logger.info(f"Waiting {stop_delay}s for Cursor to start streaming (Linux)...")
			time.sleep(stop_delay)
		
		# STEP 3: Send Ctrl+Shift+Backspace stop signal
		logger.info("Sending Ctrl+Shift+Backspace stop signal (Linux)...")
		# Press Ctrl+Shift
		xtest.fake_input(d, X.KeyPress, ctrl_keycode)
		xtest.fake_input(d, X.KeyPress, shift_keycode)
		d.sync()
		time.sleep(HOTKEY_DELAY_SEC)
		
		# Press Backspace
		xtest.fake_input(d, X.KeyPress, backspace_keycode)
		d.sync()
		time.sleep(HOTKEY_DELAY_SEC)
		
		# Release Backspace
		xtest.fake_input(d, X.KeyRelease, backspace_keycode)
		d.sync()
		time.sleep(HOTKEY_DELAY_SEC)
		
		# Release Shift+Ctrl
		xtest.fake_input(d, X.KeyRelease, shift_keycode)
		xtest.fake_input(d, X.KeyRelease, ctrl_keycode)
		d.sync()
		time.sleep(MODIFIER_RELEASE_DELAY_SEC)
		
		return True
		
	except Exception as e:
		logger.error(f"Error sending hotkey on Linux: {e}")
		return False


# macOS-specific functions
def _macos_find_cursor_windows() -> List[Tuple[int, str, dict]]:
	"""Find Cursor windows on macOS using Cocoa and Quartz.
	Returns list of tuples: (pid, window_title, window_info)
	"""
	cursor_windows = []
	title_rx = re.compile("cursor", re.IGNORECASE)
	
	try:
		# Get all running applications
		workspace = NSWorkspace.sharedWorkspace()
		running_apps = workspace.runningApplications()
		
		# Find Cursor application
		cursor_app = None
		for app in running_apps:
			app_name = app.localizedName()
			if app_name and "cursor" in app_name.lower():
				cursor_app = app
				break
		
		if not cursor_app:
			logger.debug("Cursor application not found in running applications")
			return []
		
		cursor_pid = cursor_app.processIdentifier()
		
		# Get window list using Quartz
		window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
		
		if not window_list:
			return []
		
		# Find windows belonging to Cursor
		for window in window_list:
			try:
				owner_pid = window.get('kCGWindowOwnerPID', 0)
				window_title = window.get('kCGWindowName', '')
				window_layer = window.get('kCGWindowLayer', 0)
				
				# Check if this window belongs to Cursor and has a title
				if owner_pid == cursor_pid and window_title and title_rx.search(window_title):
					# Only consider normal windows (layer 0)
					if window_layer == 0:
						window_info = {
							'pid': cursor_pid,
							'window_number': window.get('kCGWindowNumber', 0),
							'bounds': window.get('kCGWindowBounds', {}),
							'app': cursor_app
						}
						cursor_windows.append((cursor_pid, window_title, window_info))
			except Exception as e:
				continue
		
	except Exception as e:
		logger.error(f"Error finding Cursor windows on macOS: {e}")
	
	# Intelligent prioritization: Match current working directory with window title
	if cursor_windows:
		cursor_windows = _prioritize_matching_window_macos(cursor_windows)
	
	return cursor_windows


def _prioritize_matching_window_macos(windows: List[Tuple[int, str, dict]]) -> List[Tuple[int, str, dict]]:
	"""Prioritize the Cursor window matching the current working directory for macOS."""
	try:
		folder_name = _get_cwd_folder_name()
		
		# Score each window using shared scoring logic
		scored_windows = []
		for pid, title, window_info in windows:
			score = _score_window_title(title, folder_name)
			scored_windows.append((score, (pid, title, window_info)))
		
		# Sort by score (highest first) and return just the window tuples
		scored_windows.sort(key=lambda x: x[0], reverse=True)
		
		if scored_windows and scored_windows[0][0] >= 100:
			logger.debug(f"Exact match found (score={scored_windows[0][0]})")
		elif scored_windows and scored_windows[0][0] >= 50:
			logger.debug(f"Partial match found (score={scored_windows[0][0]})")
		
		return [win_tuple for score, win_tuple in scored_windows]
		
	except Exception as e:
		logger.error(f"Error in window prioritization: {e}")
		return windows


def _macos_focus_window(pid: int, window_info: dict) -> bool:
	"""Focus a window on macOS using NSRunningApplication."""
	try:
		app = window_info['app']
		
		# Check if app is hidden
		if app.isHidden():
			app.unhide()
			time.sleep(RESTORE_DELAY_SEC)
		
		# Activate the application (brings all windows to front)
		success = app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
		
		if not success:
			logger.warning("Failed to activate Cursor application")
			return False
		
		time.sleep(FOCUS_STABILIZATION_DELAY_SEC)
		
		# Verify focus by checking if app is active
		return app.isActive()
		
	except Exception as e:
		logger.error(f"Error focusing window on macOS: {e}")
		return False


def _macos_send_hotkey(window_info: dict, stop_delay: float = 0.0) -> bool:
	"""Send hotkey combination on macOS using Quartz CGEvent with configurable delay.
	
	Sequence:
	1. Send Cmd+Option+B twice IMMEDIATELY to prepare Cursor (macOS uses Cmd instead of Ctrl)
	2. Wait for stop_delay seconds for Cursor to start streaming
	3. Send Cmd+Shift+Backspace for final stop signal
	"""
	try:
		# macOS keycodes
		B_KEYCODE = 0x0B
		BACKSPACE_KEYCODE = 0x33
		
		# STEP 1: Send Cmd+Option+B twice IMMEDIATELY to prepare Cursor
		logger.info("Sending Cmd+Option+B twice to prepare Cursor (macOS)...")
		for _ in range(2):
			# Create flags for Cmd+Option
			flags = kCGEventFlagMaskCommand | kCGEventFlagMaskAlternate
			
			# Press B with modifiers
			event_down = CGEventCreateKeyboardEvent(None, B_KEYCODE, True)
			CGEventSetFlags(event_down, flags)
			CGEventPost(kCGHIDEventTap, event_down)
			time.sleep(HOTKEY_DELAY_SEC)
			
			# Release B
			event_up = CGEventCreateKeyboardEvent(None, B_KEYCODE, False)
			CGEventPost(kCGHIDEventTap, event_up)
			time.sleep(MODIFIER_RELEASE_DELAY_SEC)
		
		# STEP 2: Wait for configured delay (for Cursor to start streaming)
		if stop_delay > 0:
			logger.info(f"Waiting {stop_delay}s for Cursor to start streaming (macOS)...")
			time.sleep(stop_delay)
		
		# STEP 3: Send Cmd+Shift+Backspace stop signal
		logger.info("Sending Cmd+Shift+Backspace stop signal (macOS)...")
		# Create flags for Cmd+Shift
		flags = kCGEventFlagMaskCommand | kCGEventFlagMaskShift
		
		# Press Backspace with modifiers
		event_down = CGEventCreateKeyboardEvent(None, BACKSPACE_KEYCODE, True)
		CGEventSetFlags(event_down, flags)
		CGEventPost(kCGHIDEventTap, event_down)
		time.sleep(HOTKEY_DELAY_SEC)
		
		# Release Backspace
		event_up = CGEventCreateKeyboardEvent(None, BACKSPACE_KEYCODE, False)
		CGEventPost(kCGHIDEventTap, event_up)
		time.sleep(MODIFIER_RELEASE_DELAY_SEC)
		
		return True
		
	except Exception as e:
		logger.error(f"Error sending hotkey on macOS: {e}")
		return False


# Windows-specific functions
def _windows_api_focus(hwnd: int) -> bool:
	"""Use Windows API directly to focus window"""
	try:
		user32 = ctypes.windll.user32
		
		# Check if window is minimized
		if user32.IsIconic(hwnd):
			user32.ShowWindow(hwnd, 9)  # SW_RESTORE
			time.sleep(RESTORE_DELAY_SEC)
		
		# Allow set foreground window
		user32.AllowSetForegroundWindow(ctypes.c_uint32(-1))
		
		# Focus using multiple methods
		user32.SetForegroundWindow(hwnd)
		user32.BringWindowToTop(hwnd)
		user32.SetActiveWindow(hwnd)
		
		return user32.GetForegroundWindow() == hwnd
	except Exception:
		return False


def _windows_find_cursor_windows_by_title() -> List[object]:
	from pywinauto import Desktop  # type: ignore
	# Case-insensitive title match for 'Cursor'; try both UIA and Win32 backends
	title_rx = re.compile("- cursor", re.IGNORECASE)
	found: List[object] = []
	seen: Set[int] = set()

	for backend in ("uia", "win32"):
		try:
			desktop = Desktop(backend=backend)
			# Pass 1: direct title_re search (visible only)
			try:
				wins = desktop.windows(title_re=title_rx, visible_only=True)
				for w in wins:
					h = getattr(w, "handle", None)
					if isinstance(h, int) and h not in seen:
						seen.add(h)
						found.append(w)
			except Exception:
				pass

			# Pass 2: enumerate all and manually filter by window_text
			try:
				all_wins = desktop.windows()
				for w in all_wins:
					try:
						title = ""
						try:
							title = w.window_text() or ""
						except Exception:
							title = ""
						if title_rx.search(title or ""):
							h = getattr(w, "handle", None)
							if isinstance(h, int) and h not in seen:
								seen.add(h)
								found.append(w)
					except Exception:
						continue
			except Exception:
				pass
		except Exception:
			continue

	# Intelligent prioritization: Match current working directory with window title
	# Window title pattern: "[tab_info] - [folder_name] - Cursor"
	if found:
		found = _prioritize_matching_window(found)

	return found


def _prioritize_matching_window(windows: List[object]) -> List[object]:
	"""Prioritize the Cursor window matching the current working directory for Windows."""
	try:
		folder_name = _get_cwd_folder_name()
		
		# Score each window using shared scoring logic
		scored_windows = []
		for w in windows:
			try:
				title = w.window_text() or ""
				score = _score_window_title(title, folder_name)
				scored_windows.append((score, w))
			except Exception as e:
				logger.warning(f"Error scoring window: {e}")
				scored_windows.append((0, w))
		
		# Sort by score (highest first) and return just the windows
		scored_windows.sort(key=lambda x: x[0], reverse=True)
		
		if scored_windows and scored_windows[0][0] >= 100:
			logger.debug(f"Exact match found (score={scored_windows[0][0]})")
		elif scored_windows and scored_windows[0][0] >= 50:
			logger.debug(f"Partial match found (score={scored_windows[0][0]})")
		
		return [w for score, w in scored_windows]
		
	except Exception as e:
		logger.error(f"Error in window prioritization: {e}")
		return windows


def _enhanced_focus_window(wrapper: object) -> bool:
	"""Enhanced window focusing using multiple methods"""
	_clear_keyboard_state()
	
	# Try Windows API first (most reliable)
	if hasattr(wrapper, "handle"):
		hwnd = wrapper.handle
		if _windows_api_focus(hwnd):
			return _verify_window_focus(wrapper, hwnd)
	
	# Fallback to PyWinAuto methods
	try:
		if hasattr(wrapper, "set_focus"):
			wrapper.set_focus()
		if hasattr(wrapper, "set_foreground"):
			wrapper.set_foreground()
		time.sleep(0.05)
		
		if hasattr(wrapper, "handle"):
			return _verify_window_focus(wrapper, wrapper.handle)
	except Exception:
		pass
	
	return False


def _verify_window_focus(wrapper: object, hwnd: int) -> bool:
	"""Verify window has focus using multiple methods"""
	verification_score = 0
	
	try:
		# Check 1: pywinauto is_active
		if hasattr(wrapper, "is_active") and wrapper.is_active():
			verification_score += 1
	except Exception:
		pass
	
	try:
		# Check 2: Windows API foreground (most reliable)
		import win32gui
		foreground_hwnd = win32gui.GetForegroundWindow()
		if foreground_hwnd == hwnd:
			verification_score += 2
	except Exception:
		pass
	
	try:
		# Check 3: Keyboard focus
		if hasattr(wrapper, "has_keyboard_focus") and wrapper.has_keyboard_focus():
			verification_score += 1
	except Exception:
		pass
	
	return verification_score >= 2


def _focus_and_send_hotkey_to_windows(wrappers: Union[List[object], List[Tuple[int, str, dict]]], stop_delay: float) -> bool:
	"""Focus any of the provided windows and send hotkeys with retry logic.
	Handles Windows, Linux, and macOS platforms.
	
	Sequence with configurable delay:
	1. Send Ctrl+Alt+B twice IMMEDIATELY to prepare Cursor (fast 50ms delays)
	   (macOS uses Cmd+Option+B instead of Ctrl+Alt+B)
	2. Wait for stop_delay seconds for Cursor to start streaming
	3. Send Ctrl+Shift+Backspace for final stop signal
	   (macOS uses Cmd+Shift+Backspace instead of Ctrl+Shift+Backspace)
	
	Args:
		wrappers: List of window wrappers to try
		stop_delay: Delay in seconds between initial hotkey and stop signal
	"""
	if IS_WINDOWS:
		try:
			from pywinauto import keyboard  # type: ignore
		except Exception:
			return False
	elif IS_LINUX or IS_MACOS:
		# Linux and macOS handling is done in platform-specific functions
		pass
	else:
		return False
	
	logger.info(f"Using stop_delay = {stop_delay}s")
	
	for w in wrappers or []:
		for attempt in range(FOCUS_RETRY_ATTEMPTS):
			try:
				# Platform-specific focus handling
				if IS_WINDOWS:
					# Enhanced focus with verification
					if not _enhanced_focus_window(w):
						if attempt < FOCUS_RETRY_ATTEMPTS - 1:
							time.sleep(RETRY_DELAY_SEC)
							continue
						else:
							break
				elif IS_LINUX:
					# w is a tuple: (window_id, window_title, window_info)
					window_id, window_title, window_info = w
					if not _linux_focus_window(window_id, window_info):
						if attempt < FOCUS_RETRY_ATTEMPTS - 1:
							time.sleep(RETRY_DELAY_SEC)
							continue
						else:
							break
				elif IS_MACOS:
					# w is a tuple: (pid, window_title, window_info)
					pid, window_title, window_info = w
					if not _macos_focus_window(pid, window_info):
						if attempt < FOCUS_RETRY_ATTEMPTS - 1:
							time.sleep(RETRY_DELAY_SEC)
							continue
						else:
							break
				
				time.sleep(FOCUS_STABILIZATION_DELAY_SEC)
				
				# Send hotkeys with proper error handling
				hotkey_success = False
				
				if IS_WINDOWS and hasattr(w, "type_keys"):
					try:
						# STEP 1: Send Ctrl+Alt+B twice IMMEDIATELY to prepare Cursor
						logger.info("Sending Ctrl+Alt+B twice to prepare Cursor...")
						w.type_keys('{VK_CONTROL down}{VK_MENU down}b{VK_MENU up}{VK_CONTROL up}', set_foreground=True, pause=HOTKEY_DELAY_SEC)
						time.sleep(MODIFIER_RELEASE_DELAY_SEC)
						w.type_keys('{VK_CONTROL down}{VK_MENU down}b{VK_MENU up}{VK_CONTROL up}', set_foreground=True, pause=HOTKEY_DELAY_SEC)
						w.type_keys('{VK_MENU up}{VK_CONTROL up}{VK_SHIFT up}', set_foreground=True, pause=HOTKEY_DELAY_SEC)
						time.sleep(MODIFIER_RELEASE_DELAY_SEC)
						
						# STEP 2: Wait for configured delay (for Cursor to start streaming)
						if stop_delay > 0:
							logger.info(f"Waiting {stop_delay}s for Cursor to start streaming...")
							time.sleep(stop_delay)
						
						# STEP 3: Send Ctrl+Shift+Backspace stop signal
						logger.info("Sending Ctrl+Shift+Backspace stop signal...")
						w.type_keys('{VK_CONTROL down}{VK_SHIFT down}{BACKSPACE}{VK_SHIFT up}{VK_CONTROL up}', set_foreground=True, pause=HOTKEY_DELAY_SEC)
						time.sleep(MODIFIER_RELEASE_DELAY_SEC)
						hotkey_success = True
					except Exception:
						pass
				
				if IS_WINDOWS and not hotkey_success:
					try:
						# STEP 1: Send Ctrl+Alt+B twice IMMEDIATELY to prepare Cursor
						logger.info("Sending Ctrl+Alt+B twice to prepare Cursor (keyboard fallback)...")
						keyboard.send_keys('{VK_CONTROL down}{VK_MENU down}b{VK_MENU up}{VK_CONTROL up}', pause=HOTKEY_DELAY_SEC)
						time.sleep(MODIFIER_RELEASE_DELAY_SEC)
						keyboard.send_keys('{VK_CONTROL down}{VK_MENU down}b{VK_MENU up}{VK_CONTROL up}', pause=HOTKEY_DELAY_SEC)
						keyboard.send_keys('{VK_MENU up}{VK_CONTROL up}{VK_SHIFT up}', pause=HOTKEY_DELAY_SEC)
						time.sleep(MODIFIER_RELEASE_DELAY_SEC)
						
						# STEP 2: Wait for configured delay (for Cursor to start streaming)
						if stop_delay > 0:
							logger.info(f"Waiting {stop_delay}s for Cursor to start streaming...")
							time.sleep(stop_delay)
						
						# STEP 3: Send Ctrl+Shift+Backspace stop signal
						logger.info("Sending Ctrl+Shift+Backspace stop signal...")
						keyboard.send_keys('{VK_CONTROL down}{VK_SHIFT down}{BACKSPACE}{VK_SHIFT up}{VK_CONTROL up}', pause=HOTKEY_DELAY_SEC)
						time.sleep(MODIFIER_RELEASE_DELAY_SEC)
						hotkey_success = True
					except Exception:
						pass
				
				elif IS_LINUX:
					# For Linux, use existing function (delay handled there)
					hotkey_success = _linux_send_hotkey(window_info, stop_delay)
				
				elif IS_MACOS:
					# For macOS, use existing function (delay handled there)
					hotkey_success = _macos_send_hotkey(window_info, stop_delay)
				
				if hotkey_success:
					return True
				
			except Exception:
				if attempt < FOCUS_RETRY_ATTEMPTS - 1:
					time.sleep(RETRY_DELAY_SEC)
					continue
				else:
					break
			finally:
				_clear_keyboard_state()
	return False


def find_cursor_windows() -> Union[List[object], List[Tuple[int, str, dict]]]:
	"""Find and return window handles for Cursor windows without focusing them.
	On Windows: returns pywinauto wrappers
	On Linux: returns list of tuples (window_id, window_title, window_info)
	On macOS: returns list of tuples (pid, window_title, window_info)
	"""
	if IS_WINDOWS:
		return _windows_find_cursor_windows_by_title()
	elif IS_LINUX:
		return _linux_find_cursor_windows()
	elif IS_MACOS:
		return _macos_find_cursor_windows()
	else:
		logger.error(f"Unsupported platform: {sys.platform}")
		return []


def debug_cursor_windows() -> None:
	"""Debug function to print information about found Cursor windows."""
	if IS_WINDOWS:
		windows = _windows_find_cursor_windows_by_title()
		logger.info(f"Platform: Windows")
		logger.info(f"Found {len(windows)} Cursor windows:")
		
		for i, w in enumerate(windows):
			try:
				title = getattr(w, 'window_text', lambda: 'Unknown')()
				handle = getattr(w, 'handle', 'Unknown')
				is_active = getattr(w, 'is_active', lambda: False)() if hasattr(w, 'is_active') else False
				is_minimized = getattr(w, 'is_minimized', lambda: False)() if hasattr(w, 'is_minimized') else False
				has_focus = getattr(w, 'has_keyboard_focus', lambda: False)() if hasattr(w, 'has_keyboard_focus') else False
				
				logger.info(f"  Window {i+1}: '{title}' (handle: {handle})")
				logger.info(f"    Active: {is_active}, Minimized: {is_minimized}, Has Focus: {has_focus}")
			except Exception as e:
				logger.warning(f"  Window {i+1}: Error getting info - {e}")
	
	elif IS_LINUX:
		windows = _linux_find_cursor_windows()
		logger.info(f"Platform: Linux (X11)")
		logger.info(f"Found {len(windows)} Cursor windows:")
		
		for i, (window_id, window_title, window_info) in enumerate(windows):
			logger.info(f"  Window {i+1}: '{window_title}'")
			logger.info(f"    Window ID: 0x{window_id:08x}")
			logger.info(f"    Position: ({window_info['x']}, {window_info['y']})")
			logger.info(f"    Size: {window_info['width']}x{window_info['height']}")
	
	elif IS_MACOS:
		windows = _macos_find_cursor_windows()
		logger.info(f"Platform: macOS (Cocoa/Quartz)")
		logger.info(f"Found {len(windows)} Cursor windows:")
		
		for i, (pid, window_title, window_info) in enumerate(windows):
			logger.info(f"  Window {i+1}: '{window_title}'")
			logger.info(f"    PID: {pid}")
			logger.info(f"    Window Number: {window_info['window_number']}")
			logger.info(f"    Bounds: {window_info['bounds']}")
	
	else:
		logger.error(f"Unsupported platform: {sys.platform}")


def focus_cursor_and_send_hotkey(stop_delay: float = None) -> bool:
	"""Find Cursor windows and send stop hotkey to the first one that focuses successfully.
	
	Args:
		stop_delay: Delay in seconds between Ctrl+Alt+B and stop signal. If None, reads from APP_STOP_DELAY env var.
	"""
	try:
		windows = find_cursor_windows()
		platform_name = 'Windows' if IS_WINDOWS else 'Linux' if IS_LINUX else 'macOS' if IS_MACOS else sys.platform
		logger.info(f"Platform: {platform_name}")
		logger.info(f"Found {len(windows)} Cursor windows")
		
		if not windows:
			logger.warning("No Cursor windows found")
			return False
		
		# If stop_delay not provided, read from environment
		if stop_delay is None:
			try:
				import os
				delay_str = os.getenv("APP_STOP_DELAY", "1.5").strip()
				stop_delay = float(delay_str)
				stop_delay = max(0.0, min(10.0, stop_delay))
			except (ValueError, TypeError):
				stop_delay = 1.5
			
		success = _focus_and_send_hotkey_to_windows(windows, stop_delay)
		if success:
			logger.info("Successfully focused Cursor and sent hotkey")
		else:
			logger.error("Failed to focus any Cursor window or send hotkey")
		return success
	except Exception as e:
		logger.error(f"Unexpected error in focus_cursor_and_send_hotkey: {e}")
		return False


def focus_and_send_stop_hotkey_to_any(wrappers: Union[List[object], List[Tuple[int, str, dict]]], stop_delay: float = None) -> bool:
	"""Try focusing and sending the stop hotkey to any of the provided cached wrappers.
	
	Args:
		wrappers: List of window wrappers to try
		stop_delay: Delay in seconds between Ctrl+Alt+B and stop signal. If None, reads from APP_STOP_DELAY env var.
	"""
	# If stop_delay not provided, read from environment
	if stop_delay is None:
		try:
			import os
			delay_str = os.getenv("APP_STOP_DELAY", "1.5").strip()
			stop_delay = float(delay_str)
			stop_delay = max(0.0, min(10.0, stop_delay))
		except (ValueError, TypeError):
			stop_delay = 1.5
	
	return _focus_and_send_hotkey_to_windows(wrappers, stop_delay)


def main() -> int:
	"""Main entry point with enhanced feedback."""
	# Add debug info if needed
	if len(sys.argv) > 1 and sys.argv[1] == "--debug":
		debug_cursor_windows()
	
	success = focus_cursor_and_send_hotkey()
	if success:
		print("✓ Successfully focused Cursor and sent stop hotkey (Ctrl+Alt+B twice + Ctrl+Shift+Backspace)")
	else:
		print("✗ Failed to focus Cursor or send hotkey - check if Cursor is running")
		print("  Use --debug flag for detailed window information")
	return 0 if success else 1


if __name__ == "__main__":
	sys.exit(main())