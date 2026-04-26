"""
Slash Command Autocomplete Popup

This module provides an autocomplete popup that appears when users type "/" in text fields.
"""

from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QTextCursor, QFont, QTextCharFormat, QColor, QBrush
import logging
import os
from typing import List, Optional

from .slash_commands import SlashCommand, get_command_manager


# Theme color configuration for slash commands
SLASH_COMMAND_THEMES = {
    "dark": {
        "bg_color": QColor(31, 111, 235, 38),  # rgba(31, 111, 235, 0.15)
        "fg_color": QColor(31, 111, 235),      # #1f6feb
    },
    "light": {
        "bg_color": QColor(0, 102, 204, 26),   # rgba(0, 102, 204, 0.1)
        "fg_color": QColor(0, 102, 204),       # #0066cc
    }
}

# UI dimension constants
DEFAULT_POPUP_MAX_HEIGHT = 300
DEFAULT_POPUP_MIN_WIDTH = 350
DEFAULT_POPUP_MAX_WIDTH = 500
DEFAULT_ITEM_HEIGHT_ESTIMATE = 30
DEFAULT_POPUP_PADDING = 10


class SlashCommandPopup(QListWidget):
    """Autocomplete popup for slash commands"""
    
    command_selected = pyqtSignal(SlashCommand)  # Emitted when a command is selected
    popup_closed = pyqtSignal()  # Emitted when popup is closed (ESC or click away)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.command_manager = get_command_manager()
        self.current_commands: List[SlashCommand] = []
        
        # Setup popup appearance
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Don't steal focus from text edit
        self.setObjectName("slashCommandPopup")
        
        # Popup styling with configurable dimensions
        self.setMinimumWidth(int(os.getenv("SLASH_POPUP_MIN_WIDTH", DEFAULT_POPUP_MIN_WIDTH)))
        self.setMaximumWidth(int(os.getenv("SLASH_POPUP_MAX_WIDTH", DEFAULT_POPUP_MAX_WIDTH)))
        self._max_popup_height = int(os.getenv("SLASH_POPUP_MAX_HEIGHT", DEFAULT_POPUP_MAX_HEIGHT))
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        
        # Connect selection signal
        self.itemClicked.connect(self._on_item_clicked)
        self.itemActivated.connect(self._on_item_activated)
    
    def keyPressEvent(self, event):
        """Handle keyboard events in the popup"""
        key = event.key()
        modifiers = event.modifiers()

        # Handle navigation keys in popup
        if key == Qt.Key.Down:
            super().keyPressEvent(event)
            return
        elif key == Qt.Key.Up:
            super().keyPressEvent(event)
            return
        elif key in (Qt.Key.Return, Qt.Key.Enter):
            # Select current item
            if self.currentItem():
                command = self.currentItem().data(Qt.ItemDataRole.UserRole)
                if command:
                    self.command_selected.emit(command)
                    self.hide()
            event.accept()
            return
        elif key == Qt.Key.Escape:
            # ESC closes the popup
            self.hide()
            self.popup_closed.emit()
            event.accept()
            return

        # For all other keys (typing), forward to parent text edit
        # This allows typing to filter commands while popup is open
        if self.parent():
            from PyQt6.QtWidgets import QApplication
            QApplication.sendEvent(self.parent(), event)
            event.accept()
    
    def hideEvent(self, event):
        """Override hide event to emit signal"""
        super().hideEvent(event)
        # Emit closed signal whenever popup is hidden (ESC, click away, etc.)
        self.popup_closed.emit()
    
    def show_commands(self, commands: List[SlashCommand], position: QPoint):
        """Show popup with filtered commands at specified position"""
        if not commands:
            self.hide()
            return

        self.current_commands = commands
        self.clear()

        # Add commands to list
        for cmd in commands:
            item = QListWidgetItem()
            item.setText(f"/{cmd.name}")
            item.setToolTip(cmd.description)
            item.setData(Qt.ItemDataRole.UserRole, cmd)  # Store command object

            # Set custom display with name and description
            display_text = f"/{cmd.name}"
            if cmd.description:
                display_text += f" - {cmd.description}"
            item.setText(display_text)

            self.addItem(item)
        
        # Select first item by default
        if self.count() > 0:
            self.setCurrentRow(0)
        
        # Adjust size to content
        self._adjust_size()
        
        # Position popup
        self.move(position)
        
        # Show popup
        self.show()
        self.raise_()
    
    def _adjust_size(self):
        """Adjust popup size based on content"""
        if self.count() == 0:
            return
        
        # Calculate required height
        item_height = self.sizeHintForRow(0)
        total_height = min(item_height * self.count() + DEFAULT_POPUP_PADDING, self._max_popup_height)
        
        # Dynamically set height based on content
        self.setFixedHeight(int(total_height))
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        command = item.data(Qt.ItemDataRole.UserRole)
        if command:
            self.command_selected.emit(command)
            self.hide()

    def _on_item_activated(self, item: QListWidgetItem):
        """Handle item activation (double-click or Enter)"""
        command = item.data(Qt.ItemDataRole.UserRole)
        if command:
            self.command_selected.emit(command)
            self.hide()
    
    def select_next(self):
        """Select next item in list (for arrow key navigation)"""
        current = self.currentRow()
        if current < self.count() - 1:
            self.setCurrentRow(current + 1)
    
    def select_previous(self):
        """Select previous item in list (for arrow key navigation)"""
        current = self.currentRow()
        if current > 0:
            self.setCurrentRow(current - 1)
    
    def select_current(self):
        """Select currently highlighted item"""
        item = self.currentItem()
        if item:
            command = item.data(Qt.UserRole)
            if command:
                self.command_selected.emit(command)
                self.hide()
    
    def filter_commands(self, query: str, reposition: bool = True):
        """Filter commands based on query and dynamically resize"""
        if not query:
            # Show all commands
            commands = self.command_manager.get_all_commands()
        else:
            # Search for matching commands
            commands = self.command_manager.search_commands(query)
        
        # Store current parent for repositioning
        parent_widget = self.parent()
        
        # Update display
        self.current_commands = commands
        self.clear()
        
        for cmd in commands:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, cmd)

            # Highlight matching part
            display_text = f"/{cmd.name}"
            if cmd.description:
                display_text += f" - {cmd.description}"
            item.setText(display_text)

            self.addItem(item)
        
        # Select first item
        if self.count() > 0:
            self.setCurrentRow(0)
        
        # If no results, hide popup
        if self.count() == 0:
            self.hide()
            return
        
        # Adjust size based on new content
        self._adjust_size()
        
        # Reposition popup above cursor with new height
        if reposition and parent_widget:
            try:
                cursor = parent_widget.textCursor()
                cursor_rect = parent_widget.cursorRect(cursor)
                global_pos = parent_widget.mapToGlobal(cursor_rect.topLeft())
                
                # Get actual popup height after resize
                popup_height = self.height()
                popup_pos = QPoint(global_pos.x(), global_pos.y() - popup_height - 5)
                
                self.move(popup_pos)
            except Exception:
                pass  # If repositioning fails, keep current position


class SlashCommandTextEditMixin:
    """
    Mixin class to add slash command functionality to QTextEdit.
    
    Usage:
        class MyTextEdit(SlashCommandTextEditMixin, QTextEdit):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setup_slash_commands()
    """
    
    def setup_slash_commands(self):
        """Initialize slash command functionality"""
        self.slash_popup = SlashCommandPopup(self)
        self.slash_popup.command_selected.connect(self._on_command_selected)
        self.slash_popup.popup_closed.connect(self._on_popup_closed)
        self.command_manager = get_command_manager()
        self.logger = logging.getLogger(__name__)
        
        # Track slash command state
        self.in_slash_command = False
        self.slash_start_position = -1
        
        # Store max popup height for position calculations
        self._max_popup_height = int(os.getenv("SLASH_POPUP_MAX_HEIGHT", DEFAULT_POPUP_MAX_HEIGHT))
    
    def keyPressEvent(self, event):
        """Override to handle slash command detection"""
        key = event.key()
        modifiers = event.modifiers()

        # If popup is visible, let popup handle navigation keys
        # (popup will forward typing keys back to us)
        if self.slash_popup.isVisible():
            if key in (Qt.Key.Down, Qt.Key.Up, Qt.Key.Return, Qt.Key.Enter, Qt.Key.Escape):
                # Let popup handle these
                from PyQt6.QtWidgets import QApplication
                QApplication.sendEvent(self.slash_popup, event)
                return
            elif key == Qt.Key.Space and modifiers == Qt.KeyboardModifier.NoModifier:
                # Space closes popup and ends slash command
                self.slash_popup.hide()
                self.in_slash_command = False
                # Let space key through to add space to text

        # Store position before keystroke
        cursor_before = self.textCursor().position()

        # Call parent implementation FIRST
        super().keyPressEvent(event)

        # Reset format AFTER keystroke if we're not in a slash command
        # This prevents pill badge formatting from bleeding to new text
        if not self.in_slash_command and event.text() and not event.text().isspace():
            cursor = self.textCursor()
            cursor_after = cursor.position()

            # If text was inserted, reset its format
            if cursor_after > cursor_before:
                cursor.setPosition(cursor_before)
                cursor.setPosition(cursor_after, QTextCursor.MoveMode.KeepAnchor)

                normal_format = QTextCharFormat()
                cursor.setCharFormat(normal_format)

                # Also reset the block char format to prevent inheritance
                cursor.setPosition(cursor_after)
                self.setCurrentCharFormat(normal_format)
                self.setTextCursor(cursor)

        # After key is processed, check for slash command trigger
        self._check_slash_command()
    
    def _check_slash_command(self):
        """Check if we're in a slash command and update popup"""
        try:
            cursor = self.textCursor()
            pos = cursor.position()

            # Get text before cursor
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
            text_before = cursor.selectedText()

            # Reset cursor position
            cursor = self.textCursor()

            # Check if we just typed "/"
            if text_before.endswith('/'):
                # Check if this is at start of line or after whitespace
                if len(text_before) == 1 or text_before[-2].isspace():
                    self.in_slash_command = True
                    self.slash_start_position = pos - 1
                    self._show_slash_popup("")
                    return

            # If we're in a slash command, check for updates
            if self.in_slash_command and self.slash_start_position >= 0:
                # Extract text from slash to cursor
                text_length = pos - self.slash_start_position
                if text_length <= 0:
                    self.in_slash_command = False
                    self.slash_popup.hide()
                    return

                cursor = self.textCursor()
                cursor.setPosition(self.slash_start_position)
                cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
                slash_text = cursor.selectedText()

                # Check if we moved away from slash command (space, newline, etc.)
                if ' ' in slash_text or '\n' in slash_text or not slash_text.startswith('/'):
                    self.in_slash_command = False
                    self.slash_popup.hide()
                    return

                # Update popup with filtered commands
                query = slash_text[1:]  # Remove leading "/"
                self._show_slash_popup(query)
        except Exception as e:
            # Log error but don't crash the application
            self.logger.error(f"Error in _check_slash_command: {e}", exc_info=True)
            self.in_slash_command = False
            self.slash_popup.hide()
    
    def _show_slash_popup(self, query: str):
        """Show slash command popup with filtered results"""
        if query:
            commands = self.command_manager.search_commands(query)
        else:
            commands = self.command_manager.get_all_commands()
        
        if not commands:
            self.slash_popup.hide()
            return
        
        # Calculate popup position (ABOVE cursor)
        cursor = self.textCursor()
        cursor_rect = self.cursorRect(cursor)
        
        # Convert to global coordinates
        global_pos = self.mapToGlobal(cursor_rect.topLeft())
        
        # Position popup ABOVE the cursor line
        # We need to know popup height to position it correctly
        popup_height = min(
            len(commands) * DEFAULT_ITEM_HEIGHT_ESTIMATE + DEFAULT_POPUP_PADDING, 
            self._max_popup_height
        )
        popup_pos = QPoint(global_pos.x(), global_pos.y() - popup_height - 5)
        
        # Show popup
        self.slash_popup.show_commands(commands, popup_pos)
    
    def _on_command_selected(self, command: SlashCommand):
        """Handle command selection from popup"""
        try:
            if not self.in_slash_command or self.slash_start_position < 0:
                return

            # Get current cursor position
            cursor = self.textCursor()
            current_pos = cursor.position()

            # Select the partial "/commandtext" that user typed
            cursor.setPosition(self.slash_start_position)
            cursor.setPosition(current_pos, QTextCursor.MoveMode.KeepAnchor)

            # Create a styled format for the command (pill badge style)
            command_format = QTextCharFormat()

            # Check if dark mode and get theme colors
            dark_mode = os.getenv("APP_DARK_MODE", "").strip().lower() in ("1", "true", "yes", "on")
            theme = SLASH_COMMAND_THEMES["dark" if dark_mode else "light"]

            # Apply theme colors
            command_format.setBackground(QBrush(theme["bg_color"]))
            command_format.setForeground(QBrush(theme["fg_color"]))

            # Make it slightly bold
            font = command_format.font()
            font.setWeight(QFont.Weight.DemiBold)
            command_format.setFont(font)

            # Insert the command text with formatting
            cursor.insertText(f"/{command.name}", command_format)

            # Store the template in a custom property on the text edit for later retrieval
            # We'll need to track which commands were used and their templates
            if not hasattr(self, '_slash_commands_used'):
                self._slash_commands_used = {}

            # Store the command template associated with this command name
            self._slash_commands_used[command.name] = command.template

            # Add a space after the command with normal formatting (reset format)
            normal_format = QTextCharFormat()
            cursor.insertText(" ", normal_format)

            # Reset state
            self.in_slash_command = False
            self.slash_start_position = -1
            self.slash_popup.hide()

            # Set focus back to text edit
            self.setFocus()
        except Exception as e:
            # Log error but don't crash
            self.logger.error(f"Error in _on_command_selected: {e}", exc_info=True)
            self.in_slash_command = False
            self.slash_start_position = -1
            self.slash_popup.hide()
    
    def _on_popup_closed(self):
        """Handle popup closed event"""
        # Reset slash command state when popup closes
        self.in_slash_command = False
        self.slash_start_position = -1
    
    def get_expanded_text(self) -> str:
        """
        Get the text with slash commands expanded to their full templates.
        Call this instead of toPlainText() to get the expanded version.
        """
        # Get plain text (strips HTML formatting)
        text = self.toPlainText()
        
        if not hasattr(self, '_slash_commands_used') or not self._slash_commands_used:
            return text
        
        import re
        
        # Find all /command patterns in text
        all_slash_patterns = re.findall(r'/(\w+)', text)
        commands_in_text = set(all_slash_patterns)
        
        # Clean up unused commands from tracking dict (fix memory leak)
        self._slash_commands_used = {
            name: template 
            for name, template in self._slash_commands_used.items()
            if name in commands_in_text
        }
        
        # Find unknown commands (in text but not tracked)
        unknown_commands = [
            cmd for cmd in commands_in_text 
            if cmd not in self._slash_commands_used
        ]
        
        # Log warning for unknown commands
        if unknown_commands:
            if hasattr(self, 'logger'):
                self.logger.warning(
                    f"Unknown slash commands in text: {unknown_commands}"
                )
        
        # Replace known commands
        # Use more specific pattern: slash + exact name + (space|punct|end)
        for command_name, template in self._slash_commands_used.items():
            pattern = r'/(' + re.escape(command_name) + r')(?=\s|[.,!?;:]|$)'
            text = re.sub(pattern, lambda m: template, text)
        
        return text

