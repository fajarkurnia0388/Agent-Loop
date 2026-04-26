"""
Slash Command Editor Dialog

Provides a UI for managing slash commands (add, edit, remove).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QLineEdit, QTextEdit, QComboBox,
    QMessageBox, QWidget, QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
import logging
from typing import Optional

from .slash_commands import SlashCommand, get_command_manager


class CommandEditorWidget(QWidget):
    """Widget for editing a single command"""
    
    command_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_command: Optional[SlashCommand] = None
        self.is_new_command = False
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the editor UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Command name
        name_layout = QHBoxLayout()
        name_label = QLabel("Command Name:")
        name_label.setProperty("labelType", "section")
        name_label.setMinimumWidth(120)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., explain, refactor, debug")
        self.name_edit.textChanged.connect(self.command_changed.emit)
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_edit, 1)
        layout.addLayout(name_layout)
        
        # Category
        category_layout = QHBoxLayout()
        category_label = QLabel("Category:")
        category_label.setProperty("labelType", "section")
        category_label.setMinimumWidth(120)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(["general", "code", "debug", "documentation"])
        self.category_combo.currentTextChanged.connect(self.command_changed.emit)
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_combo, 1)
        layout.addLayout(category_layout)
        
        # Description
        desc_label = QLabel("Description:")
        desc_label.setProperty("labelType", "section")
        layout.addWidget(desc_label)
        
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Brief description shown in autocomplete...")
        self.description_edit.setMaximumHeight(60)
        self.description_edit.textChanged.connect(self.command_changed.emit)
        layout.addWidget(self.description_edit)
        
        # Template
        template_label = QLabel("Prompt Template:")
        template_label.setProperty("labelType", "section")
        layout.addWidget(template_label)
        
        
        self.template_edit = QTextEdit()
        self.template_edit.setPlaceholderText(
            "Enter the prompt template...\n\n"
            "Example:\n"
            "Please explain the following in detail."
        )
        self.template_edit.textChanged.connect(self.command_changed.emit)
        layout.addWidget(self.template_edit)
        
        layout.addStretch()
    
    def load_command(self, command: Optional[SlashCommand], is_new: bool = False):
        """Load a command into the editor"""
        self.current_command = command
        self.is_new_command = is_new
        
        if command:
            self.name_edit.setText(command.name)
            self.category_combo.setCurrentText(command.category)
            self.description_edit.setPlainText(command.description)
            self.template_edit.setPlainText(command.template)
            self.name_edit.setEnabled(is_new)  # Can't change name of existing command
        else:
            self.clear()
    
    def clear(self):
        """Clear all fields"""
        self.current_command = None
        self.is_new_command = False
        self.name_edit.clear()
        self.name_edit.setEnabled(True)
        self.category_combo.setCurrentText("general")
        self.description_edit.clear()
        self.template_edit.clear()
    
    def get_command(self) -> Optional[SlashCommand]:
        """Get command from current form values"""
        name = self.name_edit.text().strip().lower()
        if not name:
            return None
        
        # Remove "/" prefix if user added it
        if name.startswith('/'):
            name = name[1:]
        
        category = self.category_combo.currentText().strip()
        description = self.description_edit.toPlainText().strip()
        template = self.template_edit.toPlainText().strip()
        
        if not template:
            return None
        
        return SlashCommand(
            name=name,
            description=description,
            template=template,
            category=category
        )
    
    def is_valid(self) -> bool:
        """Check if current form values are valid"""
        name = self.name_edit.text().strip()
        template = self.template_edit.toPlainText().strip()
        return bool(name and template)


class SlashCommandEditorDialog(QDialog):
    """Dialog for managing slash commands"""
    
    commands_updated = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Slash Commands")
        self.setModal(True)
        self.resize(800, 600)
        
        self.command_manager = get_command_manager()
        self.logger = logging.getLogger(__name__)
        self.unsaved_changes = False
        
        self.setup_ui()
        self.load_commands()
    
    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Title and description
        title = QLabel("Slash Commands")
        title.setProperty("labelType", "sectionHeader")
        layout.addWidget(title)
        
        description = QLabel(
            "Create and manage slash commands for quick AI prompts. "
            "Type '/' in the response field to see available commands."
        )
        description.setProperty("labelType", "hint")
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # Main content: splitter with list and editor
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side: command list with buttons
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        list_label = QLabel("Commands:")
        list_label.setProperty("labelType", "section")
        left_layout.addWidget(list_label)
        
        self.command_list = QListWidget()
        self.command_list.currentItemChanged.connect(self._on_command_selected)
        left_layout.addWidget(self.command_list)
        
        # List buttons
        list_buttons = QHBoxLayout()
        list_buttons.setSpacing(8)
        
        self.btn_new = QPushButton("New")
        self.btn_new.setProperty("buttonType", "primary")
        self.btn_new.clicked.connect(self._on_new_command)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setProperty("buttonType", "secondary")
        self.btn_delete.clicked.connect(self._on_delete_command)
        
        list_buttons.addWidget(self.btn_new)
        list_buttons.addWidget(self.btn_delete)
        list_buttons.addStretch()
        
        left_layout.addLayout(list_buttons)
        
        # Right side: command editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        editor_label = QLabel("Edit Command:")
        editor_label.setProperty("labelType", "section")
        right_layout.addWidget(editor_label)
        
        self.editor = CommandEditorWidget()
        self.editor.command_changed.connect(self._on_editor_changed)
        right_layout.addWidget(self.editor)
        
        # Editor buttons
        editor_buttons = QHBoxLayout()
        editor_buttons.setSpacing(8)
        
        self.btn_save_command = QPushButton("Save Command")
        self.btn_save_command.setProperty("buttonType", "primary")
        self.btn_save_command.clicked.connect(self._on_save_command)
        self.btn_save_command.setEnabled(False)
        
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setProperty("buttonType", "secondary")
        self.btn_clear.clicked.connect(self._on_clear_editor)
        
        editor_buttons.addWidget(self.btn_save_command)
        editor_buttons.addWidget(self.btn_clear)
        editor_buttons.addStretch()
        
        right_layout.addLayout(editor_buttons)
        
        # Add to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
        
        # Dialog buttons
        dialog_buttons = QHBoxLayout()
        dialog_buttons.setSpacing(12)
        dialog_buttons.addStretch()
        
        btn_close = QPushButton("Close")
        btn_close.setProperty("buttonType", "primary")
        btn_close.setMinimumWidth(100)
        btn_close.clicked.connect(self.accept)
        
        dialog_buttons.addWidget(btn_close)
        layout.addLayout(dialog_buttons)
    
    def load_commands(self):
        """Load commands into the list"""
        self.command_list.clear()
        commands = self.command_manager.get_all_commands()
        
        for cmd in commands:
            item = QListWidgetItem(f"/{cmd.name}")
            item.setData(Qt.UserRole, cmd)
            item.setToolTip(cmd.description)
            self.command_list.addItem(item)
    
    def _on_command_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle command selection from list"""
        if current:
            command = current.data(Qt.UserRole)
            self.editor.load_command(command, is_new=False)
            self.btn_save_command.setEnabled(False)
        else:
            self.editor.clear()
    
    def _on_new_command(self):
        """Create a new command"""
        self.command_list.clearSelection()
        self.editor.load_command(None, is_new=True)
        self.editor.name_edit.setFocus()
        self.btn_save_command.setEnabled(False)
    
    def _on_delete_command(self):
        """Delete the selected command"""
        current_item = self.command_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "No Selection", "Please select a command to delete.")
            return
        
        command = current_item.data(Qt.UserRole)
        
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the command '/{command.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.command_manager.remove_command(command.name):
                self.load_commands()
                self.editor.clear()
                self.commands_updated.emit()
            else:
                QMessageBox.warning(self, "Error", "Failed to delete command.")
    
    def _on_save_command(self):
        """Save the current command"""
        if not self.editor.is_valid():
            QMessageBox.warning(
                self,
                "Invalid Command",
                "Please fill in all required fields (name and template)."
            )
            return
        
        command = self.editor.get_command()
        if not command:
            return
        
        # Check if command name already exists (for new commands)
        if self.editor.is_new_command:
            existing = self.command_manager.get_command(command.name)
            if existing:
                QMessageBox.warning(
                    self,
                    "Duplicate Name",
                    f"A command with the name '/{command.name}' already exists."
                )
                return
        
        # Save command
        if self.command_manager.add_command(command):
            self.load_commands()
            self.editor.clear()
            self.btn_save_command.setEnabled(False)
            self.commands_updated.emit()
            
            # No confirmation message - silent save
        else:
            QMessageBox.warning(self, "Error", "Failed to save command.")
    
    def _on_clear_editor(self):
        """Clear the editor"""
        self.command_list.clearSelection()
        self.editor.clear()
        self.btn_save_command.setEnabled(False)
    
    def _on_editor_changed(self):
        """Handle editor content changes"""
        self.btn_save_command.setEnabled(self.editor.is_valid())


