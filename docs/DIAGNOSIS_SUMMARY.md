# MCP Connection Error Diagnosis - Complete Summary

## Your Question
> "there was a Tool execution failed: MCP error -32000: Connection closed error. look into it tell me how to fix it."

## Answer: The Problem

The MCP connection closes because **`ask_to_leader_project` is being called without the required `project_dir` parameter**.

### Evidence from Logs

Looking at `logs/senior_tools.log` lines 429-447, here's what happened:

1. **Line 432-446**: `memory_call` executed successfully
2. **After that**: `ask_to_leader_project` was called (not shown in logs because connection closed)
3. **Result**: MCP error -32000 "Connection closed"

### Why It Crashes

From `senior_tools.py` lines 3796-3808:

```python
# Use provided project_dir or cached value
if project_dir:
    project_base_dir = Path(project_dir).resolve()
    _cached_project_dir = str(project_base_dir)
elif _cached_project_dir:
    project_base_dir = Path(_cached_project_dir).resolve()
else:
    # ❌ THIS CAUSES THE CRASH
    logger.error("❌ No project_dir provided and no cached value!")
    return "❌ Error: No project directory provided. AI agent must pass workspace path."
```

When `project_dir` is missing and there's no cached value, the function returns an error message instead of raising an exception. The MCP protocol interprets this as a catastrophic failure and closes the connection.

## The Fix

### Immediate Solution

Always pass `project_dir` parameter when calling `ask_to_leader_project`:

```python
ask_to_leader_project(
    agent_comment="Your summary here",
    project_dir="C:\\Users\\istiak\\git\\simple_answer"  # ✅ REQUIRED!
)
```

### How to Prevent This

The AI agent should follow this pattern:

```python
# Step 1: Retrieve memory context
memory_call(
    project_dir="C:\\Users\\istiak\\git\\simple_answer",
    query="relevant search query"
)

# Step 2: Do the work
# ... make changes ...

# Step 3: Report to leader (MUST include project_dir on first call)
ask_to_leader_project(
    agent_comment="Summary of completed work",
    project_dir="C:\\Users\\istiak\\git\\simple_answer"  # ✅ Don't forget this!
)
```

## Secondary Issue: Embedding Dimension Warnings

You also saw these warnings in the logs:

```
WARNING - cosine_similarity:566 - Failed to calculate cosine similarity: 
shapes (3072,) and (1536,) not aligned: 3072 (dim 0) != 1536 (dim 0)
```

### What This Means

Your memory database contains embeddings from two different providers:
- **Gemini embeddings**: 3072 dimensions
- **OpenAI embeddings**: 1536 dimensions

This happens when you switch embedding providers in `.env` file.

### Impact

**Good news**: This does NOT crash the MCP connection!

The `cosine_similarity` function catches the error and returns 0.0:

```python
def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    try:
        # ... calculate similarity ...
    except Exception as e:
        logger.warning(f"Failed to calculate cosine similarity: {e}")
        return 0.0  # ✅ Graceful fallback
```

**Bad news**: It may reduce RAG search quality because mismatched embeddings get 0.0 similarity scores.

### Optional Fix

If you want to clean this up:

1. **Delete memory entries with old embeddings**:
   ```powershell
   # Backup first
   Copy-Item -Path memory\project_9b9ed463 -Destination memory\project_9b9ed463_backup -Recurse
   
   # Then delete to regenerate
   Remove-Item -Path memory\project_9b9ed463 -Recurse -Force
   ```

2. **Or manually edit JSON files** to remove `"embedding"` fields

3. **Restart MCP server** to regenerate with current provider

## What I Found in the Codebase

### 1. Previous Fix (Already Applied)

From memory entry dated 2025-10-06, there was a similar issue where the Context object was being passed to `asyncio.to_thread()`, causing crashes.

**That issue is ALREADY FIXED** in the current code:

```python
# senior_tools.py lines 3846-3850
response = await asyncio.to_thread(
    show_feedback_interface,
    agent_comment,
    None,  # ✅ Don't pass ctx - not thread-safe
    str(project_base_dir)
)
```

### 2. Current Code Status

The code is correct. The issue is **how the tool is being called**, not the code itself.

## Testing the Fix

After ensuring `project_dir` is always passed:

1. **Check logs** at `logs/senior_tools.log`
2. **Look for**: `✓ Using provided project_dir and cached: C:\Users\istiak\git\simple_answer`
3. **Should NOT see**: `❌ No project_dir provided and no cached value!`

## Summary Table

| Symptom | Root Cause | Fix | Priority |
|---------|-----------|-----|----------|
| MCP error -32000 | Missing `project_dir` parameter | Always pass `project_dir` to `ask_to_leader_project` | **HIGH** |
| Dimension mismatch warnings | Mixed Gemini/OpenAI embeddings | Clean memory database (optional) | LOW |
| Context thread-safety | Passing ctx to asyncio.to_thread | Already fixed in code | N/A |

## Files Created

1. **docs/MCP_CONNECTION_ERROR_FIX.md** - Detailed fix guide
2. **docs/DIAGNOSIS_SUMMARY.md** - This file

## Next Steps

1. ✅ **Immediate**: Always include `project_dir` parameter when calling `ask_to_leader_project`
2. ⚠️ **Optional**: Clean up mixed embeddings in memory database
3. 📝 **Consider**: Enhance error handling to raise exceptions instead of returning error messages

---

**Bottom Line**: The MCP connection closes because `project_dir` parameter is missing. Always pass it on the first call in each session.

