"""
Slash Command Management System

This module handles slash command definitions, storage, and retrieval.
Commands are stored as JSON files in the commands/ directory.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class SlashCommand:
    """Represents a single slash command"""
    name: str  # Command name without the "/" prefix (e.g., "explain")
    description: str  # Brief description shown in autocomplete
    template: str  # Prompt template (static text)
    category: str = "general"  # Category for organization (general, code, debug, etc.)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SlashCommand':
        """Create SlashCommand from dictionary"""
        return cls(**data)


class SlashCommandManager:
    """Manages slash commands - loading, saving, and retrieval"""
    
    def __init__(self, commands_dir: str = "commands"):
        # Convert relative path to absolute based on module location
        # This ensures commands are found regardless of CWD
        if not Path(commands_dir).is_absolute():
            # Get the directory where this module is located (src/)
            module_dir = Path(__file__).parent
            # Project root is parent of src/
            project_root = module_dir.parent
            # Commands directory is at project_root/commands
            commands_dir = str(project_root / commands_dir)
        
        self.commands_dir = Path(commands_dir)
        self.commands_file = self.commands_dir / "commands.json"
        self.commands: Dict[str, SlashCommand] = {}
        self.logger = logging.getLogger(__name__)
        
        # Ensure commands directory exists
        self.commands_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing commands or create defaults
        self._load_commands()
    
    def _load_commands(self):
        """Load commands from JSON file"""
        if self.commands_file.exists():
            try:
                with open(self.commands_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.commands = {
                        name: SlashCommand.from_dict(cmd_data)
                        for name, cmd_data in data.items()
                    }
                self.logger.info(f"Loaded {len(self.commands)} slash commands")
            except Exception as e:
                self.logger.error(f"Failed to load commands: {e}")
                self._create_default_commands()
        else:
            self._create_default_commands()
    
    def _create_default_commands(self):
        """Create default slash commands"""
        default_commands = [
            SlashCommand(
                name="explain",
                description="Explain code or concept in detail",
                template="Please explain the following in detail.",
                category="code"
            ),
            SlashCommand(
                name="refactor",
                description="Suggest refactoring improvements",
                template="Please review and suggest refactoring improvements. Focus on code quality, readability, and best practices.",
                category="code"
            ),
            SlashCommand(
                name="debug",
                description="Help debug an error or issue",
                template="Please help me debug this error. Provide potential causes and solutions.",
                category="debug"
            ),
            SlashCommand(
                name="optimize",
                description="Optimize code for performance",
                template="Please analyze and optimize the following code for performance. Suggest improvements for speed and efficiency.",
                category="code"
            ),
            SlashCommand(
                name="test",
                description="Generate unit tests for code",
                template="Please generate comprehensive unit tests. Include edge cases and error handling.",
                category="code"
            ),
            SlashCommand(
                name="document",
                description="Generate documentation",
                template="Please generate detailed documentation. Include docstrings, parameters, return values, and examples.",
                category="code"
            ),
            SlashCommand(
                name="review",
                description="Perform code review",
                template="Please perform a thorough code review. Check for bugs, security issues, style violations, and best practices.",
                category="code"
            ),
            SlashCommand(
                name="security",
                description="Security analysis and recommendations",
                template="Please analyze the code for security vulnerabilities. Provide specific recommendations to fix any issues.",
                category="debug"
            ),
            SlashCommand(
                name="simplify",
                description="Simplify complex code",
                template="Please simplify the following code while maintaining functionality. Make it more readable and easier to understand.",
                category="code"
            ),
            SlashCommand(
                name="fix",
                description="Fix code issues",
                template="Please fix the following code. Provide the corrected version with explanations.",
                category="debug"
            ),
        ]
        
        self.commands = {cmd.name: cmd for cmd in default_commands}
        self._save_commands()
        self.logger.info(f"Created {len(self.commands)} default slash commands")
    
    def _save_commands(self):
        """Save commands to JSON file with file locking"""
        import tempfile
        import shutil
        
        try:
            # Create atomic write: write to temp file, then rename
            temp_fd, temp_path = tempfile.mkstemp(
                suffix='.json.tmp',
                dir=self.commands_dir,
                text=True
            )
            
            try:
                data = {name: cmd.to_dict() for name, cmd in self.commands.items()}
                
                # Write to temp file with file locking
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    # Platform-specific file locking
                    try:
                        import msvcrt  # Windows
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    except ImportError:
                        try:
                            import fcntl  # Unix/Linux/Mac
                            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except (ImportError, OSError):
                            # No locking available, proceed anyway
                            pass
                    
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk
                
                # Atomic rename (replaces old file)
                shutil.move(temp_path, str(self.commands_file))
                
                self.logger.debug(f"Saved {len(self.commands)} commands")
                return True
            except Exception as e:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except:
                    pass
                raise e
        except Exception as e:
            self.logger.error(f"Failed to save commands: {e}")
            return False
    
    def get_command(self, name: str) -> Optional[SlashCommand]:
        """Get a command by name"""
        return self.commands.get(name.lower())
    
    def get_all_commands(self) -> List[SlashCommand]:
        """Get all commands sorted by name"""
        return sorted(self.commands.values(), key=lambda c: c.name)
    
    def search_commands(self, query: str) -> List[SlashCommand]:
        """Search commands using fuzzy matching"""
        if not query:
            return self.get_all_commands()
        
        query = query.lower()
        results = []
        
        for cmd in self.get_all_commands():
            # Calculate fuzzy match score
            name_lower = cmd.name.lower()
            desc_lower = cmd.description.lower()
            
            # Exact match gets highest score
            if query == name_lower:
                results.append((cmd, 1000))
            # Starts with query
            elif name_lower.startswith(query):
                results.append((cmd, 900))
            # Contains query as substring
            elif query in name_lower:
                results.append((cmd, 800))
            # Fuzzy match - all query chars appear in order
            elif self._fuzzy_match(query, name_lower):
                results.append((cmd, 700))
            # Description contains query
            elif query in desc_lower:
                results.append((cmd, 600))
            # Fuzzy match in description
            elif self._fuzzy_match(query, desc_lower):
                results.append((cmd, 500))
        
        # Sort by score (descending) and return commands
        results.sort(key=lambda x: x[1], reverse=True)
        return [cmd for cmd, score in results]
    
    def _fuzzy_match(self, query: str, text: str) -> bool:
        """
        Check if all characters in query appear in text in order.
        Example: "dbg" matches "debug", "refctr" matches "refactor"
        """
        query_idx = 0
        for char in text:
            if query_idx < len(query) and char == query[query_idx]:
                query_idx += 1
        return query_idx == len(query)
    
    def add_command(self, command: SlashCommand) -> bool:
        """Add or update a command"""
        try:
            # Validate command name is not empty
            if not command.name or not command.name.strip():
                self.logger.warning("Cannot add command with empty name")
                return False
            
            self.commands[command.name.lower()] = command
            return self._save_commands()
        except Exception as e:
            self.logger.error(f"Failed to add command: {e}")
            return False
    
    def remove_command(self, name: str) -> bool:
        """Remove a command by name"""
        try:
            if name.lower() in self.commands:
                del self.commands[name.lower()]
                return self._save_commands()
            return False
        except Exception as e:
            self.logger.error(f"Failed to remove command: {e}")
            return False
    
    def get_categories(self) -> List[str]:
        """Get list of unique categories"""
        categories = set(cmd.category for cmd in self.commands.values())
        return sorted(categories)
    
    def get_commands_by_category(self, category: str) -> List[SlashCommand]:
        """Get all commands in a specific category"""
        return [
            cmd for cmd in self.get_all_commands()
            if cmd.category.lower() == category.lower()
        ]


# Global instance for easy access
_manager_instance: Optional[SlashCommandManager] = None


def get_command_manager() -> SlashCommandManager:
    """Get or create the global SlashCommandManager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SlashCommandManager()
    return _manager_instance

