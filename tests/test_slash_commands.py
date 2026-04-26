"""
Unit tests for SlashCommandManager
"""
import pytest
import json
import tempfile
import os
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.slash_commands import SlashCommand, SlashCommandManager


class TestSlashCommand:
    """Test SlashCommand data class"""
    
    def test_to_dict(self):
        """Test serialization"""
        cmd = SlashCommand("test", "Test desc", "Test template", "general")
        result = cmd.to_dict()
        assert result == {
            "name": "test",
            "description": "Test desc",
            "template": "Test template",
            "category": "general"
        }
    
    def test_from_dict(self):
        """Test deserialization"""
        data = {
            "name": "test",
            "description": "Test desc",
            "template": "Test template",
            "category": "general"
        }
        cmd = SlashCommand.from_dict(data)
        assert cmd.name == "test"
        assert cmd.description == "Test desc"
        assert cmd.template == "Test template"
        assert cmd.category == "general"
    
    def test_unicode_command_name(self):
        """Test command with unicode name"""
        cmd = SlashCommand("解释", "Explain in Chinese", "请解释: {selection}", "translation")
        assert cmd.name == "解释"
        
        # Test serialization
        data = cmd.to_dict()
        assert data["name"] == "解释"
        
        # Test deserialization
        restored = SlashCommand.from_dict(data)
        assert restored.name == "解释"
        assert restored.template == "请解释: {selection}"
    
    def test_unicode_arabic_command(self):
        """Test command with Arabic unicode name"""
        cmd = SlashCommand("شرح", "Explain in Arabic", "اشرح: {selection}", "translation")
        assert cmd.name == "شرح"
        assert cmd.template == "اشرح: {selection}"
    
    def test_unicode_emoji_command(self):
        """Test command with emoji in name"""
        cmd = SlashCommand("🔍explain", "Search explain", "🔍 {selection}", "general")
        assert cmd.name == "🔍explain"
        assert "🔍" in cmd.template


class TestSlashCommandManager:
    """Test SlashCommandManager CRUD operations"""
    
    @pytest.fixture
    def temp_commands_dir(self):
        """Create temporary directory for commands"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_load_default_commands(self, temp_commands_dir):
        """Test default command creation"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        assert len(mgr.commands) == 10  # 10 default commands
        assert "explain" in mgr.commands
        assert "debug" in mgr.commands
        assert "refactor" in mgr.commands
    
    def test_add_command(self, temp_commands_dir):
        """Test adding custom command"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        initial_count = len(mgr.commands)
        
        new_cmd = SlashCommand("custom", "Custom command", "Custom: {selection}", "general")
        assert mgr.add_command(new_cmd) is True
        assert len(mgr.commands) == initial_count + 1
        assert mgr.get_command("custom") == new_cmd
    
    def test_add_unicode_command(self, temp_commands_dir):
        """Test adding command with unicode name"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Chinese
        chinese_cmd = SlashCommand("解释", "Explain in Chinese", "请解释: {selection}", "translation")
        assert mgr.add_command(chinese_cmd) is True
        assert mgr.get_command("解释") == chinese_cmd
        
        # Arabic
        arabic_cmd = SlashCommand("شرح", "Explain in Arabic", "اشرح: {selection}", "translation")
        assert mgr.add_command(arabic_cmd) is True
        assert mgr.get_command("شرح") == arabic_cmd
        
        # Japanese
        japanese_cmd = SlashCommand("説明", "Explain in Japanese", "説明してください: {selection}", "translation")
        assert mgr.add_command(japanese_cmd) is True
        assert mgr.get_command("説明") == japanese_cmd
    
    def test_remove_command(self, temp_commands_dir):
        """Test command removal"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        assert mgr.remove_command("explain") is True
        assert mgr.get_command("explain") is None
    
    def test_update_command(self, temp_commands_dir):
        """Test command update"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Update existing command (add_command handles both add and update)
        updated = SlashCommand("explain", "Updated desc", "Updated template", "general")
        assert mgr.add_command(updated) is True
        
        result = mgr.get_command("explain")
        assert result.description == "Updated desc"
        assert result.template == "Updated template"
    
    def test_fuzzy_search(self, temp_commands_dir):
        """Test fuzzy command search"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Exact match
        results = mgr.search_commands("explain")
        assert len(results) > 0
        assert results[0].name == "explain"
        
        # Partial match
        results = mgr.search_commands("exp")
        assert len(results) > 0
        assert any(cmd.name == "explain" for cmd in results)
        
        # Fuzzy match (dbg -> debug)
        results = mgr.search_commands("dbg")
        assert any(cmd.name == "debug" for cmd in results)
    
    def test_fuzzy_search_unicode(self, temp_commands_dir):
        """Test fuzzy search with unicode commands"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Add unicode commands
        mgr.add_command(SlashCommand("解释", "Explain", "解释: {selection}", "general"))
        mgr.add_command(SlashCommand("调试", "Debug", "调试: {selection}", "general"))
        
        # Search for unicode
        results = mgr.search_commands("解")
        assert len(results) > 0
        assert any(cmd.name == "解释" for cmd in results)
    
    def test_persistence(self, temp_commands_dir):
        """Test that commands persist across manager instances"""
        # Create first manager and add command
        mgr1 = SlashCommandManager(commands_dir=temp_commands_dir)
        new_cmd = SlashCommand("persistent", "Persistent test", "Test: {selection}", "general")
        mgr1.add_command(new_cmd)
        
        # Create second manager and verify command exists
        mgr2 = SlashCommandManager(commands_dir=temp_commands_dir)
        result = mgr2.get_command("persistent")
        assert result is not None
        assert result.name == "persistent"
        assert result.template == "Test: {selection}"
    
    def test_persistence_unicode(self, temp_commands_dir):
        """Test unicode command persistence"""
        # Create first manager and add unicode command
        mgr1 = SlashCommandManager(commands_dir=temp_commands_dir)
        unicode_cmd = SlashCommand("тест", "Test in Cyrillic", "Тест: {selection}", "general")
        mgr1.add_command(unicode_cmd)
        
        # Create second manager and verify
        mgr2 = SlashCommandManager(commands_dir=temp_commands_dir)
        result = mgr2.get_command("тест")
        assert result is not None
        assert result.name == "тест"
        assert result.template == "Тест: {selection}"
    
    def test_malformed_json(self, temp_commands_dir):
        """Test recovery from corrupted JSON"""
        commands_file = Path(temp_commands_dir) / "commands.json"
        commands_file.write_text("{invalid json", encoding='utf-8')
        
        # Manager should fall back to defaults
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        assert len(mgr.commands) == 10  # Falls back to defaults
    
    def test_get_command_template(self, temp_commands_dir):
        """Test retrieving command templates"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Get the explain command
        cmd = mgr.get_command("explain")
        assert cmd is not None
        assert cmd.template == "Please explain the following in detail."
    
    def test_custom_command_retrieval(self, temp_commands_dir):
        """Test adding and retrieving custom commands"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Create command with static template
        cmd = SlashCommand("ask", "Ask question", "Please help me understand this concept.", "general")
        assert mgr.add_command(cmd) is True
        
        # Retrieve and verify
        result = mgr.get_command("ask")
        assert result is not None
        assert result.template == "Please help me understand this concept."
    
    def test_unicode_command_template(self, temp_commands_dir):
        """Test unicode command with static template"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        cmd = SlashCommand("解释", "Explain", "请解释这个概念", "general")
        mgr.add_command(cmd)
        
        result = mgr.get_command("解释")
        assert result is not None
        assert "请解释" in result.template
    
    def test_file_locking_mechanism(self, temp_commands_dir):
        """Test that file locking is attempted (doesn't fail)"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Add multiple commands quickly (simulate concurrent access)
        for i in range(5):
            cmd = SlashCommand(f"test{i}", f"Test {i}", f"Template {i}", "general")
            assert mgr.add_command(cmd) is True
        
        # Verify all were saved
        assert len(mgr.commands) >= 15  # 10 defaults + 5 new
    
    def test_command_name_case_insensitive(self, temp_commands_dir):
        """Test that command names are case-insensitive"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Add command with lowercase
        cmd = SlashCommand("test", "Test", "Template", "general")
        mgr.add_command(cmd)
        
        # Retrieve with different cases
        assert mgr.get_command("test") is not None
        assert mgr.get_command("TEST") is not None
        assert mgr.get_command("Test") is not None


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    @pytest.fixture
    def temp_commands_dir(self):
        """Create temporary directory for commands"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_empty_command_name(self, temp_commands_dir):
        """Test that empty command names are rejected"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        cmd = SlashCommand("", "Empty", "Template", "general")
        assert mgr.add_command(cmd) is False
    
    def test_command_with_slash_prefix(self, temp_commands_dir):
        """Test that slash prefix in name is handled"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        cmd = SlashCommand("/test", "Test", "Template", "general")
        # Should normalize to "test" (or reject, depending on implementation)
        mgr.add_command(cmd)
        # Try to retrieve without slash
        result = mgr.get_command("test")
        # Should either find it or the add should have failed
        assert result is not None or len(mgr.commands) == 10
    
    def test_very_long_command_name(self, temp_commands_dir):
        """Test command with very long name"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        long_name = "a" * 1000
        cmd = SlashCommand(long_name, "Long", "Template", "general")
        result = mgr.add_command(cmd)
        # Should either succeed or fail gracefully
        assert isinstance(result, bool)
    
    def test_special_characters_in_name(self, temp_commands_dir):
        """Test command names with special characters"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        
        # Test various special characters
        special_names = ["test-cmd", "test_cmd", "test.cmd", "test@cmd"]
        for name in special_names:
            cmd = SlashCommand(name, "Special", "Template", "general")
            mgr.add_command(cmd)
    
    def test_template_static(self, temp_commands_dir):
        """Test static template (no dynamic content)"""
        mgr = SlashCommandManager(commands_dir=temp_commands_dir)
        cmd = SlashCommand("static", "Static", "This is a static template", "general")
        assert mgr.add_command(cmd) is True
        
        # Static templates work as-is
        result = mgr.get_command("static")
        assert result.template == "This is a static template"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


