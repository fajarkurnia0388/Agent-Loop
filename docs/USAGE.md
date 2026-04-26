# Usage Guide

This guide provides detailed usage instructions and examples for Senior Tools MCP Server.

## Table of Contents
- [Memory System](#memory-system)
- [Feedback Interface](#feedback-interface)
- [Cursor Window Control](#cursor-window-control)
- [Configuration Management](#configuration-management)
- [Best Practices](#best-practices)
- [Advanced Usage](#advanced-usage)

## Memory System

The memory system allows AI agents to remember project history, bug fixes, and user preferences across sessions.

### Saving Memories

#### Milestone Example
```python
# AI agent calls this when completing a major feature
{
  "tool": "memory_save",
  "event_type": "milestone",
  "description": "Implemented user authentication system. Files: auth/login.py - Added JWT token generation with 24h expiry. OLD: No authentication. NEW: def generate_token(user_id): return jwt.encode({'user_id': user_id, 'exp': datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY). Uses bcrypt for password hashing. Integrated with existing user model.",
  "project_dir": "/absolute/path/to/project"
}
```

#### Bug Fix Example
```python
{
  "tool": "memory_save",
  "event_type": "bug_solved",
  "description": "Fixed memory leak in database connection pool. File: db/pool.py line 45. OLD: connections = [] (never released). NEW: with connection_pool.get_connection() as conn: (auto-release). Root cause: connections not returned to pool. Solution: context manager pattern. Performance: reduced memory usage by 80%.",
  "project_dir": "/absolute/path/to/project"
}
```

#### User Preference Example
```python
{
  "tool": "memory_save",
  "event_type": "user_preference",
  "description": "User prefers async/await pattern over callbacks. Example: async def fetch_data(): return await db.query() instead of def fetch_data(callback): db.query(callback). Apply to all new database operations. Reason: better error handling and readability.",
  "project_dir": "/absolute/path/to/project"
}
```

### Retrieving Memories

#### Semantic Search
```python
# Find relevant memories about authentication
{
  "tool": "memory_call",
  "project_dir": "/absolute/path/to/project",
  "query": "authentication implementation JWT tokens",
  "event_type": "all",
  "limit": 5
}
```

**Response**:
```
## 📚 Project Memory: my_project

**Most Relevant Memories (Top 5)**

1. 🎯 MILESTONE (Relevance: 0.89)
   📅 Time: 2025-10-01 14:30
   📝 Details: Implemented user authentication system...

2. 🐛 BUG SOLVED (Relevance: 0.76)
   📅 Time: 2025-09-28 10:15
   📝 Details: Fixed token expiry validation...
```

#### Filter by Event Type
```python
# Get only bug fixes
{
  "tool": "memory_call",
  "project_dir": "/absolute/path/to/project",
  "query": "database connection issues",
  "event_type": "bug_solved",
  "limit": 3
}
```

#### Recent Memories (No Query)
```python
# Get most recent memories when no specific query
{
  "tool": "memory_call",
  "project_dir": "/absolute/path/to/project",
  "query": "",
  "event_type": "all"
}
```

### Memory Best Practices

1. **Be Verbose**: Include actual code snippets, not just descriptions
2. **Show OLD vs NEW**: Always show what changed
3. **Include Context**: File paths, line numbers, technical reasoning
4. **Use Specific Queries**: "JWT authentication implementation" not "auth stuff"
5. **Save Significant Events**: Don't save trivial changes

## Feedback Interface

The feedback interface allows AI agents to communicate with developers and receive guidance.

### Basic Usage

```python
{
  "tool": "ask_to_leader_project",
  "agent_comment": "## Summary\nImplemented user registration endpoint\n\n## Changes Made\n- **api/routes/auth.py**: Added POST /register endpoint\n  - OLD: No registration endpoint\n  - NEW: @app.post('/register') async def register(user: UserCreate): ...\n  - Validates email format and password strength\n\n## Technical Details\n- Uses Pydantic for input validation\n- Bcrypt for password hashing (cost factor: 12)\n- Returns JWT token on successful registration\n\n## Results\n- Users can now register via API\n- Passwords securely hashed\n- Email validation prevents invalid entries\n\n## What to Do Next\n- Add email verification flow\n- Implement rate limiting\n- Add unit tests for edge cases",
  "project_dir": "/absolute/path/to/project"
}
```

### UI Features

#### Keyboard Shortcuts
- **Ctrl+Enter**: Submit feedback
- **Ctrl+I**: Improve text with AI
- **Ctrl+V**: Paste images from clipboard
- **Ctrl+S**: Open settings dialog

#### Image Support
1. Copy image to clipboard (screenshot, etc.)
2. Press Ctrl+V in the feedback text area
3. Image appears as thumbnail below text
4. AI can analyze images when improving text

#### AI Improvement
1. Write your feedback
2. Press Ctrl+I or click the sparkle icon
3. AI enhances the text for clarity and professionalism
4. Review and edit the improved version

#### Settings
- **Theme**: Switch between dark and light mode
- **Auto-save**: Automatically save preferences
- **Notification**: Visual confirmation of saved settings

### Response Handling

The AI agent receives the developer's response and can:
- Answer questions directly
- Make requested changes
- Save important feedback as user preferences

Example flow:
```
Developer: "Good work! Can you also add input validation?"
AI: [Makes changes without asking for confirmation]
AI: [Calls ask_to_leader_project with results]
```

## Cursor Window Control

Control Cursor IDE windows programmatically for automation.

### Auto-Stop Mode

Automatically stop Cursor streaming without showing UI:

**.env configuration**:
```bash
APP_AUTO_STOP=true
APP_STOP_DELAY=2
APP_DISABLE_CURSOR_CONTROL=false
```

**How it works**:
1. AI agent completes work
2. Calls `ask_to_leader_project`
3. System automatically focuses Cursor
4. Sends stop hotkey (Ctrl+Alt+B twice + Ctrl+Shift+Backspace)
5. No UI shown, immediate stop

### Manual Control

Test window control manually:

```bash
# Show all Cursor windows with debug info
python focus_cursor.py --debug

# Focus Cursor and send stop hotkey
python focus_cursor.py
```

### Window Detection

The system uses intelligent CWD-based matching:

**Scoring System**:
- **100 points**: Exact CWD folder match (e.g., "my_project")
- **50 points**: Partial match (e.g., "my_project - feature-branch")
- **1 point**: Generic Cursor window

**Example**:
```
Working directory: C:\Users\user\projects\my_app
Cursor windows:
  1. "my_app - main.py" → Score: 100 (exact match)
  2. "other_project - test.py" → Score: 1 (generic)
  
Selected: Window 1 (highest score)
```

### Platform-Specific Behavior

**Windows**:
- Uses pywinauto for window enumeration
- SendKeys for hotkey injection
- Enhanced focus with maximize and bring-to-front

**Linux (X11)**:
- Uses python-xlib for window management
- XTest extension for keyboard events
- Direct X11 protocol communication

**macOS**:
- Uses pyobjc for Cocoa integration
- Quartz events for keyboard simulation
- NSWorkspace for application control

## Configuration Management

### Initialize Agent Files

Create configuration files for AI assistants:

```python
# For Cursor
{
  "tool": "init_agent_files",
  "target_directory": "/path/to/project",
  "config_folder": ".cursor"
}

# For Augment
{
  "tool": "init_agent_files",
  "target_directory": "/path/to/project",
  "config_folder": ".augment"
}

# Custom folder
{
  "tool": "init_agent_files",
  "target_directory": "/path/to/project",
  "config_folder": "config"
}
```

**Created files**:
- `.cursor/commands/.always_call_leader.md`
- `.cursor/rules/always_call_leader.mdc`

### Environment Configuration

Edit `.env` to customize behavior:

```bash
# UI Appearance
APP_DARK_MODE=true              # Dark theme
APP_SHOW_CONTEXT_MODAL=false    # Hide context section by default

# Cursor Control
APP_DISABLE_CURSOR_CONTROL=false  # Enable window control
APP_AUTO_STOP=false               # Manual mode (show UI)
APP_STOP_DELAY=2                  # Wait 2s before stop signal

# Memory System
MEMORY_RAG_TOP_K=5                # Return top 5 results
EMBEDDING_PROVIDER=gemini         # Use Gemini for embeddings

# Embedding Cache
EMBEDDING_CACHE_ENABLED=true      # Enable cache
EMBEDDING_CACHE_MAX_ENTRIES=10000 # Max 10k entries
EMBEDDING_CACHE_TTL_DAYS=30       # 30-day expiration
```

## Best Practices

### For AI Agents

1. **Always retrieve memory first**: Check context before starting work
2. **Save significant changes**: Don't save trivial edits
3. **Use structured reports**: Follow the 5-section format
4. **Show actual code**: Never just reference line numbers
5. **Act on feedback immediately**: Don't ask for confirmation

### For Developers

1. **Provide clear feedback**: Be specific about what needs changing
2. **Use images**: Screenshots help explain UI issues
3. **Save preferences**: Tell the AI your coding standards
4. **Review memory**: Check what the AI has learned
5. **Adjust settings**: Customize theme and behavior

### Memory Management

1. **Descriptive queries**: "JWT token validation bug" not "auth issue"
2. **Include code in descriptions**: Future AI needs context
3. **Categorize correctly**: milestone vs bug_solved vs user_preference
4. **Regular cleanup**: Old memories expire after TTL_DAYS
5. **Monitor cache**: Use `get_embedding_cache_stats` to check performance

## Advanced Usage

### Embedding Cache Statistics

```python
{
  "tool": "get_embedding_cache_stats"
}
```

**Response**:
```
📊 Embedding Cache Statistics

Cache Performance:
  • Hits: 1,234 (82.3%)
  • Misses: 266 (17.7%)
  • Hit Rate: 82.3%

Cache Size:
  • Entries: 1,500 / 10,000
  • File Size: 45.2 MB
  • Evictions: 12
  • Expirations: 5

API Savings:
  • Calls Avoided: 1,234
  • Estimated Cost Savings: $0.12
```

### Custom Embedding Provider

Switch between Gemini and OpenAI:

```bash
# Use OpenAI
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Use Gemini (default)
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your_key
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
```

### Batch Memory Operations

Save multiple memories in sequence:

```python
# After major refactoring
memory_save(milestone, "Refactored database layer...")
memory_save(bug_solved, "Fixed N+1 query issue...")
memory_save(user_preference, "User prefers SQLAlchemy ORM...")
```

### Integration with CI/CD

Use in automated workflows:

```bash
# In CI pipeline
python -c "
from senior_tools import memory_save
memory_save(
    'milestone',
    'Deployed version 2.0 to production',
    '/path/to/project'
)
"
```

---

For more information, see:
- [Installation Guide](INSTALLATION.md)
- [API Reference](API.md)
- [Performance Research](research.md)

