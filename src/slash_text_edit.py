"""
Custom QTextEdit with Slash Command Support

Combines QTextEdit with SlashCommandTextEditMixin for slash command functionality.
"""

from PyQt6.QtWidgets import QTextEdit
from .slash_command_popup import SlashCommandTextEditMixin


class SlashCommandTextEdit(SlashCommandTextEditMixin, QTextEdit):
    """QTextEdit with built-in slash command support"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_slash_commands()



