"""
COM Initialization Module for Windows

STRATEGY: Use COINIT_APARTMENTTHREADED (OleInitialize) for Qt clipboard compatibility.

- Qt's OLE clipboard requires OleInitialize() which is COINIT_APARTMENTTHREADED
- pywinauto needs COINIT_MULTITHREADED but will run in a separate thread
- Each thread can have its own COM threading model

This module initializes COM with APARTMENTTHREADED mode in the main thread for Qt,
while pywinauto operations run in a separate worker thread with MULTITHREADED mode.
"""

import platform

# Global flag to track if we initialized COM
COM_INITIALIZED = False

if platform.system() == "Windows":
    try:
        # Use OleInitialize() for Qt clipboard compatibility (APARTMENTTHREADED)
        # pywinauto will initialize COM separately in its own worker thread
        import pythoncom
        
        # OleInitialize = COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE
        # This is required for Qt clipboard operations to work correctly
        pythoncom.OleInitialize()
        COM_INITIALIZED = True
    except Exception as e:
        # If COM is already initialized, that's OK - use existing mode
        COM_INITIALIZED = False


