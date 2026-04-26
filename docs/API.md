# API Reference

Complete reference for all MCP tools provided by Senior Tools.

## Table of Contents
- [memory_save](#memory_save)
- [memory_call](#memory_call)
- [ask_to_leader_project](#ask_to_leader_project)
- [init_agent_files](#init_agent_files)
- [get_embedding_cache_stats](#get_embedding_cache_stats)

---

## memory_save

Save important development events to the project's memory database.

### Signature
```python
async def memory_save(
    event_type: Literal["milestone", "bug_solved", "user_preference"],
    description: str,
    project_dir: str,
    ctx: Context
) -> str
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `event_type` | string | Yes | Type of event: `"milestone"`, `"bug_solved"`, or `"user_preference"` |
| `description` | string | Yes | Detailed description with code snippets, file paths, and technical details |
| `project_dir` | string | Yes | Absolute path to the project root directory |
| `ctx` | Context | Yes | FastMCP context (provided automatically) |

### Event Types

#### milestone
Major feature completions, architecture decisions, releases.

**Example**:
```json
{
  "event_type": "milestone",
  "description": "Implemented real-time chat feature. Files: chat/websocket.py - Added WebSocket handler with Socket.IO. OLD: No real-time communication. NEW: @socketio.on('message') def handle_message(data): emit('message', data, broadcast=True). Supports rooms and private messages. Integrated with Redis for pub/sub across multiple servers.",
  "project_dir": "/home/user/projects/chat_app"
}
```

#### bug_solved
Significant bug fixes with root cause analysis and solutions.

**Example**:
```json
{
  "event_type": "bug_solved",
  "description": "Fixed race condition in payment processing. File: payments/processor.py line 78. OLD: if balance >= amount: deduct(amount) (not atomic). NEW: with transaction.atomic(): balance = F('balance') - amount (database-level atomic operation). Root cause: concurrent requests could overdraw account. Solution: database-level locking with F() expressions. Added test: test_concurrent_payments().",
  "project_dir": "/home/user/projects/payment_system"
}
```

#### user_preference
Coding standards, preferred patterns, workflow choices.

**Example**:
```json
{
  "event_type": "user_preference",
  "description": "User prefers dataclasses over dictionaries for data structures. Example: @dataclass class User: id: int; name: str; email: str instead of user = {'id': 1, 'name': 'John', 'email': 'john@example.com'}. Benefits: type hints, IDE autocomplete, validation. Apply to all new data models.",
  "project_dir": "/home/user/projects/api_server"
}
```

### Returns

Success message with project information:
```
✅ Memory saved successfully!
📁 Project: 9b9ed463 (chat_app)
📝 File: milestones.json
📊 Total events for this project: 42
🗂️ Database location: /path/to/memory
```

### Error Handling

Returns error message if save fails:
```
❌ Failed to save memory entry: [error details]
```

### Best Practices

1. **Be verbose**: Include actual code snippets
2. **Show OLD vs NEW**: Always demonstrate what changed
3. **Include file paths**: Use relative paths from project root
4. **Add technical context**: Explain why changes were made
5. **Include line numbers**: Help locate changes in files

---

## memory_call

Retrieve relevant memory entries using semantic search (RAG).

### Signature
```python
async def memory_call(
    project_dir: str,
    ctx: Context,
    query: str = "",
    event_type: Literal["milestone", "bug_solved", "user_preference", "all"] = "all",
    limit: int = None
) -> str
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_dir` | string | Yes | - | Absolute path to project root |
| `ctx` | Context | Yes | - | FastMCP context (automatic) |
| `query` | string | No | `""` | Semantic search query |
| `event_type` | string | No | `"all"` | Filter by event type |
| `limit` | int | No | `MEMORY_RAG_TOP_K` | Max results to return |

### Query Examples

**Good queries** (specific and descriptive):
- `"JWT authentication implementation with refresh tokens"`
- `"database connection pool memory leak fix"`
- `"user prefers async/await over callbacks"`
- `"React component state management patterns"`

**Bad queries** (too vague):
- `"auth"` → Use "authentication implementation details"
- `"bug"` → Use "specific bug description"
- `"code"` → Use "specific feature or pattern"

### Returns

Formatted memory entries with relevance scores:

```
## 📚 Project Memory: my_project

**Project Hash**: 9b9ed463
**Last Updated**: 2025-10-04T22:55:30
**Search Query**: "authentication implementation"

**Event Summary**:
• Milestone: 15
• Bug Solved: 8
• User Preference: 3

### Most Relevant Memories (Top 5)

**1. 🎯 MILESTONE** (Milestone)
📅 **Time**: 2025-10-01 14:30
🎯 **Relevance**: 0.89
📝 **Details**: Implemented JWT authentication...

**2. 🐛 BUG SOLVED** (Bug Solved)
📅 **Time**: 2025-09-28 10:15
🎯 **Relevance**: 0.76
📝 **Details**: Fixed token expiry validation...
```

### Semantic Search

Uses embeddings for intelligent retrieval:
- Finds conceptually similar memories
- Not just keyword matching
- Understands context and intent
- Ranks by relevance score (0.0 to 1.0)

### API Key Requirement

**Important**: Semantic search requires a valid API key:
- `EMBEDDING_PROVIDER=gemini` requires `GEMINI_API_KEY`
- `EMBEDDING_PROVIDER=openai` requires `OPENAI_API_KEY`

If no API key is configured, `memory_call` will return an error:
```
❌ Failed to retrieve relevant memories: Gemini API key not configured for semantic search
```

### No Query Behavior

If no query provided, returns most recent memories without semantic ranking:
```python
{
  "project_dir": "/path/to/project",
  "query": "",  # Empty query
  "event_type": "all"
}
# Returns: 5 most recent memories sorted by timestamp
```

---

## ask_to_leader_project

Show feedback UI to consult with the project leader.

### Signature
```python
async def ask_to_leader_project(
    agent_comment: str,
    ctx: Context,
    project_dir: str = None
) -> str
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_comment` | string | Yes | Structured report of completed work |
| `ctx` | Context | Yes | FastMCP context (automatic) |
| `project_dir` | string | No | Project path (cached after first call) |

### Agent Comment Format

Use this 5-section structure:

```markdown
## Summary
[One-line description of what was accomplished]

## Changes Made
- **relative/path/to/file.ext**: [What was changed]
  - OLD: `original code here`
  - NEW: `updated code here`
  - Lines 45-47: [Description of change]

## Technical Details
- [Key implementation decisions]
- [Important patterns and approaches used]
- [Dependencies or libraries added]

## Results
- [What now works/is fixed]
- [Measurable outcomes and improvements]
- [Performance metrics if applicable]

## What to Do Next / Things to Consider
- [Follow-up actions needed]
- [Potential risks or side effects]
- [Future improvements to consider]
```

### Example

```python
{
  "agent_comment": """## Summary
Implemented user authentication with JWT tokens

## Changes Made
- **api/auth.py**: Added authentication endpoints
  - OLD: No authentication system
  - NEW: 
    ```python
    @app.post('/login')
    async def login(credentials: LoginRequest):
        user = await verify_credentials(credentials)
        token = generate_jwt(user.id)
        return {'token': token, 'expires_in': 86400}
    ```
  - Lines 15-25: Login endpoint with JWT generation
  - Lines 30-40: Token verification middleware

- **models/user.py**: Added password hashing
  - OLD: Passwords stored in plain text
  - NEW: `password_hash = bcrypt.hashpw(password, bcrypt.gensalt(12))`
  - Uses bcrypt with cost factor 12

## Technical Details
- JWT tokens with 24-hour expiration
- Bcrypt for password hashing (cost: 12)
- Refresh token support (7-day expiration)
- Token stored in HTTP-only cookie

## Results
- Users can now log in securely
- Passwords properly hashed in database
- Token-based authentication working
- All existing tests passing

## What to Do Next / Things to Consider
- Add email verification flow
- Implement password reset functionality
- Add rate limiting to prevent brute force
- Consider adding 2FA support
- Update API documentation""",
  "project_dir": "/home/user/projects/api_server"
}
```

### UI Features

The feedback dialog provides:
- **Text editor** with syntax highlighting
- **Image support** (Ctrl+V to paste)
- **AI improvement** (Ctrl+I)
- **Settings** (Ctrl+S)
- **Submit** (Ctrl+Enter)

### Returns

Leader's response with instructions:

```
Leader's response: Good work! Can you also add rate limiting?

Complete this turn's transaction by calling mcp:senior-tools:ask_to_leader_project with a comprehensive report using this structure:

## Summary
[One-line description]

## Changes Made
[Detailed changes with code]

## Technical Details
[Implementation decisions]

## Results
[Outcomes and improvements]

## What to Do Next
[Follow-up actions]
```

### Auto-Stop Mode

If `APP_AUTO_STOP=true`, bypasses UI and automatically:
1. Focuses Cursor window
2. Sends stop hotkey
3. Returns immediately

---

## init_agent_files

Initialize agent configuration files in a project.

### Signature
```python
async def init_agent_files(
    target_directory: str,
    config_folder: str,
    ctx: Context
) -> str
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target_directory` | string | Yes | Directory where config files should be created |
| `config_folder` | string | Yes | Config folder name (`.cursor`, `.augment`, etc.) |
| `ctx` | Context | Yes | FastMCP context (automatic) |

### Supported Folders

#### .cursor
Creates:
- `.cursor/commands/.always_call_leader.md`
- `.cursor/rules/always_call_leader.mdc`

#### .augment
Creates:
- `.augment/rules/always_call_leader.md`

#### Custom
Creates:
- `{folder}/always_call_leader.md`
- `{folder}/agent_rules.md`

### Example

```python
{
  "target_directory": "/home/user/projects/my_app",
  "config_folder": ".cursor"
}
```

### Returns

```
✅ Agent files initialized successfully in .cursor/
Created: .cursor/commands/.always_call_leader.md, .cursor/rules/always_call_leader.mdc
```

Or if files exist:
```
✅ All agent files already exist with correct content in .cursor/
```

---

## get_embedding_cache_stats

Get detailed statistics about the embedding cache.

### Signature
```python
async def get_embedding_cache_stats(ctx: Context) -> str
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ctx` | Context | Yes | FastMCP context (automatic) |

### Returns

Detailed cache statistics:

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
  • Provider: gemini
```

### Use Cases

- Monitor cache performance
- Optimize cache settings
- Track API cost savings
- Debug cache issues

### Cache Configuration

Controlled by environment variables:
```bash
EMBEDDING_CACHE_ENABLED=true
EMBEDDING_CACHE_MAX_ENTRIES=10000
EMBEDDING_CACHE_TTL_DAYS=30
```

---

## Error Handling

All tools return error messages in a consistent format:

```
❌ Failed to [operation]: [error details]
```

Common errors:
- **Invalid project_dir**: Path doesn't exist
- **Missing API key**: `Gemini API key not configured for semantic search` or `OpenAI API key not configured for semantic search`
- **Permission denied**: Can't write to memory directory
- **Invalid event_type**: Must be milestone, bug_solved, or user_preference
- **Cache disabled without API key**: Embedding cache must be enabled OR valid API key configured

---

## Rate Limits

### Google Gemini
- Free tier: 60 requests/minute
- Embedding cache reduces API calls by ~80%

### OpenAI
- Depends on your plan
- text-embedding-3-small: $0.00002 per 1K tokens

---

For more information, see:
- [Usage Guide](USAGE.md)
- [Installation Guide](INSTALLATION.md)
- [Main README](../README.md)

