from pathlib import Path
import os
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QCheckBox, QPushButton, QWidget
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve, pyqtSignal, QPoint


class SlideNotification(QWidget):
    """A slide-in notification widget that appears inside the parent window."""
    
    def __init__(self, parent, message, duration=2000):
        super().__init__(parent)
        self.duration = duration
        self.parent_widget = parent
        self.setObjectName("slideNotification")
        
        # Set as child widget, not a separate window
        self.setParent(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)  # Enable styled background
        self.setAutoFillBackground(True)  # Ensure background is filled
        
        # Setup UI with theme-aware styling
        self.setup_ui(message)
        
        # Notification default geometry params
        self.notification_width = 320
        self.notification_height = 70
        self.setFixedSize(self.notification_width, self.notification_height)
        self.start_x = 0
        self.end_x = 0
        self.y_pos = 30
        
    def setup_ui(self, message):
        """Setup the notification UI with theme-aware styling"""
        
        # Main layout for the notification widget
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # Success icon container with circular background
        icon_container = QWidget()
        icon_container.setFixedSize(36, 36)
        icon_container.setObjectName("slideNotificationIcon")
        
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Success icon (checkmark)
        icon_label = QLabel("✓")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(icon_label)
        
        # Message label - soft white text
        msg_label = QLabel(message)
        msg_label.setObjectName("slideNotificationText")
        msg_label.setWordWrap(True)
        
        # Add widgets to layout
        layout.addWidget(icon_container)
        layout.addWidget(msg_label, 1)  # Give message label stretch factor
        
        # No drop shadow - keep it clean
        
    def show_notification(self):
        """Show the notification with slide-in animation"""
        # Compute parent-based geometry just-in-time to avoid width=0 issues
        parent = self.parent_widget
        if not parent or parent.width() <= 0:
            # Retry after a short delay if parent not ready
            QTimer.singleShot(50, self.show_notification)
            return

        # Ensure parent has stable geometry (not in the middle of animations)
        parent_width = parent.width()
        if parent_width < 100:  # Minimum reasonable width
            QTimer.singleShot(50, self.show_notification)
            return
            
        self.start_x = parent_width
        self.end_x = parent_width - self.notification_width - 30
        
        # Ensure end position is reasonable
        if self.end_x < 0:
            self.end_x = 10  # Minimum left margin
            
        self.move(self.start_x, self.y_pos)

        self.show()
        self.raise_()

        # Slide-in animation
        self.slide_animation = QPropertyAnimation(self, b"pos")
        self.slide_animation.setDuration(400)
        self.slide_animation.setStartValue(QPoint(self.start_x, self.y_pos))
        self.slide_animation.setEndValue(QPoint(self.end_x, self.y_pos))
        self.slide_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Connect to slide out after duration
        self.slide_animation.finished.connect(self.schedule_slide_out)
        self.slide_animation.start()
        
    def schedule_slide_out(self):
        """Schedule the slide-out animation after duration"""
        QTimer.singleShot(self.duration, self.slide_out)
        
    def slide_out(self):
        # Slide out animation
        self.slide_animation = QPropertyAnimation(self, b"pos")
        self.slide_animation.setDuration(300)
        self.slide_animation.setStartValue(QPoint(self.end_x, self.y_pos))
        self.slide_animation.setEndValue(QPoint(self.start_x, self.y_pos))
        self.slide_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.slide_animation.finished.connect(self.deleteLater)  # Clean up the widget
        self.slide_animation.start()


class SettingsDialog(QDialog):
    """Settings dialog for theme and additional context modal preferences."""
    settings_saved = pyqtSignal(bool)  # Signal emitted when settings are saved (bool indicates context modal state)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(400, 200)

        # Store original settings for cancel/restore functionality
        self.original_dark_mode = os.getenv("APP_DARK_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        self.original_disable_cursor = os.getenv("APP_DISABLE_CURSOR_CONTROL", "").strip().lower() in ("1", "true", "yes", "on")
        self.original_auto_stop = os.getenv("APP_AUTO_STOP", "").strip().lower() in ("1", "true", "yes", "on")

        # Apply current theme to the settings dialog
        self._apply_theme(self.original_dark_mode)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        title = QLabel("Theme")
        title.setProperty("labelType", "section")
        layout.addWidget(title)

        self.radio_light = QRadioButton("Light Theme")
        self.radio_dark = QRadioButton("Dark Theme")


        # Initialize from env var
        dark_pref = os.getenv("APP_DARK_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        if dark_pref:
            self.radio_dark.setChecked(True)
        else:
            self.radio_light.setChecked(True)

        row = QHBoxLayout()
        row.setSpacing(24)
        row.addWidget(self.radio_light)
        row.addWidget(self.radio_dark)
        row.addStretch()
        layout.addLayout(row)

        # UI Preferences section
        ui_label = QLabel("UI Preferences")
        ui_label.setProperty("labelType", "section")
        layout.addWidget(ui_label)

        # Cursor Control setting
        self.checkbox_disable_cursor = QCheckBox("Disable Cursor Control")
        self.checkbox_disable_cursor.setToolTip(
            "When enabled, disables cursor grabbing functionality and hides the Stop button.\n"
            "The application will not attempt to control or focus Cursor windows."
        )
        # Initialize from env var, default to False
        disable_cursor_pref = os.getenv("APP_DISABLE_CURSOR_CONTROL", "").strip().lower() in ("1", "true", "yes", "on")
        self.checkbox_disable_cursor.setChecked(disable_cursor_pref)
        layout.addWidget(self.checkbox_disable_cursor)

        # Auto-Stop setting
        self.checkbox_auto_stop = QCheckBox("Enable Auto-Stop")
        self.checkbox_auto_stop.setToolTip(
            "When enabled, the leader tool will automatically focus cursor and send stop signal\n"
            "instead of showing the UI. This completely bypasses the feedback interface."
        )
        # Initialize from env var, default to False
        auto_stop_pref = os.getenv("APP_AUTO_STOP", "").strip().lower() in ("1", "true", "yes", "on")
        self.checkbox_auto_stop.setChecked(auto_stop_pref)
        layout.addWidget(self.checkbox_auto_stop)

        # Slash Commands section
        slash_label = QLabel("Slash Commands")
        slash_label.setProperty("labelType", "section")
        layout.addWidget(slash_label)

        slash_desc = QLabel("Manage quick AI prompt commands (type '/' in response field)")
        slash_desc.setProperty("labelType", "hint")
        slash_desc.setWordWrap(True)
        layout.addWidget(slash_desc)

        slash_button_layout = QHBoxLayout()
        btn_manage_commands = QPushButton("Manage Slash Commands...")
        btn_manage_commands.setProperty("buttonType", "secondary")
        btn_manage_commands.clicked.connect(self._open_command_editor)
        slash_button_layout.addWidget(btn_manage_commands)
        slash_button_layout.addStretch()
        layout.addLayout(slash_button_layout)

        # Add some spacing before buttons
        layout.addSpacing(12)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("buttonType", "secondary")
        btn_cancel.setMinimumWidth(80)
        btn_save = QPushButton("Save")
        btn_save.setProperty("buttonType", "primary")
        btn_save.setMinimumWidth(80)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_save)
        layout.addLayout(buttons)

        btn_cancel.clicked.connect(self._cancel_and_restore)
        btn_save.clicked.connect(self._save_and_apply)

    def _open_command_editor(self):
        """Open the slash command editor dialog"""
        try:
            from .slash_command_editor import SlashCommandEditorDialog
            editor = SlashCommandEditorDialog(self)
            editor.exec()
        except Exception as e:
            logging.error(f"Failed to open command editor: {e}")

    # Preview methods removed - no immediate changes on toggle

    def _save_and_apply(self):
        # Get current selections
        dark = self.radio_dark.isChecked()
        disable_cursor = self.checkbox_disable_cursor.isChecked()
        auto_stop = self.checkbox_auto_stop.isChecked()

        # Update environment variables for current process
        os.environ["APP_DARK_MODE"] = "true" if dark else "false"
        os.environ["APP_DISABLE_CURSOR_CONTROL"] = "true" if disable_cursor else "false"
        os.environ["APP_AUTO_STOP"] = "true" if auto_stop else "false"

        # Write all settings to .env file atomically
        success = self._write_all_env_flags(dark, disable_cursor, auto_stop)
        
        if success:
            # Apply theme changes
            self._apply_theme(dark)
            
            # Emit signal for settings saved (no context modal state needed)
            self.settings_saved.emit(False)
            
            self.accept()
        else:
            # Show error message if save failed
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Save Error", "Failed to save settings to .env file. Please try again.")
            # Don't close dialog on error

    def _cancel_and_restore(self):
        """Cancel settings and restore original values"""
        try:
            # Restore original theme
            self._apply_theme(self.original_dark_mode)
            
            # Restore original environment variables
            os.environ["APP_DARK_MODE"] = "true" if self.original_dark_mode else "false"
            os.environ["APP_DISABLE_CURSOR_CONTROL"] = "true" if self.original_disable_cursor else "false"
            os.environ["APP_AUTO_STOP"] = "true" if self.original_auto_stop else "false"
            
            # Refresh parent theme if needed
            if hasattr(self.parent(), 'refresh_theme') and callable(getattr(self.parent(), 'refresh_theme')):
                self.parent().refresh_theme()
                
        except Exception as e:
            logging.debug(f"Failed to restore original settings: {e}")
        
        self.reject()

    def _apply_theme(self, dark: bool):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return
        qss = Path("styles/app_dark.qss") if dark else Path("styles/app_light.qss")
        if qss.exists():
            try:
                with open(qss, 'r', encoding='utf-8') as f:
                    app.setStyleSheet(f.read())
            except Exception:
                pass

    def _write_all_env_flags(self, dark: bool, disable_cursor: bool, auto_stop: bool) -> bool:
        """Write all settings to .env file in a single atomic operation"""
        try:
            env_file = Path(".env")
            
            # Settings to write
            settings = {
                "APP_DARK_MODE": "true" if dark else "false",
                "APP_DISABLE_CURSOR_CONTROL": "true" if disable_cursor else "false",
                "APP_AUTO_STOP": "true" if auto_stop else "false"
            }

            # Read existing content if file exists
            lines = []
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

            # Update or add settings
            keys_updated = set()
            new_lines = []

            for line in lines:
                # Check if this line contains one of our settings
                line_stripped = line.strip()
                key_found = None

                for key in settings:
                    # Check for exact key match (handles optional export and spaces)
                    if line_stripped.startswith(f"{key}=") or \
                       line_stripped.startswith(f"export {key}=") or \
                       f" {key}=" in line_stripped:
                        key_found = key
                        break

                if key_found:
                    # Replace with new value (preserve newline if present)
                    new_line = f"{key_found}={settings[key_found]}"
                    if line.endswith('\n'):
                        new_line += '\n'
                    new_lines.append(new_line)
                    keys_updated.add(key_found)
                else:
                    # Keep existing line as-is
                    new_lines.append(line)

            # Add any missing keys at the end
            for key, value in settings.items():
                if key not in keys_updated:
                    # Add newline if file doesn't end with one
                    if new_lines and not new_lines[-1].endswith('\n'):
                        new_lines[-1] += '\n'
                    new_lines.append(f"{key}={value}\n")

            # Write back to file
            with open(env_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

            return True

        except Exception as e:
            logging.error(f"Failed to write settings to .env file: {e}")
            return False
    
