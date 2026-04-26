"""
Markdown to HTML renderer with syntax highlighting for agent reports.
Converts markdown content to beautiful HTML with code highlighting and copy buttons.
"""

import re
import html
import json
import logging
import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer, ClassNotFound
from pygments.formatters import HtmlFormatter
from typing import Tuple, Dict

# Module logger
logger = logging.getLogger(__name__)


class MarkdownRenderer:
    """Renders markdown to HTML with syntax highlighting and theme support."""

    # CSS Constants (Fix #6: Extract magic numbers)
    SPACING_SMALL = '8px'
    SPACING_MEDIUM_SMALL = '4px'
    SPACING_MEDIUM = '12px'
    SPACING_LARGE = '16px'
    SPACING_XLARGE = '24px'
    BORDER_RADIUS_SMALL = '3px'
    BORDER_RADIUS_MEDIUM = '4px'
    BORDER_RADIUS_LARGE = '6px'
    BORDER_RADIUS_XLARGE = '8px'
    BORDER_RADIUS_ROUND = '10px'
    SCROLLBAR_WIDTH = '12px'
    FONT_SIZE_SMALL = '85%'
    FONT_SIZE_TINY = '12px'
    LINE_HEIGHT_NORMAL = '1.6'
    LINE_HEIGHT_TIGHT = '1.45'
    LINE_HEIGHT_HEADING = '1.25'

    # Input validation constants
    MAX_INPUT_SIZE = 1_000_000  # 1MB limit for markdown input

    # Theme color schemes (Fix #7: Centralize color definitions)
    THEME_COLORS: Dict[str, Dict[str, str]] = {
        'dark': {
            'bg': '#0d1117',
            'text': '#c9d1d9',
            'code_bg': '#161b22',
            'code_border': '#30363d',
            'inline_code_bg': 'rgba(110, 118, 129, 0.4)',
            'inline_code_text': '#f0f6fc',
            'link': '#58a6ff',
            'header': '#f0f6fc',
            'blockquote_border': '#3b434b',
            'blockquote_bg': 'rgba(110, 118, 129, 0.1)',
            'table_border': '#30363d',
            'table_header_bg': '#161b22',
            'copy_btn_bg': '#21262d',
            'copy_btn_hover': '#30363d',
            'copy_btn_text': '#c9d1d9',
        },
        'light': {
            'bg': '#ffffff',
            'text': '#24292f',
            'code_bg': '#f6f8fa',
            'code_border': '#d0d7de',
            'inline_code_bg': 'rgba(175, 184, 193, 0.2)',
            'inline_code_text': '#24292f',
            'link': '#0969da',
            'header': '#24292f',
            'blockquote_border': '#d0d7de',
            'blockquote_bg': 'rgba(175, 184, 193, 0.1)',
            'table_border': '#d0d7de',
            'table_header_bg': '#f6f8fa',
            'copy_btn_bg': '#f6f8fa',
            'copy_btn_hover': '#e1e4e8',
            'copy_btn_text': '#24292f',
        }
    }

    def __init__(self, dark_mode: bool = True):
        """
        Initialize the markdown renderer.

        Args:
            dark_mode: Whether to use dark theme colors
        """
        self.dark_mode = dark_mode
        self.code_blocks = []  # Store code blocks for copy functionality

    def get_theme_colors(self) -> Dict[str, str]:
        """
        Get color scheme based on current theme.

        Returns:
            Dictionary of color values for the current theme
        """
        return self.THEME_COLORS['dark' if self.dark_mode else 'light']

    def highlight_code(self, code: str, language: str = '') -> str:
        """
        Highlight code using Pygments.

        Args:
            code: The code to highlight
            language: Programming language (optional)

        Returns:
            HTML string with highlighted code
        """
        # Fix #5: Catch specific exceptions and log failures
        try:
            if language:
                lexer = get_lexer_by_name(language, stripall=True)
            else:
                lexer = guess_lexer(code)
        except (ClassNotFound, ValueError) as e:
            logger.debug(f"Failed to get lexer for language '{language}': {e}")
            lexer = TextLexer()
        except Exception as e:
            logger.warning(f"Unexpected error getting lexer for language '{language}': {e}")
            lexer = TextLexer()

        # Use HtmlFormatter with inline styles for theme compatibility
        formatter = HtmlFormatter(
            style='monokai' if self.dark_mode else 'default',
            noclasses=True,
            cssclass='highlight'
        )

        return highlight(code, lexer, formatter)

    def detect_diff_pattern(self, text: str) -> bool:
        """
        Detect if text contains OLD/NEW code diff pattern.

        Pattern: Lines with "OLD:" or "- OLD:" followed by code, then "NEW:" or "- NEW:" followed by code

        Args:
            text: Text to check for diff pattern

        Returns:
            True if diff pattern detected
        """
        # Look for OLD/NEW pattern (case-insensitive, with optional list markers)
        old_pattern = r'(?:^|\n)\s*-?\s*OLD\s*:\s*`'
        new_pattern = r'(?:^|\n)\s*-?\s*NEW\s*:\s*`'

        has_old = bool(re.search(old_pattern, text, re.IGNORECASE | re.MULTILINE))
        has_new = bool(re.search(new_pattern, text, re.IGNORECASE | re.MULTILINE))

        return has_old and has_new

    def extract_diff_blocks(self, text: str) -> Tuple[str, str, str]:
        """
        Extract OLD and NEW code blocks from diff pattern.

        Args:
            text: Text containing OLD/NEW pattern

        Returns:
            Tuple of (old_code, new_code, language)
        """
        # Extract OLD code (between OLD: ` and `)
        old_match = re.search(r'OLD\s*:\s*`([^`]+)`', text, re.IGNORECASE | re.DOTALL)
        old_code = old_match.group(1).strip() if old_match else ""

        # Extract NEW code (between NEW: ` and `)
        new_match = re.search(r'NEW\s*:\s*`([^`]+)`', text, re.IGNORECASE | re.DOTALL)
        new_code = new_match.group(1).strip() if new_match else ""

        # Try to detect language from context or code content
        language = self.guess_language_from_code(old_code or new_code)

        return old_code, new_code, language

    def guess_language_from_code(self, code: str) -> str:
        """
        Guess programming language from code content.

        Args:
            code: Code snippet

        Returns:
            Language name (e.g., 'python', 'javascript', 'text')
        """
        if not code:
            return 'text'

        # Simple heuristics for common languages
        if 'def ' in code or 'import ' in code or 'class ' in code and ':' in code:
            return 'python'
        elif 'function ' in code or 'const ' in code or 'let ' in code or '=>' in code:
            return 'javascript'
        elif 'public ' in code or 'private ' in code or 'class ' in code and '{' in code:
            return 'java'
        elif '#include' in code or 'int main' in code:
            return 'cpp'
        elif 'SELECT ' in code.upper() or 'INSERT ' in code.upper():
            return 'sql'
        else:
            return 'text'

    def generate_unified_diff_html(self, old_code: str, new_code: str, language: str) -> str:
        """
        Generate unified diff visualization with syntax highlighting.

        Args:
            old_code: Original code
            new_code: Modified code
            language: Programming language

        Returns:
            HTML string with diff visualization
        """
        import difflib

        colors = self.get_theme_colors()

        # Split into lines for diff
        old_lines = old_code.splitlines(keepends=True)
        new_lines = new_code.splitlines(keepends=True)

        # Generate unified diff
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile='OLD',
            tofile='NEW',
            lineterm=''
        )

        # Convert diff to HTML with syntax highlighting
        diff_lines = list(diff)

        # Skip the header lines (--- and +++)
        diff_content = diff_lines[2:] if len(diff_lines) > 2 else diff_lines

        # Theme-specific diff colors
        if self.dark_mode:
            removed_bg = 'rgba(248, 81, 73, 0.15)'  # Red tint
            removed_text = '#ff7b72'
            added_bg = 'rgba(46, 160, 67, 0.15)'  # Green tint
            added_text = '#56d364'
            context_text = colors['text']
        else:
            removed_bg = 'rgba(255, 235, 233, 0.5)'
            removed_text = '#cf222e'
            added_bg = 'rgba(230, 255, 237, 0.5)'
            added_text = '#1a7f37'
            context_text = colors['text']

        # Build HTML for diff
        diff_html_lines = []
        for line in diff_content:
            if not line:
                continue

            # Escape HTML
            escaped_line = html.escape(line.rstrip('\n'))

            if line.startswith('-'):
                # Removed line
                diff_html_lines.append(
                    f'<div style="background: {removed_bg}; color: {removed_text}; '
                    f'padding: 2px 8px; font-family: monospace; font-size: 13px; line-height: 1.5;">'
                    f'{escaped_line}</div>'
                )
            elif line.startswith('+'):
                # Added line
                diff_html_lines.append(
                    f'<div style="background: {added_bg}; color: {added_text}; '
                    f'padding: 2px 8px; font-family: monospace; font-size: 13px; line-height: 1.5;">'
                    f'{escaped_line}</div>'
                )
            elif line.startswith('@@'):
                # Hunk header
                diff_html_lines.append(
                    f'<div style="background: {colors["code_bg"]}; color: {colors["link"]}; '
                    f'padding: 4px 8px; font-family: monospace; font-size: 12px; font-weight: bold; '
                    f'border-top: 1px solid {colors["code_border"]}; border-bottom: 1px solid {colors["code_border"]};">'
                    f'{escaped_line}</div>'
                )
            else:
                # Context line
                diff_html_lines.append(
                    f'<div style="color: {context_text}; padding: 2px 8px; '
                    f'font-family: monospace; font-size: 13px; line-height: 1.5;">'
                    f'{escaped_line}</div>'
                )

        diff_html = ''.join(diff_html_lines)

        # Wrap in container with header
        code_id = len(self.code_blocks)
        self.code_blocks.append(new_code)  # Store new code for copy

        html_output = f'''
<div class="diff-container" style="position: relative; margin: {self.SPACING_LARGE} 0;">
    <div class="diff-header" style="
        background: {colors['code_bg']};
        border: 1px solid {colors['code_border']};
        border-bottom: none;
        padding: {self.SPACING_SMALL} {self.SPACING_MEDIUM};
        border-radius: {self.BORDER_RADIUS_LARGE} {self.BORDER_RADIUS_LARGE} 0 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    ">
        <span style="color: {colors['text']}; font-size: {self.FONT_SIZE_TINY}; font-family: monospace;">
            📝 Code Changes ({language})
        </span>
        <button onclick="copyCode({code_id})" class="copy-btn" style="
            background: {colors['copy_btn_bg']};
            border: 1px solid {colors['code_border']};
            color: {colors['copy_btn_text']};
            padding: {self.SPACING_MEDIUM_SMALL} {self.SPACING_MEDIUM};
            border-radius: {self.BORDER_RADIUS_MEDIUM};
            cursor: pointer;
            font-size: {self.FONT_SIZE_TINY};
            font-family: system-ui, -apple-system, sans-serif;
        " onmouseover="this.style.background='{colors['copy_btn_hover']}'"
           onmouseout="this.style.background='{colors['copy_btn_bg']}'">
            Copy NEW
        </button>
    </div>
    <div class="diff-content" style="
        background: {colors['code_bg']};
        border: 1px solid {colors['code_border']};
        border-top: none;
        border-radius: 0 0 {self.BORDER_RADIUS_LARGE} {self.BORDER_RADIUS_LARGE};
        overflow-x: auto;
        max-height: 500px;
        overflow-y: auto;
    ">
        {diff_html}
    </div>
</div>
'''
        return html_output

    def process_code_blocks(self, md_text: str) -> str:
        """
        Process fenced code blocks and add syntax highlighting with copy buttons.
        Also detects and renders OLD/NEW diff patterns.

        Args:
            md_text: Markdown text with code blocks

        Returns:
            Markdown with code blocks replaced by HTML
        """
        # Note: self.code_blocks is initialized in render() method
        # Do NOT reset here to preserve code blocks from diff processing

        # Fix #8: Add type hints to nested function
        def replace_code_block(match: re.Match[str]) -> str:
            # Fix #1: Escape language to prevent XSS
            language_raw: str = match.group(1) or ''
            language: str = html.escape(language_raw)
            code: str = match.group(2)

            # Store code for copy functionality
            code_id: int = len(self.code_blocks)
            self.code_blocks.append(code)

            # Highlight the code
            highlighted: str = self.highlight_code(code, language_raw)  # Use raw for lexer

            # Create HTML with copy button
            colors: Dict[str, str] = self.get_theme_colors()

            # Fix #6: Use constants for spacing and border radius
            html_output = f'''
<div class="code-block-container" style="position: relative; margin: {self.SPACING_LARGE} 0;">
    <div class="code-header" style="
        background: {colors['code_bg']};
        border: 1px solid {colors['code_border']};
        border-bottom: none;
        padding: {self.SPACING_SMALL} {self.SPACING_MEDIUM};
        border-radius: {self.BORDER_RADIUS_LARGE} {self.BORDER_RADIUS_LARGE} 0 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    ">
        <span style="color: {colors['text']}; font-size: {self.FONT_SIZE_TINY}; font-family: monospace;">
            {language or 'text'}
        </span>
        <button onclick="copyCode({code_id})" class="copy-btn" style="
            background: {colors['copy_btn_bg']};
            border: 1px solid {colors['code_border']};
            color: {colors['copy_btn_text']};
            padding: {self.SPACING_MEDIUM_SMALL} {self.SPACING_MEDIUM};
            border-radius: {self.BORDER_RADIUS_MEDIUM};
            cursor: pointer;
            font-size: {self.FONT_SIZE_TINY};
            font-family: system-ui, -apple-system, sans-serif;
        " onmouseover="this.style.background='{colors['copy_btn_hover']}'"
           onmouseout="this.style.background='{colors['copy_btn_bg']}'">
            Copy
        </button>
    </div>
    <div class="code-content" style="
        background: {colors['code_bg']};
        border: 1px solid {colors['code_border']};
        border-top: none;
        border-radius: 0 0 {self.BORDER_RADIUS_LARGE} {self.BORDER_RADIUS_LARGE};
        overflow-x: auto;
    ">
        {highlighted}
    </div>
</div>
'''
            return html_output

        # Fix #2: Add comment about ReDoS risk (full fix requires timeout or parser change)
        # Note: This regex pattern can cause ReDoS with malicious input like ```python\n + "a"*10000
        # Consider adding timeout or using a proper markdown parser for production
        pattern = r'```(\w*)\n(.*?)```'
        return re.sub(pattern, replace_code_block, md_text, flags=re.DOTALL)

    def process_diff_patterns(self, md_text: str) -> str:
        """
        Process OLD/NEW diff patterns in markdown and convert to unified diff visualization.

        Detects patterns like:
        - OLD: `code here`
        - NEW: `code here`

        Args:
            md_text: Markdown text potentially containing diff patterns

        Returns:
            Markdown with diff patterns replaced by HTML diff visualization
        """
        # Pattern to match list items with OLD/NEW code blocks
        # Matches: "- **path/to/file**: Description\n  - OLD: `code`\n  - NEW: `code`"
        diff_pattern = r'(- \*\*[^*]+\*\*:[^\n]*\n(?:\s*-\s*OLD\s*:\s*`[^`]+`[^\n]*\n)+(?:\s*-\s*NEW\s*:\s*`[^`]+`[^\n]*\n?)+)'

        def replace_diff_block(match: re.Match[str]) -> str:
            block_text = match.group(1)

            # Check if this block contains diff pattern
            if not self.detect_diff_pattern(block_text):
                return block_text  # Return unchanged if no diff pattern

            # Extract OLD and NEW code
            old_code, new_code, language = self.extract_diff_blocks(block_text)

            if not old_code or not new_code:
                return block_text  # Return unchanged if extraction failed

            # Generate diff HTML
            diff_html = self.generate_unified_diff_html(old_code, new_code, language)

            # Extract the file path and description from the first line
            first_line_match = re.match(r'- \*\*([^*]+)\*\*:\s*([^\n]*)', block_text)
            if first_line_match:
                file_path = first_line_match.group(1)
                description = first_line_match.group(2)

                # Return file info + diff HTML
                return f'- **{file_path}**: {description}\n\n{diff_html}\n'
            else:
                # Just return diff HTML if no file info found
                return diff_html

        # Process diff patterns
        processed = re.sub(diff_pattern, replace_diff_block, md_text, flags=re.MULTILINE | re.DOTALL)

        return processed

    def render(self, md_text: str) -> Tuple[str, list]:
        """
        Render markdown to HTML.

        Args:
            md_text: Markdown text to render

        Returns:
            Tuple of (HTML string, list of code blocks for copy functionality)

        Raises:
            ValueError: If md_text is None or too large
            TypeError: If md_text is not a string
        """
        # Fix #4: Add input validation
        if md_text is None:
            raise ValueError("md_text cannot be None")
        if not isinstance(md_text, str):
            raise TypeError(f"md_text must be str, got {type(md_text).__name__}")
        if len(md_text) > self.MAX_INPUT_SIZE:
            raise ValueError(
                f"md_text too large: {len(md_text)} chars (max {self.MAX_INPUT_SIZE})"
            )

        # Initialize code blocks array at the start of rendering
        self.code_blocks = []

        # Process diff patterns first (converts OLD/NEW to diff HTML)
        processed_md = self.process_diff_patterns(md_text)

        # Then process code blocks (adds syntax highlighting)
        processed_md = self.process_code_blocks(processed_md)

        # Convert markdown to HTML
        md = markdown.Markdown(extensions=[
            'extra',  # Tables, fenced code, etc.
            'nl2br',  # Newline to <br>
            'sane_lists',  # Better list handling
        ])
        html_content = md.convert(processed_md)

        # Get theme colors
        colors: Dict[str, str] = self.get_theme_colors()

        # Fix #3: Use json.dumps() instead of repr() for JavaScript safety
        code_blocks_json: str = json.dumps(self.code_blocks)

        # Fix #6: Use constants for all spacing and sizing values
        # Create complete HTML document with styling
        html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            font-size: 14px;
            line-height: {self.LINE_HEIGHT_NORMAL};
            color: {colors['text']};
            background: {colors['bg']};
            padding: {self.SPACING_LARGE};
            margin: 0;
            border: 1px solid {colors['code_border']};
            border-radius: {self.BORDER_RADIUS_XLARGE};
            min-height: calc(100vh - 2px);
        }}

        /* Modern scrollbar styling */
        ::-webkit-scrollbar {{
            width: {self.SCROLLBAR_WIDTH};
            height: {self.SCROLLBAR_WIDTH};
        }}

        ::-webkit-scrollbar-track {{
            background: {colors['bg']};
            border-radius: {self.BORDER_RADIUS_ROUND};
        }}

        ::-webkit-scrollbar-thumb {{
            background: {colors['code_border']};
            border-radius: {self.BORDER_RADIUS_ROUND};
            border: 2px solid {colors['bg']};
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: {colors['copy_btn_hover']};
        }}

        ::-webkit-scrollbar-corner {{
            background: {colors['bg']};
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: {colors['header']};
            margin-top: {self.SPACING_XLARGE};
            margin-bottom: {self.SPACING_LARGE};
            font-weight: 600;
            line-height: {self.LINE_HEIGHT_HEADING};
        }}

        h1 {{ font-size: 2em; border-bottom: 1px solid {colors['code_border']}; padding-bottom: {self.SPACING_SMALL}; }}
        h2 {{ font-size: 1.5em; border-bottom: 1px solid {colors['code_border']}; padding-bottom: {self.SPACING_SMALL}; }}
        h3 {{ font-size: 1.25em; }}

        p {{ margin-bottom: {self.SPACING_LARGE}; }}

        code {{
            background: {colors['inline_code_bg']};
            color: {colors['inline_code_text']};
            padding: 2px 6px;
            border-radius: {self.BORDER_RADIUS_SMALL};
            font-family: "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, monospace;
            font-size: {self.FONT_SIZE_SMALL};
        }}

        pre {{
            margin: 0;
            padding: {self.SPACING_LARGE};
            overflow-x: auto;
            font-size: {self.FONT_SIZE_SMALL};
            line-height: {self.LINE_HEIGHT_TIGHT};
        }}

        pre code {{
            background: transparent;
            padding: 0;
            border-radius: 0;
        }}

        a {{
            color: {colors['link']};
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}

        blockquote {{
            margin: 0 0 {self.SPACING_LARGE} 0;
            padding: 0 {self.SPACING_LARGE};
            border-left: 4px solid {colors['blockquote_border']};
            background: {colors['blockquote_bg']};
            color: {colors['text']};
        }}

        ul, ol {{
            margin-bottom: {self.SPACING_LARGE};
            padding-left: 2em;
        }}

        li {{
            margin-bottom: {self.SPACING_MEDIUM_SMALL};
        }}

        table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: {self.SPACING_LARGE};
        }}

        table th, table td {{
            padding: {self.SPACING_SMALL} {self.SPACING_MEDIUM};
            border: 1px solid {colors['table_border']};
        }}

        table th {{
            background: {colors['table_header_bg']};
            font-weight: 600;
        }}

        hr {{
            border: none;
            border-top: 1px solid {colors['code_border']};
            margin: {self.SPACING_XLARGE} 0;
        }}

        .highlight {{
            margin: 0;
        }}
    </style>
    <script>
        // Store code blocks for copy functionality
        const codeBlocks = {code_blocks_json};

        function copyCode(index) {{
            const code = codeBlocks[index];
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(code).then(() => {{
                    // Visual feedback
                    const btn = event.target;
                    const originalText = btn.textContent;
                    btn.textContent = '✓ Copied!';
                    setTimeout(() => {{
                        btn.textContent = originalText;
                    }}, 2000);
                }});
            }}
        }}
    </script>
</head>
<body>
    {html_content}
</body>
</html>
'''

        return html, self.code_blocks

