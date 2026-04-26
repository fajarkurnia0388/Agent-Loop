#!/usr/bin/env python3
"""
Senior Tools UI Invoker

This script provides a direct way to launch the Senior Tools UI interface.
It can be used to test the UI or launch it independently of the MCP server.
"""

import sys
import os
from pathlib import Path

# Add the current directory to Python path to ensure imports work
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    # Import the UI creation function from senior_tools (in parent directory)
    from senior_tools import create_modern_feedback_dialog, play_notification_sound_threaded
    import logging

    # Setup basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    def main():
        """Main entry point for UI invocation

        Usage:
            python invoke_ui.py <project_dir> <agent_comment>

        Arguments:
            project_dir: Path to the project directory
            agent_comment: The markdown content to display (can be "-" to read from stdin)

        Output:
            Prints user response to stdout, or empty string if cancelled
        """
        # Parse command line arguments
        if len(sys.argv) >= 3:
            # Subprocess mode: python invoke_ui.py <project_dir> <agent_comment>
            project_dir = sys.argv[1]
            agent_comment = sys.argv[2]

            # If agent_comment is "-", read from stdin
            # CRITICAL FIX: Reconfigure stdin to use UTF-8 encoding
            # Windows PowerShell defaults to cp1252 which can't handle Unicode characters
            if agent_comment == "-":
                import io
                sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
                agent_comment = sys.stdin.read()
        elif len(sys.argv) == 2:
            # Single argument mode (backward compatibility)
            project_dir = str(Path.cwd())
            agent_comment = sys.argv[1]
        else:
            # No arguments - use defaults for testing
            project_dir = str(Path.cwd())
            # Default demonstration message showing various UI features
            agent_comment = """## Summary
UI Test - Senior Tools Dialog Demonstration

## Features Tested
This dialog demonstrates the following capabilities:

### Agent Report Section
- **Markdown rendering** with headers, lists, and formatting
- **Code snippet support** with syntax highlighting
- **Copy functionality** - Select text and press Ctrl+C
- **Theme switching** - Toggle between dark and light modes
- **Scrollable content** for long reports

### Response Input Section
- **Plain text input** - No formatting preserved from clipboard
- **Image paste support** - Paste images directly with Ctrl+V
- **Auto-height adjustment** - Grows as you type
- **Keyboard shortcuts** - Ctrl+Enter to submit

### Configuration Options
- Project-specific checkboxes appear based on .env settings
- Persistent session state during dialog lifetime

## Code Example
```python
def example_function(param: str) -> str:
    \"\"\"This is a demo function\"\"\"
    return f"Hello, {param}!"
```

## Next Steps
1. Review the agent's work summary
2. Provide feedback or approval
3. Click Send or press Ctrl+Enter to submit
4. Or close the dialog to cancel

**Try the theme toggle button in the top-right corner!**"""

        logger.info("Launching Senior Tools UI...")
        logger.info(f"Project directory: {project_dir}")
        logger.info(f"Agent comment length: {len(agent_comment)} characters")

        # Play notification sound in background thread
        logger.debug("Playing notification sound...")
        play_notification_sound_threaded()

        try:
            # Launch the UI and get response (pass project_dir parameter)
            response = create_modern_feedback_dialog(agent_comment, project_dir=project_dir)

            # Output response to stdout for subprocess communication
            # Use a special marker to separate response from other output

            # CRITICAL FIX: Reconfigure stdout to use UTF-8 encoding
            # Windows PowerShell defaults to cp1252 which can't handle Unicode characters
            # This prevents UnicodeEncodeError when response contains special characters
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

            if response:
                # Print response with delimiter for easy parsing
                print("===UI_RESPONSE_START===")
                print(response)
                print("===UI_RESPONSE_END===")
                logger.info("UI completed successfully with response")
                return 0
            else:
                # Empty response means user cancelled
                print("===UI_RESPONSE_START===")
                print("")  # Empty string
                print("===UI_RESPONSE_END===")
                logger.info("UI was cancelled by user")
                return 0

        except Exception as e:
            logger.error(f"Error launching UI: {e}", exc_info=True)
            # Print error to stderr instead of stdout
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        return 0

    if __name__ == "__main__":
        sys.exit(main())

except ImportError as e:
    print(f"Error: Failed to import required modules: {e}")
    print("Make sure senior_tools.py is in the parent directory and all dependencies are installed.")
    sys.exit(1)
