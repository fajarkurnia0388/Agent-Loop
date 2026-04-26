# MCP Connection Error (-32000) - Diagnosis and Fix

## Error Message
```
Tool execution failed: MCP error -32000: Connection closed
```

## Root Cause

The MCP connection closes when `ask_to_leader_project` is called **without the required `project_dir` parameter**.

### What Happens

1. **First call in session**: `ask_to_leader_project` requires `project_dir` parameter
2. **If missing**: Function returns error message instead of raising exception
3. **MCP protocol**: Interprets this as catastrophic failure and closes connection
4. **Result**: Error -32000 "Connection closed"

## The Fix

### Always Pass `project_dir` Parameter

```python
# ✅ CORRECT - Always include project_dir
ask_to_leader_project(
    agent_comment="Your summary here",
    project_dir="C:\\Users\\istiak\\git\\simple_answer"
)

# ❌ WRONG - Missing project_dir causes connection to close
ask_to_leader_project(
    agent_comment="Your summary here"
)
```

### How Session Caching Works

From `senior_tools.py` lines 3796-3808:

```python
global _cached_project_dir

# Use provided project_dir or cached value
if project_dir:
    project_base_dir = Path(project_dir).resolve()
    _cached_project_dir = str(project_base_dir)  # Cache it for entire session
    logger.info(f"✓ Using provided project_dir and cached: {project_base_dir}")
elif _cached_project_dir:
    project_base_dir = Path(_cached_project_dir).resolve()
    logger.info(f"✓ Using cached project_dir from session: {project_base_dir}")
else:
    # No project_dir and no cache - error state
    logger.error("❌ No project_dir provided and no cached value!")
    await ctx.error("❌ AI agent must pass workspace path on first call to ask_to_leader_project")
    return "❌ Error: No project directory provided. AI agent must pass workspace path."
```

**Key Points:**
- First call: MUST include `project_dir`
- Subsequent calls: Can omit `project_dir` (uses cached value)
- Session scope: Cache persists for entire MCP server session
- Server restart: Cache is cleared, must provide `project_dir` again

## Secondary Issue: Embedding Dimension Mismatch

### Symptoms
From logs:
```
WARNING - cosine_similarity:566 - Failed to calculate cosine similarity: 
shapes (3072,) and (1536,) not aligned: 3072 (dim 0) != 1536 (dim 0)
```

### Cause
Memory database contains embeddings from different providers:
- **Gemini**: 3072 dimensions (`gemini-embedding-001`)
- **OpenAI**: 1536 dimensions (`text-embedding-3-small`)

### Impact
- **Does NOT crash MCP connection**
- Only logs warnings
- Returns 0.0 similarity score for mismatched embeddings
- May reduce RAG search quality

### Fix (Optional)
If you want to clean up mixed embeddings:

1. **Find memory entries with embeddings**:
   ```powershell
   Get-ChildItem -Path memory\project_9b9ed463 -Filter *.json
   ```

2. **Remove embedding fields** (they will regenerate with current provider):
   - Edit JSON files in `memory/project_9b9ed463/`
   - Remove `"embedding"` fields from entries
   - Or delete entire project folder to start fresh

3. **Restart MCP server** to regenerate embeddings

## Prevention

### For AI Agents
Always include `project_dir` in first `ask_to_leader_project` call:

```python
# Memory workflow
memory_call(
    project_dir="C:\\Users\\istiak\\git\\simple_answer",
    query="relevant context"
)

# Then call leader with project_dir
ask_to_leader_project(
    agent_comment="Summary of work",
    project_dir="C:\\Users\\istiak\\git\\simple_answer"  # ✅ Required!
)
```

### For Developers
Consider enhancing error handling in `ask_to_leader_project`:

```python
# Instead of returning error message
return "❌ Error: No project directory provided"

# Raise exception to properly signal MCP protocol
raise ValueError("project_dir parameter required on first call")
```

## Verification

Check logs at `logs/senior_tools.log` for:

```
✓ Using provided project_dir and cached: C:\Users\istiak\git\simple_answer
```

If you see:
```
❌ No project_dir provided and no cached value!
```

Then the MCP connection will close with error -32000.

## Summary

| Issue | Cause | Fix |
|-------|-------|-----|
| MCP Connection Closed | Missing `project_dir` parameter | Always pass `project_dir` to `ask_to_leader_project` |
| Embedding Warnings | Mixed Gemini/OpenAI embeddings | Optional: Clean memory database |

**Primary Fix**: Always include `project_dir="C:\\Users\\istiak\\git\\simple_answer"` when calling `ask_to_leader_project`.

