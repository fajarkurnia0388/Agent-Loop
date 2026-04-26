"""
Senior Tools Source Package

This package contains the modular components of the Senior Tools MCP server.
"""

# Package version
__version__ = "1.0.0"

# Expose key modules for easier imports
from . import com_init
from . import image_handler
from . import settings_dialog
from . import focus_cursor

__all__ = [
    "com_init",
    "image_handler", 
    "settings_dialog",
    "focus_cursor",
]

