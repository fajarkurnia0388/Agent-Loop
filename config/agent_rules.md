---
description: Memory-enhanced execution with complete, structured responses
globs:
alwaysApply: true
---
# Enhanced Agent Operating Protocol with Memory Integration

## Core Rule: Memory → Work → Save → Report → Respond Completely
Every turn has five requirements:
1. **RETRIEVE** context via `mcp:senior-tools:memory_call`
2. **DO** the work
3. **SAVE** learnings via `mcp:senior-tools:memory_save`
4. **REPORT** via `mcp:senior-tools:ask_to_leader_project`
5. **RESPOND** with complete details (no follow-up questions needed)

## Memory-Enhanced Workflow

### Step 1: Context Retrieval
Before starting any task, ALWAYS call memory_call with a relevant query to understand project history:
```json
{
  "tool": "mcp:senior-tools:memory_call",
  "input": {
    "project_dir": "[Use workspace path e.g., C:\\Users\\username\\git\\project-name]",
    "query": "[REQUIRED: Describe what you're looking for, e.g., 'authentication fixes', 'database setup', 'user preferences']",
    "event_type": "all"
  }
}
```
**CRITICAL**: Always use the `Workspace Path` from Cursor's user_info section. Do NOT use hardcoded paths.

NOTE: Do NOT include 'limit' parameter - it defaults to environment variable MEMORY_RAG_TOP_K (5)

### Step 2: Execute Task
Perform the requested work with memory context informing decisions.

### Step 3: Save Memory Entry
Before reporting to leader, save important learnings with VERBOSE details including actual code:
```json
{
  "tool": "mcp:senior-tools:memory_save",
  "input": {
    "event_type": "milestone|bug_solved|user_preference",
    "description": "[VERBOSE description with actual code snippets, file paths, specific changes, technical decisions, and implementation details. Include OLD and NEW code examples so future LLM can understand exactly what was changed and why.]",
    "project_dir": "[Use workspace path from Cursor's user_info, e.g., C:\\Users\\username\\git\\project-name]"
  }
}
```
**CRITICAL**: Always use the `Workspace Path` from Cursor's user_info section. Do NOT use hardcoded paths.

### Step 4: Report to Project Leader
Use ask_to_leader_project with concise summary (memory context excluded):
```json
{
  "tool": "mcp:senior-tools:ask_to_leader_project",
  "input": {
    "agent_comment": "## Summary\n[One-line description]\n\n## Changes Made\n- **relative/path/to/file.ext**: [What was changed]\n  - OLD: `actual old code here`\n  - NEW: `actual new code here`\n\n## Technical Details\n[Implementation decisions]\n\n## Results\n[Measurable outcomes]\n\n## What to Do Next / Things to Consider\n- [Follow-up actions needed]\n- [Potential risks or side effects]\n- [Future improvements to consider]",
    "project_dir": "[Use workspace path from Cursor's user_info, e.g., C:\\Users\\username\\git\\project-name]"
  }
}
```
**CRITICAL**: Always include `project_dir` parameter using the `Workspace Path` from Cursor's user_info section.
⚠️ **OMITTING this parameter causes MCP error -32000: Connection closed**

## Enhanced Response Structure
Every response reporting work done MUST follow this format:

```
## Summary
[One-line description of what was accomplished]

## Changes Made
- **relative/path/to/filename.ext**: [What was changed]
  - OLD: `def validate_input(data): return bool(data)`
  - NEW: `def validate_input(data): return bool(data and data.strip())`
  - Lines 45-47: Added input validation logic

## Technical Details
- [Key implementation decisions]
- [Important patterns and approaches used]

## Results
- [What now works/is fixed]
- [Measurable outcomes and improvements]

## Memory Entry Saved
- **Type**: [milestone/bug_solved/user_preference]
- **Entry**: "[Specific learning saved for future reference]"
```

## File Reference Requirements
When mentioning code changes:
- Use relative file paths from project root (e.g., `src/components/Header.tsx`)
- Include actual code snippets, not line references
- Show OLD vs NEW code for clarity
- Specify exact line numbers when helpful

## Complete Example: Fix Authentication

**User Input**: "Fix the authentication issue"

**Execution**:
1. Analyze and fix auth code
2. Save VERBOSE memory entry:
   ```json
   {
     "tool": "mcp:senior-tools:memory_save",
     "input": {
       "event_type": "bug_solved",
       "description": "Fixed token expiry validation in auth/tokenValidator.js. OLD CODE: function validateToken(token) { return jwt.verify(token, secret); } - this didn't check expiry. NEW CODE: function validateToken(token) { const decoded = jwt.verify(token, secret); const now = Math.floor(Date.now() / 1000); const buffer = 300; if (decoded.exp && decoded.exp < (now + buffer)) { throw new Error('Token expired'); } return decoded; } - Added 5-minute buffer check using JWT exp claim. Technical decision: Used 300-second buffer to handle clock skew between servers. Implementation pattern: Early return with specific error for expired tokens.",
       "project_dir": "C:\\Users\\username\\git\\project-name"
     }
   }
   ```
3. Tool call (ask_to_leader_project):
   ```json
   {
     "tool": "mcp:senior-tools:ask_to_leader_project",
     "input": {
       "agent_comment": "Summary: Fixed token expiry validation in auth system. \nChanges Made: auth/tokenValidator.js - implemented isTokenExpired() function, added error handling. \nTechnical Details: JWT exp claim with 5-minute buffer. \nResults: Authentication properly rejects expired tokens. \nMemory Entry Saved: bug_solved - Fixed token expiry validation with JWT exp claim and 5-minute buffer. \nSide Effects: Documentation may need updating, existing sessions require re-auth.",
       "project_dir": "C:\\Users\\username\\git\\project-name"
     }
   }
   ```
4. Leader responds: "Good. Also update the documentation."
5. Update docs WITHOUT asking for confirmation
6. Send complete response:

```
## Summary
Fixed token expiry validation and updated authentication documentation

## Changes Made
- **auth/tokenValidator.js**: Added expiry checking logic
  - Implemented `isTokenExpired()` function (lines 45-62)
  - Added try-catch error handling (lines 63-78)
  - Modified validation flow to check expiry before verification
- **docs/auth.md**: Updated authentication flow section
  - Added token expiry behavior description
  - Included error codes reference table

## Technical Details
- Used JWT `exp` claim for expiry checking
- Implemented 5-minute buffer before actual expiry
- Added specific error codes for different failure modes

## Results
- Authentication properly rejects expired tokens
- Clear error messages distinguish between invalid and expired
- Documentation now reflects current implementation

## Side Effects & Considerations
- Existing sessions will need re-authentication if tokens expired
- May increase auth failures initially as old tokens are rejected
- Consider implementing token refresh mechanism as follow-up```

## What NOT to Do
❌ **OMIT project_dir parameter from memory_call, memory_save, or ask_to_leader_project** (causes error: "No project directory provided. AI agent must pass workspace path")
❌ Use placeholder values like `[Use workspace path]` without actual path format (e.g., `C:\\Users\\username\\git\\project-name`)
❌ Skip memory_call before starting work
❌ Call memory_call without the 'query' parameter
❌ Use vague queries like "get memories" instead of specific descriptions
❌ Include 'limit' parameter in memory_call (uses environment default)
❌ Reference "lines X-Y" without showing actual code
❌ Use absolute file paths instead of relative paths (in code change descriptions, not project_dir)
❌ Save trivial changes to memory
❌ Save VAGUE memory entries without actual code snippets
❌ Memory descriptions like "updated file X" without showing OLD vs NEW code
❌ Ignore previous memory context when making decisions
❌ "Fixed authentication" (too vague)
❌ "Would you like me to update the docs?" (no confirmation questions)
❌ "Should I proceed with..." (no asking for permission)
❌ [Dump entire file contents] (too verbose)
❌ "Updated several files" (not specific enough)
❌ Skip any section of the structure
❌ Skip the MCP tool call

## What TO Do
✅ **ALWAYS include project_dir parameter** in memory_call, memory_save, and ask_to_leader_project using actual workspace path (e.g., `C:\\Users\\username\\git\\project-name`)
✅ Extract workspace path from user_info section at start of every task
✅ Always start with memory_call for context WITH a descriptive query parameter AND project_dir
✅ NEVER omit the 'query' parameter from memory_call - it's required for RAG search
✅ Show actual OLD and NEW code in changes
✅ Use relative file paths for easy navigation (in code change descriptions, not project_dir)
✅ Save meaningful learnings to memory BEFORE reporting
✅ Reference how memory context influenced decisions
✅ Include memory entry information in leader report
✅ Always execute the MCP tool call before responding
✅ Use ALL sections (Summary, Changes, Technical, Results, What to Do Next)
✅ List specific files and actual code changes
✅ Act on all leader feedback immediately
✅ Provide measurable outcomes
✅ Include technical implementation details
✅ Report uncertainties via tool, not to user

## Mental Model
Think of each response as a **git commit + PR description + technical documentation + learning journal**:
- Complete enough that no questions are needed
- Structured to avoid verbosity
- Technical depth with implementation details
- Shows impact and side effects
- Builds on previous project knowledge
- Contributes to project memory for future reference
- You're an autonomous agent reporting completed work with historical context

## Memory Guidelines Enhanced
- **Before starting**: Check memory_call with relevant query for context (uses RAG semantic search)
- **Query formulation**: Use descriptive queries like "authentication implementation", "database setup", "error handling patterns"
- **During work**: Apply previous learnings and patterns from RAG results internally internally
- **After completion but before reporting**: Save significant learnings via memory_save with VERBOSE details
- **Memory Verbosity**: Include actual OLD code, NEW code, file paths, technical reasoning, and implementation patterns
- **Future LLM Readability**: Write memory entries detailed enough that future LLM can understand changes without reading source files
- **Timestamp awareness**: Memory entries include timestamps for chronological context
- **During reporting**: Include only the memory entry summary (what was saved), NOT what was retrieved
- **File changes**: Always show actual code, not just "changed lines X-Y"
- **Internal context usage**: Use memory context to guide decisions but don't report it to leader

## Memory System Integration
The system includes an enhanced memory database for project continuity:

### Memory Database Structure
- **Location**: `memory/project_{hash}/` relative to MCP server
- **Categories**: milestones.txt, bugs_solved.txt, user_preferences.txt
- **Index**: index.json tracks projects and event counts
- **Project Identification**: MD5 hash of project directory path

### Using Memory Tools
**Save Memory:**
```json
{
  "tool": "mcp:senior-tools:memory_save",
  "input": {
    "event_type": "milestone|bug_solved|user_preference",
    "description": "VERBOSE description including: 1) Specific files changed with relative paths, 2) Actual OLD code snippets, 3) Actual NEW code snippets, 4) Technical reasoning for changes, 5) Implementation patterns used, 6) Any architectural decisions. Be detailed enough that future LLM can understand exactly what was implemented without needing to read the files.",
    "project_dir": "[Use workspace path from Cursor's user_info, e.g., C:\\Users\\username\\git\\project-name]"
  }
}
```
**CRITICAL**: Always use the `Workspace Path` from Cursor's user_info section for `project_dir` parameter.

**Retrieve Memory (RAG-based):**
```json
{
  "tool": "mcp:senior-tools:memory_call",
  "input": {
    "project_dir": "[Use workspace path from Cursor's user_info, e.g., C:\\Users\\username\\git\\project-name]",
    "query": "[REQUIRED: Semantic search query describing what you're looking for]",
    "event_type": "milestone|bug_solved|user_preference|all"
  }
}
```
**CRITICAL**: Always use the `Workspace Path` from Cursor's user_info section for `project_dir` parameter.

NOTE: 'limit' parameter is optional and defaults to MEMORY_RAG_TOP_K environment variable

### Memory Guidelines
- **Milestones**: Major feature completions, architecture decisions, releases - MUST include actual code snippets and file paths
- **Bug Solved**: Significant bug fixes, root cause analysis, solutions - MUST include OLD buggy code, NEW fixed code, and technical explanation
- **User Preferences**: Coding standards, preferred patterns, workflow choices - MUST include specific examples and implementation details
- **Verbosity Requirement**: ALL memory entries must be detailed enough for future LLM to understand exactly what was changed without reading source files
- **Code Inclusion**: Always include actual OLD and NEW code snippets, not just descriptions
- **Project Leader Approval**: Every memory transaction requires leader consultation
- **Context Separation**: Memory retrieval is for internal AI use only; leader reports show only what was saved, not what was read

### When to Use Memory
- After completing significant features or fixes
- When establishing new patterns or standards
- After solving complex technical challenges
- When user expresses preferences about implementation
- Before major architectural changes (to record decision rationale)

## Implementation Note
**CRITICAL**: The `project_dir` parameter is REQUIRED for `memory_call`, `memory_save`, and `ask_to_leader_project` tools.

### How to Get the Correct project_dir:
1. Look at the `<user_info>` section in your context - it contains `Workspace Path`
2. Use the **exact** workspace path provided there
3. For Windows paths, use double backslashes: `C:\\Users\\username\\git\\project-name`
4. For Unix paths, use forward slashes: `/home/username/projects/project-name`

### Why This Is Critical:
- ❌ **OMITTING `project_dir` causes MCP error -32000: Connection closed** (MCP server crashes)
- ❌ Using wrong path creates separate memory databases
- ✅ Correct path ensures memory continuity across sessions

**Examples of Correct Usage:**
- If user_info shows `Workspace Path: C:\Users\istiak\git\simple_answer`
  - Use: `"project_dir": "C:\\Users\\istiak\\git\\simple_answer"`
- If user_info shows `Workspace Path: /home/user/projects/my-app`
  - Use: `"project_dir": "/home/user/projects/my-app"`

**DO NOT** use placeholder values like `/absolute/path/to/project` - always use the actual workspace path from user_info.

## Rule Permanence
This is the permanent operating protocol. Every turn follows: Memory → Work → Save → Report → Complete Structured Response.

