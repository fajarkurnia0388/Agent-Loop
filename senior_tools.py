# CRITICAL: Import COM initialization FIRST before anything else
# This ensures clipboard operations work correctly on Windows
from src import com_init

from pathlib import Path
from fastmcp import FastMCP, Context
from datetime import datetime
from typing import Literal, Dict, Any, List, Tuple
import sys
import os
import json
import uuid
import hashlib
import re
import base64
import time
from dotenv import load_dotenv
from src.image_handler import image_manager
import logging
import numpy as np
import openai
import warnings
import platform

# Suppress warning noise before importing PyQt6
warnings.simplefilter("ignore", FutureWarning)
warnings.filterwarnings(
    "ignore", message=".*sipPyTypeDict.*", category=DeprecationWarning
)

from PIL import Image

# Modern Qt6 imports for glass morphism interface (explicit, preserve lazy in-function imports)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QLabel,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QTextEdit,
    QTextBrowser,
    QCheckBox,
    QPushButton,
    QToolButton,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QEvent, QTimer, QRectF
from PyQt6.QtGui import (
    QKeySequence,
    QPainter,
    QPainterPath,
    QRegion,
    QShortcut,
    QAction,
)

import threading
import asyncio
import tempfile

# Import playsound for notification sounds
try:
    from playsound import playsound

    HAS_PLAYSOUND = True
except ImportError:
    HAS_PLAYSOUND = False

# Import focus_cursor functionality
try:
    from src.focus_cursor import (
        focus_cursor_and_send_hotkey,
        find_cursor_windows,
        focus_and_send_stop_hotkey_to_any,
    )

    HAS_FOCUS_CURSOR = True
except ImportError:
    HAS_FOCUS_CURSOR = False

# Configuration constant for focus_cursor functionality

# Global cache for project directory (persists throughout MCP server session)
_cached_project_dir: str = None


def play_notification_sound():
    """Play only sounds/notification.wav if present; otherwise do nothing.

    Resolves the WAV path relative to this module so it works regardless of the
    current working directory when invoked via MCP.
    """
    import time

    try:
        module_dir = Path(__file__).resolve().parent
        sound_path = module_dir / "sounds" / "notification.wav"
        if not sound_path.exists():
            try:
                logger.warning(f"Notification sound not found at: {sound_path}")
            except Exception:
                pass
            return False
        if platform.system() == "Windows":
            try:
                import winsound  # type: ignore

                winsound.PlaySound(str(sound_path), winsound.SND_FILENAME)
                return True
            except Exception:
                pass
        if HAS_PLAYSOUND:
            try:
                playsound(str(sound_path), block=False)
                time.sleep(1.5)
                return True
            except Exception:
                return False
        return False
    except Exception as e:
        logger.warning(f"Failed to play notification sound: {e}")
        return False


def play_notification_sound_threaded():
    """Play notification sound in a separate thread to avoid blocking UI"""

    def sound_worker():
        try:
            result = play_notification_sound()
            if result:
                logger.info("Threaded notification sound played successfully")
            else:
                logger.warning("Threaded notification sound failed to play")
        except Exception as e:
            logger.error(f"Error in threaded sound playback: {e}")

    # Create and start the sound thread
    sound_thread = threading.Thread(target=sound_worker, daemon=True)
    sound_thread.start()
    logger.debug("Notification sound thread started")


# Load environment variables from .env
# Use absolute path based on module location to ensure .env is loaded from MCP server directory
_mcp_server_dir = Path(__file__).parent.absolute()
_env_file_path = _mcp_server_dir / ".env"
load_dotenv(dotenv_path=_env_file_path)

# RAG system configuration
MEMORY_RAG_TOP_K = int(os.getenv("MEMORY_RAG_TOP_K", "5"))
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
genai = None

# Embedding cache configuration
EMBEDDING_CACHE_MAX_ENTRIES = max(
    1, int(os.getenv("EMBEDDING_CACHE_MAX_ENTRIES", "10000"))
)
EMBEDDING_CACHE_ENABLED = os.getenv("EMBEDDING_CACHE_ENABLED", "true").lower() == "true"
EMBEDDING_CACHE_TTL_DAYS = max(
    1, int(os.getenv("EMBEDDING_CACHE_TTL_DAYS", "30"))
)  # Cache entries expire after N days

# Initialize clients
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY


async def get_openai_embedding(text: str) -> List[float]:
    """Get embedding from OpenAI API"""
    try:
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")

        logger.info(f"Generating OpenAI embedding for text (length: {len(text)})")

        response = openai.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=text)

        embedding = response.data[0].embedding
        logger.info(f"Generated embedding with {len(embedding)} dimensions")
        return embedding

    except Exception as e:
        logger.error(f"Failed to generate OpenAI embedding: {e}")
        raise


async def get_gemini_embedding(text: str) -> List[float]:
    """Get embedding from Google Gemini API"""
    try:
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not configured")

        logger.info(f"Generating Gemini embedding for text (length: {len(text)})")

        # Lazy import to avoid startup warnings and subprocess noise
        global genai
        if genai is None:
            import google.generativeai as genai_module

            genai = genai_module
            genai.configure(api_key=GEMINI_API_KEY)

        # Use Gemini's embedding API
        result = genai.embed_content(
            model=f"models/{GEMINI_EMBEDDING_MODEL}",
            content=text,
            task_type="retrieval_document",
        )

        embedding = result["embedding"]
        logger.info(f"Generated embedding with {len(embedding)} dimensions")
        return embedding

    except Exception as e:
        logger.error(f"Failed to generate Gemini embedding: {e}")
        raise


async def get_embedding(text: str) -> List[float]:
    """Get embedding using the configured provider"""
    if EMBEDDING_PROVIDER == "openai":
        return await get_openai_embedding(text)
    elif EMBEDDING_PROVIDER == "gemini":
        return await get_gemini_embedding(text)
    else:
        # Default fallback
        if GEMINI_API_KEY:
            return await get_gemini_embedding(text)
        elif OPENAI_API_KEY:
            return await get_openai_embedding(text)
        else:
            raise ValueError("No embedding provider configured")


def _normalize_text_for_cache(text: str) -> str:
    """
    Normalize text for better cache hit rates
    - Strips leading/trailing whitespace
    - Collapses multiple whitespace into single space
    - Preserves case (embeddings may be case-sensitive for proper nouns)
    """
    return " ".join(text.strip().split())


def _is_cache_entry_expired(entry: dict, ttl_days: int) -> bool:
    """Check if a cache entry has exceeded its TTL"""
    try:
        timestamp = datetime.fromisoformat(entry.get("timestamp", ""))
        age = datetime.now() - timestamp
        # Convert TTL days to seconds for sub-day precision
        # Use > (not >=) so entries are valid FOR the TTL duration, expire AFTER
        # TTL=0 means entries expire immediately (any age > 0 seconds)
        ttl_seconds = ttl_days * 86400  # 24 * 60 * 60
        return age.total_seconds() > ttl_seconds
    except (ValueError, TypeError):
        # If timestamp is invalid, consider it expired
        return True


def _compress_embedding(embedding: List[float]) -> List[float]:
    """
    Store embedding as float32 list for JSON serialization
    Note: Removed base64 encoding to reduce 33% size overhead
    """
    # Convert to float32 for consistent precision and smaller size
    arr = np.array(embedding, dtype=np.float32)
    return arr.tolist()


def _decompress_embedding(compressed: List[float]) -> List[float]:
    """
    Decompress embedding (now just returns the list)
    Kept for backward compatibility with old cache format
    """
    return compressed


def _atomic_write_json(file_path: Path, data: dict):
    """
    Atomically write JSON data to file using temp file + rename
    Prevents corruption on crash/interrupt (H3 fix)
    """
    try:
        # Write to temporary file first
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp"
        )

        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename (overwrites existing file)
            os.replace(temp_path, file_path)
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except:
                pass
            raise
    except Exception as e:
        logger.error(f"Atomic write failed: {e}")
        raise


# Global cache statistics with thread safety
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "evictions": 0,
    "expirations": 0,
    "total_size_bytes": 0,
}
_cache_stats_lock = threading.Lock()
_cache_file_lock = asyncio.Lock()


async def get_embedding_with_cache(text: str) -> List[float]:
    """
    Get embedding with persistent file cache

    Features:
    - Text normalization for better hit rates
    - TTL-based expiration
    - LRU eviction when cache is full
    - Thread-safe with asyncio.Lock
    - Atomic writes with temp file
    - SHA-256 cache keys (collision-resistant)
    - Cache statistics tracking

    Cache structure:
    {
        "cache_key_hash": {
            "text": "original text",
            "embedding": [0.1, 0.2, ...],
            "provider": "gemini",
            "timestamp": "2025-10-04T21:30:00",
            "last_accessed": "2025-10-04T21:30:00",
            "hits": 5
        },
        "_stats": {
            "hits": 100,
            "misses": 20,
            "evictions": 5,
            "expirations": 3
        }
    }
    """
    if not EMBEDDING_CACHE_ENABLED:
        return await get_embedding(text)

    # Use asyncio lock to prevent race conditions (C1 fix)
    async with _cache_file_lock:
        try:
            # Normalize text for better cache hit rate
            normalized_text = _normalize_text_for_cache(text)

            # Generate cache key using SHA-256 (C3 fix - collision-resistant)
            cache_key = hashlib.sha256(normalized_text.encode()).hexdigest()

            # Define cache file path
            memory_base_dir = Path(__file__).parent / "memory"
            memory_base_dir.mkdir(exist_ok=True)
            cache_file = memory_base_dir / "embedding_cache.json"

            # Load existing cache
            cache_data = {}
            if cache_file.exists():
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        # Load persisted stats only on first load (M3 fix)
                        if (
                            "_stats" in cache_data
                            and _cache_stats["hits"] == 0
                            and _cache_stats["misses"] == 0
                        ):
                            with _cache_stats_lock:
                                _cache_stats.update(cache_data["_stats"])
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to load cache file, starting fresh: {e}")
                    cache_data = {}

            # Check for cache hit
            if cache_key in cache_data:
                cache_entry = cache_data[cache_key]

                # Check if entry has expired
                if _is_cache_entry_expired(cache_entry, EMBEDDING_CACHE_TTL_DAYS):
                    logger.info(
                        f"Cache entry expired (key: {cache_key[:8]}..., age: {EMBEDDING_CACHE_TTL_DAYS}+ days)"
                    )
                    del cache_data[cache_key]
                    with _cache_stats_lock:
                        _cache_stats["expirations"] += 1
                else:
                    # Valid cache hit - update metadata but defer write (H1 fix)
                    cache_entry["hits"] = cache_entry.get("hits", 0) + 1
                    cache_entry["last_accessed"] = datetime.now().isoformat()

                    with _cache_stats_lock:
                        _cache_stats["hits"] += 1

                    # Decompress embedding (backward compatible)
                    if "embedding_compressed" in cache_entry:
                        embedding = _decompress_embedding(
                            cache_entry["embedding_compressed"]
                        )
                    elif "embedding" in cache_entry:
                        embedding = cache_entry["embedding"]
                    else:
                        # Corrupted entry, treat as miss
                        logger.warning(
                            f"Cache entry missing embedding data (key: {cache_key[:8]}...)"
                        )
                        del cache_data[cache_key]
                        with _cache_stats_lock:
                            _cache_stats["misses"] += 1
                        embedding = await get_embedding(text)
                        # Continue to save new entry below

                    # Only write to disk every 10 hits to reduce I/O (H1 fix)
                    if cache_entry["hits"] % 10 == 0:
                        cache_data["_stats"] = dict(_cache_stats)
                        _atomic_write_json(cache_file, cache_data)

                    with _cache_stats_lock:
                        hit_rate = (
                            _cache_stats["hits"]
                            / (_cache_stats["hits"] + _cache_stats["misses"])
                            * 100
                            if (_cache_stats["hits"] + _cache_stats["misses"]) > 0
                            else 0
                        )
                    logger.info(
                        f"Embedding cache HIT (key: {cache_key[:8]}..., hits: {cache_entry['hits']}, hit_rate: {hit_rate:.1f}%)"
                    )
                    return embedding

            # Cache miss - generate embedding
            with _cache_stats_lock:
                _cache_stats["misses"] += 1
            logger.info(
                f"Embedding cache MISS (key: {cache_key[:8]}...) - generating new embedding"
            )
            embedding = await get_embedding(text)

            # Clean expired entries before checking size limit
            expired_keys = [
                key
                for key, entry in cache_data.items()
                if key != "_stats"
                and _is_cache_entry_expired(entry, EMBEDDING_CACHE_TTL_DAYS)
            ]
            for expired_key in expired_keys:
                del cache_data[expired_key]
                with _cache_stats_lock:
                    _cache_stats["expirations"] += 1

            if expired_keys:
                logger.info(f"Removed {len(expired_keys)} expired cache entries")

            # Check cache size limit and perform LRU eviction if needed
            cache_entries_count = len([k for k in cache_data.keys() if k != "_stats"])
            if cache_entries_count >= EMBEDDING_CACHE_MAX_ENTRIES:
                logger.info(
                    f"Cache size limit reached ({cache_entries_count}/{EMBEDDING_CACHE_MAX_ENTRIES}), performing LRU eviction"
                )

                # Sort by last_accessed timestamp (oldest first) - M4 acknowledged but acceptable
                sorted_entries = sorted(
                    [(k, v) for k, v in cache_data.items() if k != "_stats"],
                    key=lambda x: x[1].get("last_accessed", x[1].get("timestamp", "")),
                )

                # Remove oldest 10% of entries
                eviction_percentage = 0.1  # L1 fix - named constant
                num_to_remove = max(
                    1, int(EMBEDDING_CACHE_MAX_ENTRIES * eviction_percentage)
                )
                for old_key, _ in sorted_entries[:num_to_remove]:
                    del cache_data[old_key]
                    with _cache_stats_lock:
                        _cache_stats["evictions"] += 1

                logger.info(
                    f"Evicted {num_to_remove} old cache entries, new size: {len(cache_data) - 1}"
                )

            # Store embedding (H4 fix - removed base64 overhead)
            embedding_compressed = _compress_embedding(embedding)

            # Add new entry to cache
            text_preview_length = 200  # L1 fix - named constant
            cache_data[cache_key] = {
                "text": text[:text_preview_length],  # Store first N chars for debugging
                "embedding": embedding_compressed,
                "provider": EMBEDDING_PROVIDER,
                "timestamp": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
                "hits": 0,
            }

            # Update stats
            with _cache_stats_lock:
                cache_data["_stats"] = dict(_cache_stats)

            # Calculate and update total size
            try:
                with _cache_stats_lock:
                    _cache_stats["total_size_bytes"] = (
                        cache_file.stat().st_size if cache_file.exists() else 0
                    )
            except Exception as size_error:
                logger.warning(f"Failed to calculate cache size: {size_error}")

            # Save updated cache with atomic write (H3 fix)
            _atomic_write_json(cache_file, cache_data)

            with _cache_stats_lock:
                hit_rate = (
                    _cache_stats["hits"]
                    / (_cache_stats["hits"] + _cache_stats["misses"])
                    * 100
                    if (_cache_stats["hits"] + _cache_stats["misses"]) > 0
                    else 0
                )
            logger.info(
                f"Saved embedding to cache (total entries: {len(cache_data) - 1}, hit_rate: {hit_rate:.1f}%)"
            )
            return embedding

        except Exception as e:
            logger.error(
                f"Cache operation failed, falling back to direct API call: {e}"
            )
            # M2 fix - log error but don't alert user for single failures
            return await get_embedding(text)


def get_cache_statistics_internal() -> dict:
    """
    Get detailed embedding cache statistics (internal function)

    Returns:
        dict with cache statistics
    """
    try:
        memory_base_dir = Path(__file__).parent / "memory"
        cache_file = memory_base_dir / "embedding_cache.json"

        # Get file size
        size_bytes = cache_file.stat().st_size if cache_file.exists() else 0
        size_mb = size_bytes / (1024 * 1024)

        # Load cache to count entries
        total_entries = 0
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    total_entries = len([k for k in cache_data.keys() if k != "_stats"])
            except Exception as load_error:
                logger.warning(f"Failed to load cache for stats: {load_error}")

        # Calculate statistics with thread safety
        with _cache_stats_lock:
            total_requests = _cache_stats["hits"] + _cache_stats["misses"]
            hit_rate = (
                (_cache_stats["hits"] / total_requests * 100)
                if total_requests > 0
                else 0
            )

            # Cost estimation (Gemini: free, OpenAI: ~$0.0001 per embedding) - L1 fix
            openai_cost_per_embedding = 0.0001
            cost_per_embedding = (
                openai_cost_per_embedding if EMBEDDING_PROVIDER == "openai" else 0.0
            )
            estimated_savings = _cache_stats["hits"] * cost_per_embedding

            return {
                "hits": _cache_stats["hits"],
                "misses": _cache_stats["misses"],
                "hit_rate": round(hit_rate, 2),
                "total_entries": total_entries,
                "evictions": _cache_stats["evictions"],
                "expirations": _cache_stats["expirations"],
                "size_mb": round(size_mb, 2),
                "size_bytes": size_bytes,
                "estimated_api_calls_saved": _cache_stats["hits"],
                "estimated_cost_savings_usd": round(estimated_savings, 4),
                "max_entries": EMBEDDING_CACHE_MAX_ENTRIES,
                "ttl_days": EMBEDDING_CACHE_TTL_DAYS,
                "enabled": EMBEDDING_CACHE_ENABLED,
                "provider": EMBEDDING_PROVIDER,
            }

    except Exception as e:
        logger.error(f"Failed to get cache statistics: {e}")
        return {
            "error": str(e),
            "hits": _cache_stats.get("hits", 0),
            "misses": _cache_stats.get("misses", 0),
        }


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    try:
        # Convert to numpy arrays
        a = np.array(vec1)
        b = np.array(vec2)

        # Calculate cosine similarity
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = dot_product / (norm_a * norm_b)
        return float(similarity)

    except Exception as e:
        logger.warning(f"Failed to calculate cosine similarity: {e}")
        return 0.0


# ============================================================================
# COMPLETE LOGGING SYSTEM
# ============================================================================


class FlushingFileHandler(logging.FileHandler):
    """Custom FileHandler that flushes after every log entry

    CRITICAL for multi-instance MCP servers:
    - Prevents buffered logs from being lost if process crashes
    - Ensures logs from multiple instances are written immediately
    - Avoids log interleaving issues in concurrent writes
    """

    def emit(self, record):
        """Emit a record and immediately flush to disk"""
        super().emit(record)
        self.flush()


def setup_logging():
    """Configure the logging system for senior_tools

    Uses absolute path based on module location to ensure logs are saved
    in the MCP server's directory, not the client's workspace directory.

    MULTI-INSTANCE SUPPORT:
    - Includes process ID in logs to distinguish between multiple MCP server instances
    - Forces immediate flush after each log to prevent buffering issues
    - Uses UTF-8 encoding with error handling for special characters
    """
    import os

    # Resolve log directory relative to this module's location (MCP server directory)
    # This ensures logs are saved in the correct location regardless of CWD
    mcp_server_dir = Path(__file__).parent.absolute()
    log_dir = mcp_server_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "senior_tools.log"

    # Get process ID for multi-instance identification
    process_id = os.getpid()

    # Check if senior_tools.log handler already exists to avoid duplicates
    root_logger = logging.getLogger()
    senior_tools_handler_exists = False
    for handler in root_logger.handlers:
        if hasattr(handler, "baseFilename") and Path(handler.baseFilename) == log_file:
            senior_tools_handler_exists = True
            break

    if not senior_tools_handler_exists:
        # Add our handlers to the root logger
        # ENHANCED: Use FlushingFileHandler for immediate writes (multi-instance safe)
        file_handler = FlushingFileHandler(
            log_file, mode="a", encoding="utf-8", delay=False
        )
        file_handler.setLevel(logging.DEBUG)

        # ENHANCED: Include process ID to distinguish multiple instances
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - PID:%(process)d - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
            )
        )
        root_logger.addHandler(file_handler)

        # Add console handler only if no StreamHandler exists
        has_stream_handler = any(
            isinstance(h, logging.StreamHandler) and not hasattr(h, "baseFilename")
            for h in root_logger.handlers
        )
        if not has_stream_handler:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - PID:%(process)d - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
                )
            )
            root_logger.addHandler(console_handler)

        # Set root logger level
        root_logger.setLevel(logging.DEBUG)

        # ENHANCED: Force flush after each log entry for multi-instance safety
        for handler in root_logger.handlers:
            if hasattr(handler, "setStream"):
                # Ensure stream is flushed immediately
                handler.flush()

    logger = logging.getLogger(__name__)
    logger.info(f"Logger configured successfully - File: {log_file}")
    logger.info(f"MCP server directory: {mcp_server_dir}")
    logger.info(f"Current working directory: {Path.cwd()}")
    logger.info(f"Process ID: {process_id} (for multi-instance tracking)")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {platform.system()} {platform.release()}")
    return logger


# Initialize logger
logger = setup_logging()

# ============================================================================
# CURSOR CONFIGURATION AUTO-SETUP
# ============================================================================


def setup_cursor_config_files(target_dir: str = None):
    """
    Automatically setup Cursor configuration files when MCP server starts.
    Creates .cursor/commands/.always_call_leader.md and .cursor/rules/always_call_leader.mdc

    Args:
        target_dir: Optional target directory. If None, tries to detect Cursor's workspace.
    """
    try:
        logger.info("Setting up Cursor configuration files...")

        # Determine the target directory
        if target_dir:
            base_dir = Path(target_dir)
            logger.info(f"Using specified target directory: {base_dir}")
        else:
            # Try to detect Cursor's workspace directory
            # Method 1: Check if we're in a different directory than the MCP server location
            mcp_server_dir = Path(__file__).parent.absolute()
            current_dir = Path.cwd()

            logger.info(f"MCP server directory: {mcp_server_dir}")
            logger.info(f"Current working directory: {current_dir}")

            # If current directory is different from MCP server location, use current
            if current_dir != mcp_server_dir:
                base_dir = current_dir
                logger.info(f"Using current working directory as workspace: {base_dir}")
            else:
                # Fallback: Use current directory (MCP server location)
                base_dir = current_dir
                logger.info(f"Using MCP server directory as default: {base_dir}")

        # Define the .cursor directory structure
        cursor_dir = base_dir / ".cursor"
        commands_dir = cursor_dir / "commands"
        rules_dir = cursor_dir / "rules"

        # Create directories if they don't exist
        commands_dir.mkdir(parents=True, exist_ok=True)
        rules_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created .cursor directory structure in: {cursor_dir}")

        # Define file paths
        command_file = commands_dir / ".always_call_leader.md"
        rules_file = rules_dir / "always_call_leader.mdc"

        # Content for the command file
        command_content = "Complete this turn's transaction by calling mcp:senior-tools:ask_to_leader_project with: '[What you did]: [Result]. [Any risks/follow-ups]'"

        # Load rules content from agent_rules.md
        try:
            rules_path = Path(__file__).parent / "config" / "agent_rules.md"
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_content = f.read()

            if not rules_content:
                logger.error("❌ Could not load rules content from agent_rules.md")
                return False

            logger.info(
                "✅ Successfully loaded rules content from config/agent_rules.md"
            )

        except Exception as e:
            logger.error(f"❌ Error loading rules content from agent_rules.md: {e}")
            return False

        # Check and create/update command file
        command_updated = False
        if not command_file.exists():
            with open(command_file, "w", encoding="utf-8") as f:
                f.write(command_content)
            logger.info(f"Created command file: {command_file}")
            command_updated = True
        else:
            # Check if content matches
            with open(command_file, "r", encoding="utf-8") as f:
                existing_content = f.read().strip()
            if existing_content != command_content:
                with open(command_file, "w", encoding="utf-8") as f:
                    f.write(command_content)
                logger.info(f"Updated command file: {command_file}")
                command_updated = True
            else:
                logger.info(
                    f"Command file already exists with correct content: {command_file}"
                )

        # Check and create/update rules file
        rules_updated = False
        if not rules_file.exists():
            with open(rules_file, "w", encoding="utf-8") as f:
                f.write(rules_content)
            logger.info(f"Created rules file: {rules_file}")
            rules_updated = True
        else:
            # Check if content matches (basic check)
            with open(rules_file, "r", encoding="utf-8") as f:
                existing_content = f.read().strip()
            if existing_content != rules_content.strip():
                with open(rules_file, "w", encoding="utf-8") as f:
                    f.write(rules_content)
                logger.info(f"Updated rules file: {rules_file}")
                rules_updated = True
            else:
                logger.info(
                    f"Rules file already exists with correct content: {rules_file}"
                )

        # Summary message
        if command_updated or rules_updated:
            logger.info(
                "✅ Cursor configuration files have been set up/updated successfully!"
            )
        else:
            logger.info(
                "✅ Cursor configuration files already exist with correct content"
            )

        return True

    except Exception as e:
        logger.error(f"❌ Error setting up Cursor configuration files: {e}")
        # Don't fail the entire module if this setup fails
        return False


# Module initialization log
logger.info("=" * 80)
logger.info("SENIOR_TOOLS MODULE INITIALIZED")
logger.info("=" * 80)
logger.info(f"Module file: {__file__}")
logger.info(f"Module directory: {Path(__file__).parent}")
logger.info(f"Python executable: {sys.executable}")
logger.info(f"Process ID: {os.getpid()}")
logger.info(f"Parent process ID: {os.getppid() if hasattr(os, 'getppid') else 'N/A'}")
logger.info(f"Environment variables count: {len(os.environ)}")
logger.debug(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
logger.debug(f"PATH (first 200 chars): {os.environ.get('PATH', 'Not set')[:200]}")


logger.info("Creating FastMCP instance...")
mcp = FastMCP(name="senior_tools")
logger.info("FastMCP instance created successfully")
logger.debug(f"FastMCP name: {mcp.name if hasattr(mcp, 'name') else 'N/A'}")

# ============================================================================
# MODULE-LEVEL CURSOR WINDOW CACHE
# Pre-grab Cursor windows once at MCP server initialization
# ============================================================================

# Module-level cache for Cursor windows (populated once at startup)
_cached_cursor_windows = []


def _pregrab_cursor_windows_at_startup():
    """Pre-discover Cursor windows at MCP server initialization in a separate thread.

    This happens once when the MCP server starts, not when the UI is shown.
    Since the MCP server lifecycle matches the Cursor instance lifecycle,
    window information remains valid until the server restarts.

    If Cursor closes or a new folder is opened, the MCP server restarts,
    triggering a fresh discovery with the new folder context.

    THREADING STRATEGY:
    - Runs in a separate thread with its own COM initialization (MULTITHREADED)
    - Main thread uses APARTMENTTHREADED (from com_init) for Qt clipboard
    - Each thread can have different COM threading models on Windows
    """
    global _cached_cursor_windows

    if not HAS_FOCUS_CURSOR:
        logger.debug("Focus cursor module not available - skipping MCP startup pregrab")
        return

    # Check if cursor control is disabled
    disable_cursor = os.getenv("APP_DISABLE_CURSOR_CONTROL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if disable_cursor:
        logger.debug("Cursor control disabled - skipping MCP startup pregrab")
        return

    def worker():
        """Worker function that runs in separate thread with its own COM initialization"""
        global _cached_cursor_windows

        try:
            # Initialize COM with MULTITHREADED mode in this worker thread
            # This is separate from main thread's APARTMENTTHREADED mode
            if platform.system() == "Windows":
                try:
                    import pythoncom

                    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                    logger.debug(
                        "Worker thread: COM initialized as MULTITHREADED for pywinauto"
                    )
                except Exception as e:
                    logger.debug(f"Worker thread: COM initialization note: {e}")

            logger.info("Pre-grabbing Cursor windows at MCP server initialization...")
            windows = find_cursor_windows()
            _cached_cursor_windows = windows or []

            if _cached_cursor_windows:
                logger.info(
                    f"✓ Pre-grabbed {len(_cached_cursor_windows)} Cursor window(s) at MCP startup (prioritized by CWD match)"
                )
            else:
                logger.warning("No Cursor windows found during MCP startup pregrab")

        except Exception as e:
            logger.error(f"Error pre-grabbing Cursor windows at MCP startup: {e}")
            _cached_cursor_windows = []
        finally:
            # Cleanup COM in worker thread
            if platform.system() == "Windows":
                try:
                    import pythoncom

                    pythoncom.CoUninitialize()
                    logger.debug("Worker thread: COM uninitialized")
                except Exception:
                    pass

    # Run worker in a separate thread and wait for completion
    import threading

    thread = threading.Thread(target=worker, daemon=False)
    thread.start()
    thread.join(timeout=5.0)  # Wait up to 5 seconds for pregrab to complete

    if thread.is_alive():
        logger.warning(
            "Pregrab thread still running after 5s timeout - continuing anyway"
        )


# Execute pregrab at module initialization (once per MCP lifecycle)
# This is safe because find_cursor_windows() only discovers window metadata,
# it doesn't send any hotkeys or trigger stop mechanisms
_pregrab_cursor_windows_at_startup()

# ============================================================================
# MODERN QT6 INTERFACE WITH GLASS MORPHISM
# ============================================================================


# Custom event for updating stop button text from worker thread
class UpdateButtonEvent(QEvent):
    """Custom event to update button text from worker thread"""

    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, text: str):
        super().__init__(UpdateButtonEvent.EVENT_TYPE)
        self.text = text


# Custom event to signal stop operation completion
class StopOperationCompleteEvent(QEvent):
    """Custom event to signal stop operation completion"""

    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, success: bool):
        super().__init__(StopOperationCompleteEvent.EVENT_TYPE)
        self.success = success


class ModernTaskMasterDialog(QDialog):
    """Professional TaskMaster dialog with clean, corporate design"""

    # UI Constants (Fix #6: Extract magic numbers)
    WINDOW_BORDER_RADIUS = 16  # Main window rounded corners
    WIDGET_BORDER_RADIUS = (
        8  # Widget rounded corners (matches HTML BORDER_RADIUS_XLARGE)
    )

    def __init__(
        self,
        agent_comment: str = "",
        dark_mode: bool = True,
        project_dir: str = None,
        parent=None,
    ):
        super().__init__(parent)
        self.agent_comment = agent_comment
        self.dark_mode = dark_mode
        self.project_dir = project_dir  # Store project directory for display
        self.config_vars = {}
        self.result = ""

        # Initialize logger
        self.logger = logging.getLogger(__name__)

        # For window dragging
        self.drag_position = None

        # For stop button updates
        self.stop_button_ref = None

        # Thread safety for stop operation (C1 & C2 fixes)
        self._is_closing = False
        self._stop_worker_lock = threading.Lock()
        self._stop_cancelled = False
        self._stop_thread_ref = None
        self._stop_start_time = None
        self._stop_timeout = None

        self.setup_ui()
        self.load_styles()
        self.setup_shortcuts()

        # Set window properties - frameless for clean look
        self.setWindowTitle("TaskMaster Professional")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )  # Enable transparency for rounded corners (Qt6)
        self.setModal(True)
        # Initial size: keep width, compute height based on current image presence
        try:
            self.resize(800, 600)
            # If image section starts hidden, adjust to compact height; otherwise expand
            if hasattr(self, "adjust_window_height_for_images"):
                self.adjust_window_height_for_images()
        except Exception:
            pass
        self.center_on_screen()
        # Initialize rounded corners on Windows
        self._init_rounded_corners()

    def showEvent(self, event):
        """Override showEvent to set focus after dialog is fully shown"""
        super().showEvent(event)
        # Use QTimer to defer focus setting until after the event loop processes the show
        QTimer.singleShot(0, self._set_initial_focus)

    def _set_initial_focus(self):
        """Set focus to the agent report text area after dialog is shown"""
        try:
            if hasattr(self, "agent_text") and self.agent_text is not None:
                self.agent_text.setFocus()
                # Note: QWebEngineView doesn't support textCursor() in PyQt6
                # Focus is set but cursor positioning is not available for web views
        except Exception as e:
            logger.debug(f"Failed to set initial focus: {e}")

    def _load_header_image(self):
        """Load appropriate header image based on current theme"""
        try:
            from PyQt6.QtGui import QPixmap

            script_dir = Path(__file__).parent.absolute()
            # Use dark header for dark mode, regular header for light mode
            header_filename = "header_dark.png" if self.dark_mode else "header.png"
            header_path = script_dir / "images" / header_filename
            if header_path.exists():
                pixmap = QPixmap(str(header_path))
                # Scale to the label's available height (fallback to 32px) while maintaining aspect ratio
                target_height = (
                    self.header_title.height()
                    or self.header_title.sizeHint().height()
                    or 32
                )
                if not isinstance(target_height, int):
                    try:
                        target_height = int(target_height)
                    except Exception:
                        target_height = 32
                if target_height <= 0:
                    target_height = 32
                scaled_pixmap = pixmap.scaledToHeight(
                    target_height, Qt.TransformationMode.SmoothTransformation
                )
                self.header_title.setPixmap(scaled_pixmap)
                # Prevent QLabel from further scaling the pixmap inconsistently
                try:
                    self.header_title.setScaledContents(False)
                except Exception:
                    pass
            else:
                self.header_title.setText("AgentLoop")  # Fallback if image not found
        except Exception:
            self.header_title.setText("AgentLoop")  # Fallback on error

    def refresh_theme(self):
        """Refresh theme/QSS and theme-dependent elements dynamically."""
        import os

        try:
            # Check current theme preference
            dark_pref = os.getenv("APP_DARK_MODE", "true").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            old_dark_mode = self.dark_mode
            self.dark_mode = dark_pref

            # Skip if theme hasn't changed
            if old_dark_mode == dark_pref:
                logger.debug("Theme unchanged, skipping refresh")
                return

            logger.info(
                f"Theme switching from {'dark' if old_dark_mode else 'light'} to {'dark' if dark_pref else 'light'}"
            )

            # Reload app QSS from disk (same logic as on startup)
            app = QApplication.instance()
            if app is not None:
                script_dir = Path(__file__).parent.absolute()
                preferred_dark = dark_pref
                qss_paths = [
                    script_dir
                    / (
                        "styles/app_dark.qss"
                        if preferred_dark
                        else "styles/app_light.qss"
                    ),
                    script_dir
                    / (
                        "styles/app_light.qss"
                        if preferred_dark
                        else "styles/app_dark.qss"
                    ),
                ]
                qss_loaded = False
                for p in qss_paths:
                    try:
                        if p.exists():
                            with open(p, "r", encoding="utf-8") as f:
                                css_content = f.read()
                                app.setStyleSheet(css_content)
                            logger.debug(f"Loaded QSS: {p}")
                            qss_loaded = True
                            break
                    except Exception as e:
                        logger.warning(f"Failed to load QSS {p}: {e}")
                        continue

                if qss_loaded:
                    # Force complete widget style refresh after QSS change
                    try:
                        app.style().unpolish(app)
                        app.style().polish(app)
                        for widget in app.allWidgets():
                            widget.style().unpolish(widget)
                            widget.style().polish(widget)
                            widget.update()
                    except Exception as e:
                        logger.warning(f"Failed to force style refresh: {e}")

            # Reload header image with new theme
            self._load_header_image()

            # Recolor/refresh sparkle icon if present
            try:
                if hasattr(self, "sparkle_button") and self.sparkle_button is not None:
                    self._update_sparkle_icon()
                    # Reapply stylesheet to preserve hover effects (theme-aware)
                    self.sparkle_button.setStyleSheet(self._get_sparkle_hover_style())
                    logger.debug("Updated sparkle button theme")
            except Exception as e:
                logger.warning(f"Failed to update sparkle button theme: {e}")

            # Reposition sparkle icon if needed (with slight delay for layout to settle)
            try:
                if hasattr(self, "_position_sparkle_on_response_text"):
                    QTimer.singleShot(50, self._position_sparkle_on_response_text)
            except Exception as e:
                logger.warning(f"Failed to reposition sparkle icon: {e}")

            # Recolor/refresh brain icon if present
            try:
                if hasattr(self, "brain_button") and self.brain_button is not None:
                    self._update_brain_icon()
                    # Reapply stylesheet to preserve hover effects (theme-aware)
                    self.brain_button.setStyleSheet(self._get_brain_hover_style())
                    logger.debug("Updated brain button theme")
            except Exception as e:
                logger.warning(f"Failed to update brain button theme: {e}")

            # Reposition brain icon if needed (with slight delay for layout to settle)
            try:
                if hasattr(self, "_position_brain_on_agent_text"):
                    QTimer.singleShot(50, self._position_brain_on_agent_text)
            except Exception as e:
                logger.warning(f"Failed to reposition brain icon: {e}")

            logger.info("Theme refresh completed successfully")

        except Exception as e:
            logger.error(f"Error during theme refresh: {e}")
            # Fail silently to avoid breaking user session

    def _update_sparkle_icon(self):
        """Load sparkle icon from 50x50 theme-specific assets."""
        from PyQt6.QtGui import QIcon, QPixmap

        try:
            images_dir = Path(__file__).parent / "images"

            # Use theme-specific 50x50 icons only
            icon_file = (
                "sparkle_icon_dark.png" if self.dark_mode else "sparkle_icon.png"
            )
            icon_path = images_dir / icon_file

            if icon_path.exists():
                pixmap = QPixmap(str(icon_path))
                if not pixmap.isNull():
                    self.sparkle_button.setIcon(QIcon(pixmap))
                    return

            # Fallback to emoji if icon files missing
            self.sparkle_button.setText("✨")
        except Exception:
            self.sparkle_button.setText("✨")

    def _get_sparkle_hover_style(self):
        """Get theme-appropriate hover style for sparkle button."""
        if self.dark_mode:
            return (
                "QToolButton#sparkleIcon{border:none;background:transparent;padding:0;margin:0;border-radius:8px;}"
                "QToolButton#sparkleIcon:hover{background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;}"
                "QToolButton#sparkleIcon:pressed{background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.3);border-radius:8px;}"
                "QToolButton#sparkleIcon:focus{outline:none;border:none;}"
            )
        else:
            return (
                "QToolButton#sparkleIcon{border:none;background:transparent;padding:0;margin:0;border-radius:8px;}"
                "QToolButton#sparkleIcon:hover{background:rgba(0,0,0,0.05);border:1px solid rgba(0,0,0,0.1);border-radius:8px;}"
                "QToolButton#sparkleIcon:pressed{background:rgba(0,0,0,0.08);border:1px solid rgba(0,0,0,0.15);border-radius:8px;}"
                "QToolButton#sparkleIcon:focus{outline:none;border:none;}"
            )

    def _update_brain_icon(self):
        """Load brain icon from theme-specific assets."""
        from PyQt6.QtGui import QIcon, QPixmap

        try:
            images_dir = Path(__file__).parent / "images"

            # Use theme-specific icons
            icon_file = "brain_icon_dark.png" if self.dark_mode else "brain_icon.png"
            icon_path = images_dir / icon_file

            if icon_path.exists():
                pixmap = QPixmap(str(icon_path))
                if not pixmap.isNull():
                    self.brain_button.setIcon(QIcon(pixmap))
                    return

            # Fallback to emoji if icon files missing
            self.brain_button.setText("🧠")
        except Exception:
            self.brain_button.setText("🧠")

    def _get_brain_hover_style(self):
        """Get theme-appropriate hover style for brain button."""
        if self.dark_mode:
            return (
                "QToolButton#brainIcon{border:none;background:transparent;padding:0;margin:0;border-radius:8px;}"
                "QToolButton#brainIcon:hover{background:rgba(160,160,255,0.15);border:1px solid rgba(160,160,255,0.3);border-radius:8px;}"
                "QToolButton#brainIcon:pressed{background:rgba(160,160,255,0.2);border:1px solid rgba(160,160,255,0.4);border-radius:8px;}"
                "QToolButton#brainIcon:focus{outline:none;border:none;}"
            )
        else:
            return (
                "QToolButton#brainIcon{border:none;background:transparent;padding:0;margin:0;border-radius:8px;}"
                "QToolButton#brainIcon:hover{background:rgba(107,114,128,0.1);border:1px solid rgba(107,114,128,0.2);border-radius:8px;}"
                "QToolButton#brainIcon:pressed{background:rgba(107,114,128,0.15);border:1px solid rgba(107,114,128,0.3);border-radius:8px;}"
                "QToolButton#brainIcon:focus{outline:none;border:none;}"
            )

    def setup_ui(self):
        """Setup the main UI layout with professional design"""
        # Create outer layout with small margin for shadow/rounding
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)  # No margins needed with transparent bg

        # Main content container with padding
        main_container = QFrame()
        main_container.setProperty("containerType", "main")
        main_container.setObjectName("mainContainer")  # Add object name for styling
        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(16)

        # Professional header
        self.create_header(container_layout)

        # Agent comment section
        self.create_agent_section(container_layout)

        # Response section
        self.create_response_section(container_layout)

        # Image section
        self.create_image_section(container_layout)

        # Buttons
        self.create_buttons(container_layout)

        layout.addWidget(main_container)

        # Note: Focus is set in showEvent() to ensure it works after dialog is fully displayed

    def create_header(self, layout):
        """Create professional header"""
        header_frame = QFrame()
        header_frame.setProperty("panelType", "header")
        header_frame.setMaximumHeight(48)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Title with image
        title = QLabel()
        title.setProperty("labelType", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        # Ensure consistent visual height regardless of theme/DPI (Qt6)
        try:
            title.setFixedHeight(32)
        except Exception:
            pass

        # Store title widget for theme refreshing
        self.header_title = title

        # Load appropriate header image based on theme
        self._load_header_image()

        # Add title with left alignment for more leftward positioning
        header_layout.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft)

        header_layout.addStretch()

        # Status indicator
        status_label = QLabel("● Active")
        status_label.setProperty("labelType", "status")
        status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(status_label)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setProperty("buttonType", "close")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        close_btn.setToolTip("Close")
        header_layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignVCenter)  # Qt6

        layout.addWidget(header_frame)

    def _init_rounded_corners(self) -> None:
        """Enable rounded corners using Qt mask only.
        Provides consistent appearance across all platforms.
        """
        try:
            # Always use Qt mask for consistent cross-platform appearance
            self.update_round_mask()
        except Exception:
            # Fail silently to avoid breaking UI
            pass

    def update_round_mask(self, radius: int = None) -> None:
        """Apply a rounded-rect mask to the window for visual rounding."""
        if radius is None:
            radius = self.WINDOW_BORDER_RADIUS
        try:
            rect = self.rect()
            if rect.isNull():
                return
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), float(radius), float(radius))
            region = QRegion(path.toFillPolygon().toPolygon())
            self.setMask(region)
        except Exception:
            pass

    def _apply_rounded_corners_to_widget(
        self, widget: QWidget, radius: int = None
    ) -> None:
        """
        Apply rounded corners to any widget using a mask.

        Fixes applied:
        - Issue #1: Use weak references to prevent memory leaks
        - Issue #3: Specific exception handling with appropriate logging levels
        - Issue #4: Increased timer delay to 50ms to avoid race conditions
        - Issue #5: Added cleanup on widget destruction
        - Issue #6: Use class constant for default radius

        Args:
            widget: The widget to apply rounded corners to
            radius: Corner radius in pixels (default: WIDGET_BORDER_RADIUS)
        """
        # Fix #6: Use class constant for default radius
        if radius is None:
            radius = self.WIDGET_BORDER_RADIUS

        try:
            from weakref import ref as weakref_ref

            # Fix #5: Prevent double-application
            if hasattr(widget, "_rounded_corners_applied"):
                logger.debug(
                    f"Rounded corners already applied to {widget.__class__.__name__}"
                )
                return

            widget._rounded_corners_applied = True

            # Fix #1: Use weak reference to prevent circular reference memory leak
            widget_ref = weakref_ref(widget)

            def update_widget_mask() -> None:
                try:
                    w = widget_ref()
                    if w is None:  # Widget was deleted
                        return
                    rect = w.rect()
                    if rect.isNull() or rect.width() == 0 or rect.height() == 0:
                        return
                    path = QPainterPath()
                    path.addRoundedRect(QRectF(rect), float(radius), float(radius))
                    region = QRegion(path.toFillPolygon().toPolygon())
                    w.setMask(region)
                # Fix #3: Specific exception handling with appropriate logging
                except (RuntimeError, AttributeError) as e:
                    # Expected errors: widget deleted, Qt not initialized
                    logger.debug(
                        f"Failed to update widget mask for {widget.__class__.__name__}: {e}"
                    )
                except Exception as e:
                    # Unexpected errors should be logged at warning level
                    logger.warning(
                        f"Unexpected error updating widget mask for {widget.__class__.__name__}: {e}",
                        exc_info=True,
                    )

            # Store the update function for later use
            widget._update_mask = update_widget_mask

            # Fix #4: Use 50ms delay instead of 0 to ensure widget geometry is ready
            QTimer.singleShot(50, update_widget_mask)

            # Override resizeEvent to update mask
            original_resize = widget.resizeEvent

            def new_resize_event(event) -> None:
                try:
                    original_resize(event)
                finally:
                    w = widget_ref()
                    if w is not None:
                        update_widget_mask()

            widget.resizeEvent = new_resize_event

            # Fix #5: Add cleanup on widget destruction
            def cleanup():
                try:
                    if hasattr(widget, "_update_mask"):
                        delattr(widget, "_update_mask")
                    if hasattr(widget, "_rounded_corners_applied"):
                        delattr(widget, "_rounded_corners_applied")
                    logger.debug(
                        f"Cleaned up rounded corners for {widget.__class__.__name__}"
                    )
                except Exception:
                    pass

            widget.destroyed.connect(cleanup)

        # Fix #3: Specific exception handling for outer try block
        except (RuntimeError, AttributeError, ImportError) as e:
            # Expected errors: widget issues, weakref import failure
            logger.debug(
                f"Failed to apply rounded corners to {widget.__class__.__name__}: {e}"
            )
        except Exception as e:
            # Unexpected errors
            logger.warning(
                f"Unexpected error applying rounded corners to {widget.__class__.__name__}: {e}",
                exc_info=True,
            )

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        finally:
            # Keep the rounded mask in sync with window size
            self.update_round_mask()

    def paintEvent(self, event):
        """Custom paint event for smooth anti-aliased corners (Qt6)."""
        if self.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        super().paintEvent(event)

    def _refresh_button_layout(self):
        """Refresh the button layout to show/hide stop button based on cursor control setting"""
        try:
            if not hasattr(self, "button_layout") or self.button_layout is None:
                logger.debug("Button layout not found, skipping refresh")
                return

            # Clear existing buttons
            while self.button_layout.count():
                child = self.button_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            # Recreate button layout with current settings
            self._create_button_layout()
            logger.debug("Button layout refreshed successfully")

        except Exception as e:
            logger.warning(f"Failed to refresh button layout: {e}")

    def _create_button_layout(self):
        """Create the button layout with appropriate buttons based on current settings"""
        try:
            # Secondary actions (left side) - AI button moved to input box as sparkle icon
            settings_button = QPushButton("Settings")
            settings_button.setProperty("buttonType", "secondary")
            settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
            settings_button.clicked.connect(self.open_settings)
            self.button_layout.addWidget(settings_button)

            self.button_layout.addStretch()

            # Primary actions (right side)
            # Only show stop button if cursor control is enabled
            if not self._is_cursor_control_disabled():
                stop_button = QPushButton("Stop")
                stop_button.setProperty("buttonType", "warning")
                stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
                stop_button.clicked.connect(self.stop_cursor)
                stop_button.setToolTip("Stop execution (Ctrl+Shift+Backspace)")
                self.button_layout.addWidget(stop_button)
                # Store reference for updates from worker thread
                self.stop_button_ref = stop_button

            send_button = QPushButton("Send Response")
            send_button.setProperty("buttonType", "primary")
            send_button.setCursor(Qt.CursorShape.PointingHandCursor)
            send_button.clicked.connect(self.send_response)
            send_button.setDefault(True)
            send_button.setToolTip("Send (Ctrl+Enter)")  # Qt6
            self.button_layout.addWidget(send_button)

        except Exception as e:
            logger.warning(f"Failed to create button layout: {e}")

    # Removed unused _init_config_vars_defaults; config values are initialized via UI creation

    def create_agent_section(self, layout):
        """Create agent comment section with professional styling"""
        agent_frame = QFrame()
        agent_frame.setProperty("panelType", "content")
        agent_layout = QVBoxLayout(agent_frame)
        agent_layout.setContentsMargins(16, 12, 16, 12)

        # Header with status - Agent Report [folder name] character count
        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Left: "Agent Report"
        title = QLabel("Agent Report")
        title.setProperty("labelType", "sectionHeader")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(title)

        # Middle: Project directory (with stretch spacers to center it)
        header_layout.addStretch()
        try:
            # Use provided project_dir if available, otherwise fall back to cwd
            if self.project_dir:
                project_path = Path(self.project_dir)
                logger.info(f"Using provided project_dir: {project_path}")
                project_name = project_path.name
            else:
                project_path = Path.cwd()
                logger.info(f"No project_dir provided, using cwd: {project_path}")
                project_name = project_path.name

            logger.info(
                f"Display project name: {project_name} (from path: {project_path})"
            )
            project_label = QLabel(f"📁 {project_name}")
            project_label.setProperty("labelType", "projectDirectory")
            project_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            project_label.setMaximumWidth(300)  # Maximum width constraint
            header_layout.addWidget(project_label)
        except Exception as e:
            logger.warning(f"Failed to get project directory name: {e}")
        header_layout.addStretch()

        # Right: Character count (pushed to far right)
        char_count = QLabel(f"{len(self.agent_comment)} characters")
        char_count.setProperty("labelType", "meta")
        char_count.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(char_count)

        agent_layout.addLayout(header_layout)

        # Use QWebEngineView for modern markdown rendering
        self.agent_text = QWebEngineView()
        self.agent_text.setAccessibleName("Agent Report")
        self.agent_text.setMinimumHeight(180)
        self.agent_text.setProperty("textType", "professional")

        # Apply rounded corners to the web view widget
        self._apply_rounded_corners_to_widget(self.agent_text, radius=8)

        # Render markdown to HTML with syntax highlighting
        try:
            logger.debug("Starting markdown rendering...")
            from src.markdown_renderer import MarkdownRenderer

            renderer = MarkdownRenderer(dark_mode=self.dark_mode)
            logger.debug("MarkdownRenderer created, calling render()...")
            html_content, code_blocks = renderer.render(self.agent_comment)
            logger.debug(
                f"Markdown rendered successfully, HTML length: {len(html_content)}"
            )

            # CRITICAL FIX: Set base URL to enable proper resource loading
            # This prevents QWebEngineView from blocking when loading HTML
            from PyQt6.QtCore import QUrl

            base_url = QUrl.fromLocalFile(str(Path(__file__).parent.absolute()) + "/")
            logger.debug(f"Setting HTML with base URL: {base_url.toString()}")
            self.agent_text.setHtml(html_content, base_url)
            logger.debug("HTML set successfully")

            self.code_blocks = code_blocks  # Store for potential future use
        except Exception as e:
            logger.error(f"Failed to render markdown: {e}", exc_info=True)
            # Fallback to plain text
            fallback_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: {'#c9d1d9' if self.dark_mode else '#24292f'};
            background: {'#0d1117' if self.dark_mode else '#ffffff'};
            padding: 16px;
            margin: 0;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>{self.agent_comment}</body>
</html>
"""
            from PyQt6.QtCore import QUrl

            base_url = QUrl.fromLocalFile(str(Path(__file__).parent.absolute()) + "/")
            logger.debug("Using fallback HTML")
            self.agent_text.setHtml(fallback_html, base_url)

        agent_layout.addWidget(self.agent_text)

        # Create floating brain button for memory display (bottom-right, positioned over web view)
        self.brain_button = QToolButton(
            agent_frame
        )  # Parent to frame instead of web view
        self.brain_button.setObjectName("brainIcon")
        self.brain_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.brain_button.setToolTip("View Project Memory")
        self.brain_button.clicked.connect(self.show_memory_dialog)
        try:
            self.brain_button.setFlat(True)
            self.brain_button.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground, True
            )
            self.brain_button.setAttribute(
                Qt.WidgetAttribute.WA_NoSystemBackground, True
            )
        except Exception:
            pass  # Qt6

        # Load brain icon and set size
        from PyQt6.QtCore import QSize

        try:
            self._update_brain_icon()
            self.brain_button.setIconSize(QSize(24, 24))
            # Transparent palette for button
            try:
                from PyQt6.QtGui import QPalette

                pal = self.brain_button.palette()
                pal.setColor(QPalette.Button, Qt.transparent)
                pal.setColor(QPalette.Base, Qt.transparent)
                self.brain_button.setPalette(pal)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed to load brain icon: {e}")
            self.brain_button.setText("🧠")

        # Style for hover effects
        self.brain_button.setAutoRaise(True)
        self.brain_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.brain_button.setStyleSheet(self._get_brain_hover_style())

        # Position the brain button at bottom-right of the web view
        def position_brain():
            try:
                # Get web view dimensions
                web_rect = self.agent_text.geometry()
                h = web_rect.height()
                w = web_rect.width()

                icon_size = 24
                padding = 12  # Comfortable padding from edges

                # Calculate position from bottom-right (relative to agent_frame)
                left = web_rect.x() + w - icon_size - padding
                top = web_rect.y() + h - icon_size - padding

                self.brain_button.setGeometry(left, top, icon_size, icon_size)
                self.brain_button.raise_()  # Ensure it's on top
            except Exception as e:
                logger.warning(f"Failed to position brain button: {e}")

        # Save reference for event-triggered positioning
        self._position_brain_on_agent_text = position_brain

        # Position once now
        QTimer.singleShot(100, position_brain)  # Delay to ensure layout is complete

        # Reposition when agent text is resized or scrolled
        self.agent_text.installEventFilter(self)

        layout.addWidget(agent_frame)

    def create_image_section(self, layout):
        """Create professional image handling section"""
        image_frame = QFrame()
        # Keep a reference so we can hide/show the entire section based on paste state
        self.image_section_frame = image_frame
        image_frame.setProperty("panelType", "imageSection")
        image_main_layout = QVBoxLayout(image_frame)
        image_main_layout.setContentsMargins(16, 8, 16, 8)
        image_main_layout.setSpacing(8)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.image_status = QLabel("No images attached")
        self.image_status.setProperty("statusType", "no_images")
        self.image_status.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(self.image_status)

        header_layout.addStretch()

        # Clear button
        clear_btn = QPushButton("Clear All")
        clear_btn.setProperty("buttonType", "secondary")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_images)
        clear_btn.setMaximumWidth(100)
        clear_btn.setMaximumHeight(28)
        header_layout.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)  # Qt6

        image_main_layout.addLayout(header_layout)

        # Image container
        images_scroll_frame = QFrame()
        images_scroll_frame.setProperty("panelType", "imageContainer")
        images_scroll_frame.setMaximumHeight(120)

        images_scroll = QScrollArea(images_scroll_frame)
        images_scroll.setWidgetResizable(True)
        images_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        images_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        images_scroll.setProperty("scrollType", "professional")

        self.images_container = QWidget()
        images_scroll.setWidget(self.images_container)

        from PyQt6.QtWidgets import QGridLayout

        self.images_layout = QGridLayout(self.images_container)
        self.images_layout.setContentsMargins(8, 8, 8, 8)
        self.images_layout.setSpacing(8)

        scroll_frame_layout = QVBoxLayout(images_scroll_frame)
        scroll_frame_layout.setContentsMargins(0, 0, 0, 0)
        scroll_frame_layout.addWidget(images_scroll)

        image_main_layout.addWidget(images_scroll_frame)

        self.images_scroll_frame = images_scroll_frame
        self.images_scroll_frame.hide()

        layout.addWidget(image_frame)
        # Hide entire image section until an image is actually pasted
        try:
            self.image_section_frame.hide()
        except Exception:
            pass
        # Adjust overall dialog height to reflect hidden image section
        try:
            self.adjust_window_height_for_images()
        except Exception:
            pass

    def create_response_section(self, layout):
        """Create response section with professional styling"""
        response_frame = QFrame()
        response_frame.setProperty("panelType", "content")
        response_layout = QVBoxLayout(response_frame)
        response_layout.setContentsMargins(16, 12, 16, 12)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Your Response")
        title.setProperty("labelType", "sectionHeader")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(title)

        shortcut_hint = QLabel("Ctrl+Enter to send")
        shortcut_hint.setProperty("labelType", "hint")
        shortcut_hint.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_layout.addStretch()
        header_layout.addWidget(shortcut_hint)

        response_layout.addLayout(header_layout)

        # Use SlashCommandTextEdit for slash command support
        try:
            from src.slash_text_edit import SlashCommandTextEdit

            self.response_text = SlashCommandTextEdit()
            self.logger.info("Slash command support enabled")
        except ImportError as e:
            # Fallback to standard QTextEdit if slash commands unavailable
            self.logger.warning(
                f"Slash command module unavailable, falling back to standard input: {e}"
            )
            self.response_text = QTextEdit()
        except Exception as e:
            # Catch any other initialization errors
            self.logger.error(
                f"Error initializing slash command support: {e}", exc_info=True
            )
            self.response_text = QTextEdit()

        self.response_text.setAccessibleName("Response Input")
        self.response_text.setPlaceholderText(
            "Enter your feedback here (type '/' for commands)..."
        )
        self.response_text.setProperty("textType", "professional")

        # Only set rich text if slash commands are enabled
        if hasattr(self.response_text, "get_expanded_text"):
            self.response_text.setAcceptRichText(True)
        else:
            self.response_text.setAcceptRichText(False)

        # Dynamic height adjustment
        font_metrics = self.response_text.fontMetrics()
        line_height = font_metrics.lineSpacing()
        padding = 24

        self.response_text.setMinimumHeight(line_height + padding)
        self.response_text.setMaximumHeight(line_height * 4 + padding)

        from PyQt6.QtWidgets import QSizePolicy

        self.response_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.response_text.textChanged.connect(self.adjust_response_height)

        # Create sparkle tool button overlaid on the right inside the input
        self.sparkle_button = QToolButton(self.response_text)
        self.sparkle_button.setObjectName("sparkleIcon")
        self.sparkle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sparkle_button.setToolTip("Enhanced with AI")
        self.sparkle_button.clicked.connect(self.improve_with_ai)
        try:
            self.sparkle_button.setFlat(True)
            self.sparkle_button.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground, True
            )
            self.sparkle_button.setAttribute(
                Qt.WidgetAttribute.WA_NoSystemBackground, True
            )
        except Exception:
            pass  # Qt6

        # Load sparkle icon via unified helper and set size
        from PyQt6.QtCore import QSize

        try:
            self._update_sparkle_icon()
            self.sparkle_button.setIconSize(QSize(24, 24))
            # Explicitly ensure the button palette has transparent base
            try:
                from PyQt6.QtGui import QPalette

                pal = self.sparkle_button.palette()
                pal.setColor(QPalette.Button, Qt.transparent)
                pal.setColor(QPalette.Base, Qt.transparent)
                self.sparkle_button.setPalette(pal)
            except Exception:
                pass
        except Exception:
            self.sparkle_button.setText("✨")

        # Style and padding to keep text clear of the icon (fully transparent, no borders)
        self.sparkle_button.setAutoRaise(True)
        self.sparkle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Apply theme-aware hover effects
        self.sparkle_button.setStyleSheet(self._get_sparkle_hover_style())

        # Reserve space on the right so text doesn't overlap the icon (24px + padding)
        self.response_text.setViewportMargins(0, 0, 44, 0)

        # Position the icon initially and keep it vertically centered on input
        def position_sparkle():
            try:
                h = self.response_text.height()
                icon_size = 24
                right_padding = 10
                top = (h - icon_size) // 2
                left = self.response_text.width() - icon_size - right_padding
                self.sparkle_button.setGeometry(left, top, icon_size, icon_size)
            except Exception:
                pass

        # Save reference for eventFilter-triggered positioning
        self._position_sparkle_on_response_text = position_sparkle

        # Position once now and again after layout settles
        position_sparkle()
        QTimer.singleShot(100, position_sparkle)  # Delay to ensure layout is complete

        response_layout.addWidget(self.response_text)

        # Setup image paste functionality
        self.setup_image_paste_functionality()

        response_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(response_frame)

    def adjust_response_height(self):
        """Adjust the height of response text area based on content (1-4 lines)"""
        try:
            document = self.response_text.document()
            document_height = document.size().height()

            font_metrics = self.response_text.fontMetrics()
            line_height = font_metrics.lineSpacing()
            padding = 24  # Account for padding and borders

            # Calculate number of lines needed
            lines_needed = max(1, min(4, int(document_height / line_height) + 1))
            new_height = line_height * lines_needed + padding

            # Only resize if height changed significantly
            current_height = self.response_text.height()
            if abs(new_height - current_height) > 5:
                self.response_text.setFixedHeight(new_height)
                # Ensure size policy remains fixed to prevent expansion
                from PyQt6.QtWidgets import QSizePolicy

                self.response_text.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )

        except Exception as e:
            print(f"Error adjusting response height: {e}")

    def reset_response_height(self):
        """Reset response text area to initial 1-line height"""
        try:
            font_metrics = self.response_text.fontMetrics()
            line_height = font_metrics.lineSpacing()
            padding = 24  # Account for padding and borders
            initial_height = line_height + padding
            self.response_text.setFixedHeight(initial_height)
            # Ensure size policy remains fixed to prevent expansion
            from PyQt6.QtWidgets import QSizePolicy

            self.response_text.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        except Exception as e:
            print(f"Error resetting response height: {e}")

    def create_buttons(self, layout):
        """Create professional action buttons"""
        button_frame = QFrame()
        button_frame.setProperty("panelType", "buttonBar")
        self.button_layout = QHBoxLayout(button_frame)
        self.button_layout.setContentsMargins(16, 12, 16, 12)
        self.button_layout.setSpacing(8)

        # Create the initial button layout
        self._create_button_layout()

        layout.addWidget(button_frame)

    def open_settings(self):
        try:
            from src.settings_dialog import SettingsDialog, SlideNotification

            dlg = SettingsDialog(self)

            # Connect to settings saved signal
            def on_settings_saved(_context_modal_enabled):
                # Create simple notification message
                msg = "Settings updated"

                # Delay notification to ensure main modal animations complete
                def show_delayed_notification():
                    notification = SlideNotification(self, msg, duration=2500)
                    notification.show_notification()

                # Wait for modal animations to complete (resize animation is 200ms + buffer)
                QTimer.singleShot(400, show_delayed_notification)

            dlg.settings_saved.connect(on_settings_saved)

            # Show dialog without minimizing parent (Qt6)
            self.setWindowState(
                self.windowState() & ~Qt.WindowState.WindowMinimized
                | Qt.WindowState.WindowActive
            )
            res = dlg.exec()

            if res == QDialog.DialogCode.Accepted:
                try:
                    # Clear widget-level styles so app stylesheet applies
                    self.setStyleSheet("")
                    for w in self.findChildren(QWidget):
                        w.setStyleSheet("")
                    # Refresh theme-dependent elements (like header images)
                    self.refresh_theme()
                    # Refresh button layout to show/hide stop button based on cursor control setting
                    self._refresh_button_layout()
                    # Keep window active and not minimized (Qt6)
                    self.setWindowState(
                        self.windowState() & ~Qt.WindowState.WindowMinimized
                        | Qt.WindowState.WindowActive
                    )
                    self.raise_()
                    self.activateWindow()
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open settings: {e}")

    def _is_cursor_control_disabled(self):
        """Check if cursor control functionality is disabled"""
        return os.getenv("APP_DISABLE_CURSOR_CONTROL", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    def _is_auto_stop_enabled(self):
        """Check if auto-stop functionality is enabled"""
        return os.getenv("APP_AUTO_STOP", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    def load_styles(self):
        """Load styles - external QSS files handle all theming"""
        # No inline styles - let external QSS files control all theming
        # This allows proper dark/light theme switching via .env configuration
        pass

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Ctrl+Enter to send
        send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        send_shortcut.activated.connect(self.send_response)

        # Ctrl+I to improve with AI
        ai_shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        ai_shortcut.activated.connect(self.improve_with_ai)

        # NOTE: We DO NOT register a custom Ctrl+C shortcut here because:
        # Qt's QTextEdit has built-in copy support that works automatically when:
        # 1. The widget has Qt.TextEditorInteraction flags set
        # 2. Text is selected
        # Registering a custom shortcut would override Qt's default behavior

    def copy_agent_text(self):
        """Copy selected text from agent_text to clipboard"""
        try:
            logger.info("copy_agent_text() called")
            focused_widget = QApplication.focusWidget()
            logger.info(
                f"Focused widget: {focused_widget} (type: {type(focused_widget).__name__})"
            )

            # Check if agent_text has focus
            if hasattr(self, "agent_text") and self.agent_text.hasFocus():
                # Note: QWebEngineView doesn't support textCursor() in PyQt6
                # Just copy whatever is selected (if anything)
                self.agent_text.copy()
                logger.info("✓ Copied selected text from agent text")
            else:
                # If agent_text doesn't have focus, let Qt handle default copy behavior
                # This allows copying from response_text or other widgets
                logger.info(
                    f"agent_text doesn't have focus, delegating to focused widget"
                )
                if hasattr(focused_widget, "copy"):
                    focused_widget.copy()
                    logger.info(f"✓ Called copy() on {type(focused_widget).__name__}")
        except Exception as e:
            logger.error(f"Error copying text: {e}", exc_info=True)

    def setup_image_paste_functionality(self):
        """Setup image paste functionality for PyQt6 QTextEdit"""
        # Install event filter to handle paste events
        self.response_text.installEventFilter(self)

        # Override the paste action in context menu (Qt6)
        self.response_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.response_text.customContextMenuRequested.connect(self.show_context_menu)

    def eventFilter(self, obj, event):
        """Handle events for image paste functionality and button positioning"""
        if hasattr(self, "response_text") and obj == self.response_text:
            # Keep sparkle icon aligned on resizes and when shown
            try:
                if hasattr(
                    self, "_position_sparkle_on_response_text"
                ) and event.type() in (
                    QEvent.Type.Resize,
                    QEvent.Type.Show,
                    QEvent.LayoutRequest,
                ):
                    self._position_sparkle_on_response_text()
            except Exception:
                pass

            if event.type() == QEvent.Type.KeyPress:
                if (
                    event.key() == Qt.Key.Key_V
                    and event.modifiers() == Qt.KeyboardModifier.ControlModifier
                ):
                    # Handle Ctrl+V for image paste
                    if self.handle_paste_event():
                        # Image was handled, consume the event to prevent default paste
                        return True
                    # No image detected, paste as plain text (strip formatting)
                    self.paste_plain_text()
                    return True  # Consume event to prevent default formatted paste

        # Handle brain button positioning on agent_text resize/scroll
        if hasattr(self, "agent_text") and obj == self.agent_text:
            try:
                if hasattr(self, "_position_brain_on_agent_text") and event.type() in (
                    QEvent.Type.Resize,
                    QEvent.Type.Show,
                    QEvent.LayoutRequest,
                ):
                    self._position_brain_on_agent_text()
            except Exception:
                pass

        return super().eventFilter(obj, event)

    def show_context_menu(self, position):
        """Show custom context menu with image paste support"""
        menu = self.response_text.createStandardContextMenu()

        # Add image paste action at the top
        paste_image_action = QAction("📷 Paste Image", self)
        paste_image_action.triggered.connect(self.paste_image_from_menu)
        paste_image_action.setShortcut(QKeySequence("Ctrl+V"))

        # Insert at the beginning
        actions = menu.actions()
        if actions:
            menu.insertAction(actions[0], paste_image_action)
            menu.insertSeparator(actions[0])
        else:
            menu.addAction(paste_image_action)

        menu.exec_(self.response_text.mapToGlobal(position))

    def paste_image_from_menu(self):
        """Handle image paste from context menu"""
        if not self.handle_paste_event():
            # If no image was pasted, do normal paste
            # But first check if clipboard actually has an image that we missed
            try:
                clipboard = QApplication.clipboard()
                if clipboard.mimeData().hasImage():
                    logger.warning("Image detected but not handled - skipping paste")
                    return  # Don't paste anything if image is present
            except:
                pass
            # Paste as plain text only - strip all formatting
            self.paste_plain_text()

    def paste_plain_text(self):
        """Paste clipboard content as plain text only, stripping all formatting"""
        try:
            clipboard = QApplication.clipboard()
            text = clipboard.text()
            if text:
                # Insert plain text at cursor position
                cursor = self.response_text.textCursor()
                cursor.insertText(text)
                logger.debug("Pasted text as plain text (formatting stripped)")
        except Exception as e:
            logger.error(f"Error pasting plain text: {e}")

    def handle_paste_event(self):
        """Handle paste event - check for images first, then allow text paste"""
        try:
            # Check clipboard content for debugging
            clipboard = QApplication.clipboard()
            mimeData = clipboard.mimeData()

            logger.debug(f"Clipboard formats: {mimeData.formats()}")
            logger.debug(f"Has image: {mimeData.hasImage()}")
            logger.debug(f"Has text: {mimeData.hasText()}")

            # If clipboard has an image, prevent text paste completely
            if mimeData.hasImage():
                # Try to get image from clipboard
                if image_manager.add_image_from_clipboard():
                    # Image was added successfully
                    self.update_image_status()
                    self.update_images_display()

                    # Note: Notification sound removed - should only play at application startup
                    logger.debug("Image pasted successfully (no sound notification)")

                    return True  # Event handled, don't process further
                else:
                    # Image detected but failed to add - allow normal text paste
                    logger.warning(
                        "Image detected in clipboard but failed to add - allowing text paste"
                    )
                    return False  # Allow default paste behavior
            else:
                # No image in clipboard, allow normal text paste
                logger.debug("No image in clipboard, allowing text paste")
                return False

        except Exception as e:
            logger.error(f"Error handling paste event: {e}")
            # On error, check if clipboard has image to prevent text paste
            try:
                clipboard = QApplication.clipboard()
                if clipboard.mimeData().hasImage():
                    return True  # Prevent paste if image is present
            except:
                pass
            return False  # Allow normal paste on error if no image

    def center_on_screen(self):
        """Center dialog on screen"""
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        self.move(
            (screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2
        )

    def clear_images(self):
        """Clear all images with better feedback and remove attachment text from input"""
        image_manager.clear_descriptions()
        self.update_images_display()
        self.update_image_status()
        # Remove attachment text from response input
        self.remove_attachment_text_from_input()
        # Keep response editor height unchanged when images are cleared
        try:
            self.adjust_window_height_for_images()
        except Exception:
            pass

    def remove_individual_image(self, index):
        """Remove a specific image by index"""
        try:
            # Check if it's a described image or pending image
            described_count = len(image_manager.image_descriptions)

            if index < described_count:
                # Remove from described images
                image_manager.remove_description(index)
            else:
                # Remove from pending images
                pending_index = index - described_count
                if 0 <= pending_index < len(image_manager.pending_images):
                    image_manager.pending_images.pop(pending_index)

            self.update_images_display()
            self.update_image_status()

            # If no images left, remove attachment text from input and reset height
            total_images = len(image_manager.image_descriptions) + len(
                image_manager.pending_images
            )
            if total_images == 0:
                self.remove_attachment_text_from_input()
                # Keep response editor height unchanged when images are cleared
                try:
                    self.adjust_window_height_for_images()
                except Exception:
                    pass

        except Exception as e:
            print(f"Error removing image {index}: {e}")

    def remove_attachment_text_from_input(self):
        """Remove attachment text (like '📷 Image pasted') from the response input"""
        try:
            current_text = self.response_text.toPlainText()
            # Remove common attachment patterns
            import re

            # Pattern to match any potential image attachment notifications
            # (keeping for backward compatibility with any existing text)
            patterns = [
                r"📷 Image pasted \(\d+ images? attached\)",
                r"📷 Image pasted \(1 image attached\)",
                r"📷 \d+ images? ready to send",
                r"📷 1 image ready to send",
                r"📷 Image attached and ready for preview",
                r"📷 \d+ images attached and ready for preview",
            ]

            for pattern in patterns:
                current_text = re.sub(pattern, "", current_text)

            # Clean up extra whitespace
            current_text = re.sub(
                r"\n\s*\n\s*\n", "\n\n", current_text
            )  # Multiple newlines to double
            current_text = current_text.strip()

            self.response_text.setPlainText(current_text)
        except Exception as e:
            print(f"Error removing attachment text: {e}")

    def update_image_status(self):
        """Update image status with professional styling"""
        total_images = len(image_manager.image_descriptions) + len(
            image_manager.pending_images
        )

        if total_images == 0:
            self.image_status.setText("No images attached")
            self.image_status.setProperty("statusType", "no_images")
        else:
            text = f"{total_images} image{'s' * (total_images != 1)} attached"
            self.image_status.setText(text)
            self.image_status.setProperty("statusType", "images_attached")

    def update_images_display(self):
        """Update the display of individual images in grid layout"""
        # Clear existing image widgets from grid layout
        while self.images_layout.count():
            child = self.images_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()  # Properly destroy widgets

        total_images = len(image_manager.image_descriptions) + len(
            image_manager.pending_images
        )

        if total_images == 0:
            # Hide both the scroll region and the entire image section when no images
            try:
                self.images_scroll_frame.hide()
            except Exception:
                pass
            try:
                if hasattr(self, "image_section_frame"):
                    self.image_section_frame.hide()
            except Exception:
                pass
            # Adjust overall dialog height down
            try:
                self.adjust_window_height_for_images()
            except Exception:
                pass
            return

        # Show the entire image section and the scroll frame when there are images
        try:
            if hasattr(self, "image_section_frame"):
                self.image_section_frame.show()
        except Exception:
            pass
        self.images_scroll_frame.show()
        # Adjust overall dialog height up
        try:
            self.adjust_window_height_for_images()
        except Exception:
            pass

        # Calculate grid dimensions (3 images per row)
        images_per_row = 3
        current_row = 0
        current_col = 0

        # Add individual image items - simplified labels
        for i, _description in enumerate(image_manager.image_descriptions):
            self.add_image_item_to_grid(i, True, current_row, current_col)
            current_col += 1
            if current_col >= images_per_row:
                current_col = 0
                current_row += 1

        # Add pending images - no "Pending" text, just show as images
        for i, _ in enumerate(image_manager.pending_images):
            self.add_image_item_to_grid(
                len(image_manager.image_descriptions) + i,
                False,
                current_row,
                current_col,
            )
            current_col += 1
            if current_col >= images_per_row:
                current_col = 0
                current_row += 1

    def add_image_item_to_grid(self, index, is_described, row, col):
        """Add an image item to grid layout with remove button"""
        # Create container with layout management
        container = QFrame()
        container.setProperty("containerType", "image")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(2, 2, 2, 2)
        container_layout.setSpacing(0)

        # Remove button at top right
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()

        remove_btn = QPushButton("✕")
        remove_btn.setProperty("buttonType", "remove_image")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.remove_individual_image(index))
        remove_btn.setToolTip("Remove image")  # Qt6
        top_row.addWidget(remove_btn)

        container_layout.addLayout(top_row)

        # Image preview
        preview_label = self.create_image_preview(index, is_described)
        if preview_label:
            container_layout.addWidget(preview_label)
        else:
            # Fallback placeholder
            placeholder = QLabel("IMG")
            placeholder.setProperty("labelType", "image_preview")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.addWidget(placeholder)

        # Add to grid layout
        self.images_layout.addWidget(container, row, col)

    def create_image_preview(self, index, is_described):
        """Create an image preview for grid layout"""
        try:
            # Get the actual image
            image = None
            if is_described:
                # For described images, get from processed images
                if index < len(image_manager.processed_images):
                    image = image_manager.processed_images[index]
            else:
                # For pending images
                pending_index = index - len(image_manager.image_descriptions)
                if 0 <= pending_index < len(image_manager.pending_images):
                    image = image_manager.pending_images[pending_index]

            if image:
                # Convert PIL image to QPixmap for display
                from PyQt6.QtGui import QPixmap, QImage

                try:
                    # Prefer direct conversion via ImageQt
                    from PIL.ImageQt import ImageQt

                    qim = ImageQt(image.copy())
                    pixmap = QPixmap.fromImage(qim)
                except Exception:
                    # Fallback: encode to PNG bytes and load into QImage
                    import io

                    buf = io.BytesIO()
                    safe_img = image
                    if safe_img.mode not in ("RGB", "RGBA"):
                        safe_img = safe_img.convert("RGBA")
                    safe_img.save(buf, format="PNG")
                    data = buf.getvalue()
                    qimg = QImage.fromData(data, "PNG")
                    pixmap = QPixmap.fromImage(qimg)

                # Create preview label - let QSS handle sizing
                preview_label = QLabel()
                preview_label.setPixmap(pixmap)
                preview_label.setProperty("labelType", "image_preview")
                preview_label.setScaledContents(True)
                preview_label.setToolTip("Image preview")

                return preview_label

        except Exception as e:
            print(f"Error creating image preview: {e}")

        # Fallback: return None if preview can't be created
        return None

    def adjust_window_height_for_images(self):
        """Adjust dialog height based on whether images are present.
        Keeps Agent Report area unchanged; only tweaks overall dialog height.
        """
        try:
            total_images = len(image_manager.image_descriptions) + len(
                image_manager.pending_images
            )
        except Exception:
            total_images = 0

        # Decide a target height; smaller when there are no images
        target_height = 560 if total_images == 0 else 720

        # Maintain width; animate height change smoothly if visible
        current_width = self.width()
        if not self.isVisible():
            try:
                self.resize(current_width, target_height)
            except Exception:
                pass
            return

        try:
            from PyQt6.QtCore import QPropertyAnimation, QRect

            self.resize_animation = QPropertyAnimation(self, b"geometry")
            self.resize_animation.setDuration(180)
            self.resize_animation.setStartValue(self.geometry())
            self.resize_animation.setEndValue(
                QRect(self.x(), self.y(), current_width, target_height)
            )
            self.resize_animation.start()
        except Exception:
            try:
                self.resize(current_width, target_height)
            except Exception:
                pass

    def show_memory_dialog(self):
        """Show project memory context in a dialog."""
        try:
            if not self.project_dir:
                QMessageBox.information(
                    self, "No Project", "No project directory available."
                )
                return

            # Get memory data
            memory_data = get_project_memory(self.project_dir)

            if "error" in memory_data:
                QMessageBox.information(
                    self,
                    "No Memory",
                    f"No memory data available: {memory_data.get('error', 'Unknown error')}",
                )
                return

            # Build memory content
            memory_content = f"## 📚 Project Memory: {memory_data['project_name']}\n\n"
            memory_content += f"**Project Hash**: {memory_data['project_hash']}\n"
            memory_content += f"**Last Updated**: {memory_data['last_updated']}\n\n"

            # Add event counts
            counts = memory_data.get("event_counts", {})
            if any(counts.values()):
                memory_content += "**Event Summary**:\n"
                if counts.get("milestone", 0) > 0:
                    memory_content += f"• Milestone: {counts['milestone']}\n"
                if counts.get("bug_solved", 0) > 0:
                    memory_content += f"• Bug Solved: {counts['bug_solved']}\n"
                if counts.get("user_preference", 0) > 0:
                    memory_content += (
                        f"• User Preference: {counts['user_preference']}\n"
                    )
                memory_content += "\n"

            # Add memories by category
            memories = memory_data.get("memories", {})
            for event_type, entries in memories.items():
                if entries:
                    memory_content += (
                        f"\n### {event_type.replace('_', ' ').title()}s\n\n"
                    )
                    for entry in entries:
                        memory_content += f"• {entry}\n"

            # Create dialog
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Memory: {memory_data['project_name']}")
            dialog.setModal(True)
            dialog.setMinimumSize(700, 500)

            # Apply same styling as parent
            dialog.setStyleSheet(self.styleSheet())

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(20, 20, 20, 20)

            # Memory display
            memory_display = QTextBrowser()
            memory_display.setOpenExternalLinks(False)
            memory_display.setProperty("textType", "professional")
            if hasattr(memory_display, "setMarkdown"):
                memory_display.setMarkdown(memory_content)
            else:
                memory_display.setPlainText(memory_content)
            layout.addWidget(memory_display)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.setProperty("buttonType", "secondary")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.clicked.connect(dialog.accept)
            close_btn.setMaximumWidth(120)
            layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignCenter)

            dialog.exec()

        except Exception as e:
            logger.error(f"Error showing memory dialog: {e}")
            QMessageBox.warning(self, "Error", f"Failed to show memory: {e}")

    def improve_with_ai(self):
        """Improve response with AI in a background thread with a cancelable progress dialog."""
        current_text = self.response_text.toPlainText().strip()
        if not current_text:
            QMessageBox.warning(self, "Warning", "Please enter some text first!")
            return

        # Ensure API key
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            api_key = self.prompt_for_gemini_api_key()
            if not api_key:
                return

        try:
            from google import genai
            from google.genai import types
            import io
        except Exception as e:
            QMessageBox.warning(
                self, "Error", f"Google GenAI library not available: {e}"
            )
            return

        def build_parts():
            prompt_text = f"""Improve this feedback text to be more professional, clear, and constructive:

Original text: {current_text}

Make it:
- More professional and polite
- Clearer and more specific
- Constructive and actionable
- Well-structured
- Reference specific details from images if relevant

Return only the improved text, no explanations."""
            all_images = []
            if (
                hasattr(image_manager, "processed_images")
                and image_manager.processed_images
            ):
                all_images.extend(image_manager.processed_images)
            if (
                hasattr(image_manager, "pending_images")
                and image_manager.pending_images
            ):
                all_images.extend(image_manager.pending_images)
            if (
                hasattr(image_manager, "image_descriptions")
                and image_manager.image_descriptions
            ):
                image_context = "\n\n".join(image_manager.image_descriptions)
                prompt_text += (
                    f"\n\nPrevious Image Context (for reference):\n{image_context}"
                )
            parts = [types.Part.from_text(text=prompt_text)]
            MAX_IMAGES_FOR_AI = 5
            MAX_IMAGE_SIDE = 1600
            for image in all_images[:MAX_IMAGES_FOR_AI]:
                try:
                    img = image.copy()
                    if max(img.size) > MAX_IMAGE_SIDE:
                        img.thumbnail(
                            (MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS
                        )
                    has_alpha = img.mode in ("RGBA", "LA") or (
                        img.mode == "P" and "transparency" in img.info
                    )
                    mime_type = "image/png" if has_alpha else "image/jpeg"
                    with io.BytesIO() as buffer:
                        if has_alpha:
                            img.save(buffer, format="PNG", optimize=True)
                        else:
                            if img.mode != "RGB":
                                img = img.convert("RGB")
                            img.save(
                                buffer,
                                format="JPEG",
                                quality=85,
                                optimize=True,
                                progressive=True,
                            )
                        data = buffer.getvalue()
                    parts.append(types.Part.from_bytes(mime_type=mime_type, data=data))
                except Exception as e:
                    logger.warning(f"Skipping image for AI due to error: {e}")
            return parts

        try:
            parts = build_parts()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to prepare AI request: {e}")
            return

        progress = QProgressDialog("Improving text with AI...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        cancelled = {"v": False}
        progress.canceled.connect(lambda: cancelled.__setitem__("v", True))

        result = {"done": False, "ok": False, "text": "", "err": None}

        def worker():
            try:
                client = genai.Client(api_key=api_key)
                cfg = types.GenerateContentConfig(response_mime_type="text/plain")
                contents = [types.Content(role="user", parts=parts)]
                resp = client.models.generate_content(
                    model="gemini-2.5-flash", contents=contents, config=cfg
                )
                if cancelled["v"]:
                    result.update({"done": True})
                    return
                improved = (resp.text or "").strip()
                result.update({"done": True, "ok": True, "text": improved})
            except Exception as e:
                result.update({"done": True, "ok": False, "err": e})

        import threading as _th

        t = _th.Thread(target=worker, daemon=True)
        t.start()

        def poll():
            if result["done"]:
                progress.reset()
                if cancelled["v"]:
                    QMessageBox.information(
                        self, "Cancelled", "AI improvement cancelled."
                    )
                    return
                if result["ok"]:
                    self.response_text.setPlainText(result["text"])
                    QMessageBox.information(self, "Success", "Text improved with AI!")
                else:
                    QMessageBox.warning(
                        self, "Error", f"AI improvement failed: {result['err']}"
                    )
            else:
                QTimer.singleShot(150, poll)

        progress.show()
        QTimer.singleShot(150, poll)

    def prompt_for_gemini_api_key(self):
        """Show a popup dialog to enter Gemini API key and save it to .env file"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Gemini API Key Required")
        dialog.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        dialog.setModal(True)
        dialog.resize(500, 200)

        # Center the dialog
        screen = QApplication.primaryScreen().geometry()
        size = dialog.geometry()
        dialog.move(
            (screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2
        )

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title and description
        title_label = QLabel("🔑 Enter your Gemini API Key")
        title_label.setProperty("labelType", "api_title")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "Please enter your Google Gemini API key. It will be saved securely in your .env file."
        )
        desc_label.setProperty("labelType", "api_description")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # API key input
        api_key_input = QLineEdit()
        api_key_input.setPlaceholderText("Enter your Gemini API key here...")
        api_key_input.setEchoMode(QLineEdit.Password)  # Hide the key as it's typed
        api_key_input.setProperty("inputType", "api_key")
        layout.addWidget(api_key_input)

        # Buttons
        button_layout = QHBoxLayout()

        cancel_button = QPushButton("Cancel")
        cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_button.clicked.connect(dialog.reject)
        cancel_button.setProperty("buttonType", "api_cancel")
        button_layout.addWidget(cancel_button)

        button_layout.addStretch()

        save_button = QPushButton("Save API Key")
        save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        save_button.clicked.connect(dialog.accept)
        save_button.setDefault(True)
        save_button.setProperty("buttonType", "api_save")
        button_layout.addWidget(save_button)

        layout.addLayout(button_layout)

        # Set focus to input field
        api_key_input.setFocus()

        # Show dialog and get result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            api_key = api_key_input.text().strip()
            if api_key:
                # Save to .env file
                if self.save_api_key_to_env(api_key):
                    QMessageBox.information(
                        self, "Success", "API key saved successfully!"
                    )
                    # Update environment variable for current session
                    os.environ["GEMINI_API_KEY"] = api_key
                    return api_key
                else:
                    QMessageBox.warning(
                        self, "Error", "Failed to save API key to .env file!"
                    )
                    return None
            else:
                QMessageBox.warning(self, "Warning", "Please enter a valid API key!")
                return None

        return None

    def save_api_key_to_env(self, api_key):
        """Save the API key to .env file in MCP server directory"""
        try:
            # Use absolute path based on module location to ensure .env is saved in MCP server directory
            mcp_server_dir = Path(__file__).parent.absolute()
            env_file_path = mcp_server_dir / ".env"

            # Read existing .env content
            existing_content = ""
            if env_file_path.exists():
                with open(env_file_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()

            # Check if GEMINI_API_KEY already exists
            lines = existing_content.split("\n")
            updated_lines = []
            key_found = False

            for line in lines:
                if line.strip().startswith("GEMINI_API_KEY="):
                    # Replace existing key
                    updated_lines.append(f"GEMINI_API_KEY={api_key}")
                    key_found = True
                else:
                    updated_lines.append(line)

            # If key wasn't found, add it
            if not key_found:
                if updated_lines and updated_lines[-1].strip():
                    updated_lines.append("")  # Add blank line before new key
                updated_lines.append(f"GEMINI_API_KEY={api_key}")

            # Write back to file
            with open(env_file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(updated_lines))

            logger.info(f"API key saved to: {env_file_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving API key to .env: {e}")
            return False

    def send_response(self):
        """Send the response"""
        # Use get_expanded_text() to expand slash commands to their full templates
        if hasattr(self.response_text, "get_expanded_text"):
            try:
                response = self.response_text.get_expanded_text().strip()
            except Exception as e:
                self.logger.error(f"Error expanding slash commands: {e}")
                response = self.response_text.toPlainText().strip()
        else:
            response = self.response_text.toPlainText().strip()

        if not response:
            # If input is empty, send default response that project leader agrees to continue
            response = "Project leader agrees, continue."

        # Build final response
        final_response = response

        # Add image descriptions if any
        if (
            hasattr(image_manager, "image_descriptions")
            and image_manager.image_descriptions
        ):
            final_response += "\n\n[Image Context]\n" + "\n".join(
                image_manager.image_descriptions
            )

        self.result = final_response
        self.accept()

    def get_response(self) -> str:
        """Get the final response"""
        return self.result

    def _get_stop_delay(self) -> float:
        """Get stop delay from environment variable (in seconds)"""
        try:
            delay_str = os.getenv("APP_STOP_DELAY", "1.5").strip()
            delay = float(delay_str)
            # Clamp to reasonable range: 0-10 seconds
            return max(0.0, min(10.0, delay))
        except (ValueError, TypeError) as e:
            # M2: Log actual invalid value in exception
            logger.warning(
                f"Invalid APP_STOP_DELAY value '{delay_str}' ({type(delay_str).__name__}): {e}. Using default 1.5 seconds"
            )
            return 1.5

    def closeEvent(self, event):
        """Override to signal worker threads before closing (C1 & C2 fix)"""
        with self._stop_worker_lock:
            self._is_closing = True
            self._stop_cancelled = True
        super().closeEvent(event)

    def stop_cursor(self):
        """Stop Cursor execution with configurable delay then send stop signals

        Flow:
            1. Dialog closes immediately when stop button clicked
            2. Background thread waits for configured delay (APP_STOP_DELAY) for Cursor to start streaming
            3. Send Ctrl+Alt+B twice to stop Cursor
            4. Send Ctrl+Shift+Backspace for final stop signal

        Thread Safety:
            - Worker thread runs in daemon mode and continues after dialog closes
            - No UI updates after dialog closes
        """

        # Check if cursor control is disabled
        if self._is_cursor_control_disabled():
            logger.debug("Cursor control disabled - ignoring stop command")
            QMessageBox.information(
                self,
                "Disabled",
                "Cursor control functionality is disabled in settings.",
            )
            return

        # Get configurable delay
        stop_delay = self._get_stop_delay()

        def stop_cursor_worker():
            """Worker function to execute focus_cursor sequence in background

            Sequence:
            1. Initialize COM with MULTITHREADED mode in this worker thread
            2. Wait for configured delay (APP_STOP_DELAY) for Cursor to start streaming
            3. Send Ctrl+Alt+B twice to stop Cursor
            4. Send Ctrl+Shift+Backspace for final stop signal
            """
            try:
                # Initialize COM with MULTITHREADED mode in this worker thread
                # This is separate from main thread's APARTMENTTHREADED mode
                if platform.system() == "Windows":
                    try:
                        import pythoncom

                        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                        logger.debug(
                            "Stop worker thread: COM initialized as MULTITHREADED for pywinauto"
                        )
                    except Exception as e:
                        logger.debug(
                            f"Stop worker thread: COM initialization note: {e}"
                        )

                # Check if focus_cursor functionality is available
                if not HAS_FOCUS_CURSOR:
                    logger.warning("Focus cursor module not available for stop cursor")
                    return

                logger.info(f"Executing stop sequence with {stop_delay}s delay...")

                # Pass stop_delay to focus_cursor functions
                global _cached_cursor_windows
                success = False

                # Lazy discovery: Only discover windows when Stop button is actually pressed
                if not _cached_cursor_windows:
                    logger.info(
                        "Discovering Cursor windows on-demand (first stop press)..."
                    )
                    _cached_cursor_windows = find_cursor_windows() or []
                    if _cached_cursor_windows:
                        logger.info(
                            f"✓ Discovered {len(_cached_cursor_windows)} Cursor window(s)"
                        )
                    else:
                        logger.warning("No Cursor windows found")

                if _cached_cursor_windows:
                    logger.info("Using cached Cursor windows...")
                    success = focus_and_send_stop_hotkey_to_any(
                        _cached_cursor_windows, stop_delay
                    )
                else:
                    logger.info("No cached windows, using fallback discovery...")
                    success = focus_cursor_and_send_hotkey(stop_delay)

                if success:
                    logger.info("✓ Stop sequence completed successfully")
                else:
                    logger.warning("Failed to send stop hotkeys")

            except Exception as e:
                logger.error(f"Error executing stop cursor: {e}")
            finally:
                # Cleanup COM in worker thread
                if platform.system() == "Windows":
                    try:
                        import pythoncom

                        pythoncom.CoUninitialize()
                        logger.debug("Stop worker thread: COM uninitialized")
                    except Exception:
                        pass

        # Check if focus_cursor functionality is available
        if HAS_FOCUS_CURSOR:
            # Start worker thread in daemon mode (runs in background after dialog closes)
            focus_thread = threading.Thread(target=stop_cursor_worker, daemon=True)
            focus_thread.start()
            logger.info("Stop cursor thread started, dialog closing immediately")
        else:
            logger.warning(
                "Cannot execute stop cursor - focus_cursor module not available"
            )

        # Close dialog immediately
        self.reject()

    def event(self, event):
        """Handle custom events"""
        if isinstance(event, UpdateButtonEvent):
            # Update stop button text from worker thread
            if self.stop_button_ref and hasattr(self.stop_button_ref, "setText"):
                self.stop_button_ref.setText(event.text)
            return True
        elif isinstance(event, StopOperationCompleteEvent):
            # H4 fix: Handle completion event
            if event.success:
                logger.info("Stop operation completed successfully")
            else:
                logger.info("Stop operation completed with errors")
            # Close dialog after operation completes
            self.reject()
            return True
        return super().event(event)

    def mousePressEvent(self, event):
        """Handle mouse press for window dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release for window dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = None
            event.accept()


def create_modern_feedback_dialog(
    agent_comment: str = "", project_dir: str = None
) -> str:
    """Create and show modern feedback dialog

    THREADING ARCHITECTURE: This function runs in the MainThread of a subprocess
    launched by ask_to_leader_project(). The subprocess approach was implemented
    to solve Qt threading issues that occurred with the previous asyncio.to_thread()
    implementation.

    SOLUTION: Qt runs safely in MainThread of subprocess, avoiding worker thread crashes.
    """
    # CRITICAL: Log FIRST before any Qt calls that might crash from worker thread
    try:
        logger.info("=" * 80)
        logger.info("ENTERING create_modern_feedback_dialog")
        logger.info(f"Agent comment length: {len(agent_comment)}")
        logger.info(f"Project dir: {project_dir}")
        logger.info(f"Current thread: {threading.current_thread().name}")
        logger.info(f"Thread ID: {threading.get_ident()}")
        logger.info(
            f"Is main thread: {threading.current_thread() == threading.main_thread()}"
        )
    except Exception as e:
        # If even logging crashes, something is very wrong
        print(f"CRITICAL: Logging failed in create_modern_feedback_dialog: {e}")
        raise

    # Reload .env from MCP server directory to pick up any runtime changes
    mcp_server_dir = Path(__file__).parent.absolute()
    env_file_path = mcp_server_dir / ".env"
    logger.debug(f"Loading .env from: {env_file_path}")
    load_dotenv(dotenv_path=env_file_path, override=True)
    logger.debug(".env file loaded successfully")

    # COM is already initialized at module load time for Windows
    # See com_init.py which is imported first
    if platform.system() == "Windows" and com_init.COM_INITIALIZED:
        logger.debug("COM was initialized at module load - clipboard should work")
    elif platform.system() == "Windows":
        logger.warning("COM was NOT initialized properly - clipboard may not work!")

    logger.debug(
        f"Platform: {platform.system()}, COM initialized: {com_init.COM_INITIALIZED if platform.system() == 'Windows' else 'N/A'}"
    )

    # Enable HiDPI scaling (safe-guarded)
    try:
        logger.debug("Setting Qt HiDPI attributes...")
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        logger.debug("Qt HiDPI attributes set successfully")
    except Exception as e:
        logger.warning(
            f"Failed to set HiDPI attributes (may be normal from worker thread): {e}"
        )

    # Create QApplication if it doesn't exist
    # CRITICAL: QApplication.instance() can crash when called from worker threads
    try:
        logger.debug("About to call QApplication.instance()...")
        logger.debug(
            f"Current thread before Qt call: {threading.current_thread().name}"
        )
        app = QApplication.instance()
        logger.debug(f"QApplication.instance() returned: {app is not None}")
    except Exception as e:
        logger.error(
            f"CRITICAL: QApplication.instance() crashed from thread {threading.current_thread().name}: {e}",
            exc_info=True,
        )
        raise RuntimeError(
            f"Qt threading error - cannot create UI from worker thread. Must run on main thread. Error: {e}"
        ) from e
    if app is None:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")  # Modern look

        # Set default theme preference (fallback if QSS loading fails)
        preferred_dark = True  # Default to dark mode

        # Try to apply external QSS once the app is created
        try:
            # Use absolute paths based on script location to work from any working directory
            script_dir = Path(__file__).parent.absolute()
            logger.info(f"Script directory for QSS loading: {script_dir}")

            # Check .env for theme preference, default to dark mode
            # Use consolidated environment loading (load_dotenv already called at module level)
            # Get theme preference with strict validation to prevent injection
            def validate_app_dark_mode(value):
                """Validate APP_DARK_MODE environment variable to prevent injection."""
                if not value:
                    return "true"  # Default to dark mode

                # Strip and sanitize input
                clean_value = str(value).strip().lower()

                # Only allow specific safe values
                valid_true_values = {"1", "true", "yes", "on"}
                valid_false_values = {"0", "false", "no", "off"}

                if clean_value in valid_true_values:
                    return "true"
                elif clean_value in valid_false_values:
                    return "false"
                else:
                    logger.warning(
                        f"Invalid APP_DARK_MODE value '{value}'. Using default: true"
                    )
                    return "true"

            # Get and validate environment variable (no duplicate loading needed)
            app_dark_mode_raw = os.getenv("APP_DARK_MODE", "true")
            app_dark_mode_validated = validate_app_dark_mode(app_dark_mode_raw)
            preferred_dark = app_dark_mode_validated == "true"
            logger.info(
                f"Theme from environment - APP_DARK_MODE: '{app_dark_mode_raw}' -> validated: '{app_dark_mode_validated}' -> Dark mode: {preferred_dark}"
            )

            # Set QSS file order based on preference (dark mode is default)
            if preferred_dark:
                qss_paths = [
                    script_dir / "styles/app_dark.qss",
                    script_dir / "styles/app_light.qss",  # fallback
                ]
                logger.info("Using dark theme preference")
            else:
                qss_paths = [
                    script_dir / "styles/app_light.qss",
                    script_dir / "styles/app_dark.qss",  # fallback
                ]
                logger.info("Using light theme preference")

            for p in qss_paths:
                logger.debug(f"Checking QSS file in create_modern_feedback_dialog: {p}")
                if p.exists():
                    logger.info(
                        f"Loading QSS file in create_modern_feedback_dialog: {p}"
                    )
                    with open(p, "r", encoding="utf-8") as f:
                        css_content = f.read()
                        app.setStyleSheet(css_content)
                        logger.info(
                            f"Applied QSS to app in create_modern_feedback_dialog: {len(css_content)} characters"
                        )
                    break
                else:
                    logger.debug(
                        f"QSS file not found in create_modern_feedback_dialog: {p}"
                    )
        except Exception as e:
            logger.warning(f"Failed loading QSS in create_modern_feedback_dialog: {e}")
            # preferred_dark already has default value (True) set before try block
    else:
        # QApplication already exists - set default theme preference
        preferred_dark = True  # Default to dark mode

    # Create and show dialog
    logger.info("Creating ModernTaskMasterDialog instance...")
    try:
        dialog = ModernTaskMasterDialog(agent_comment, preferred_dark, project_dir)
        logger.info("ModernTaskMasterDialog created successfully")
    except Exception as e:
        logger.error(f"Failed to create ModernTaskMasterDialog: {e}", exc_info=True)
        raise

    logger.info("Showing dialog with exec_() - THIS WILL BLOCK until user responds")
    logger.debug(f"Dialog parent: {dialog.parent()}")
    logger.debug(f"Dialog modal: {dialog.isModal()}")

    # CRITICAL FIX: Process events before exec_() to allow QWebEngineView to initialize
    # QWebEngineView needs the event loop to load HTML content
    logger.debug("Processing pending events before dialog.exec()...")
    app.processEvents()
    logger.debug("Events processed, now calling dialog.exec()...")

    dialog_result = dialog.exec()

    logger.info(
        f"Dialog closed - Result code: {dialog_result} (Accepted={QDialog.DialogCode.Accepted}, Rejected={QDialog.DialogCode.Rejected})"
    )

    if dialog_result == QDialog.DialogCode.Accepted:
        response = dialog.get_response()
        logger.info(f"User accepted - Response length: {len(response)}")
        logger.debug(
            f"Response preview: {response[:200]}..."
            if len(response) > 200
            else f"Response: {response}"
        )
        return response
    else:
        logger.info("User cancelled or rejected dialog")
        return ""  # User cancelled
    # Note: We don't uninitialize COM here because it was initialized at module load
    # and should persist for the lifetime of the process


# Global variables to maintain temporary session state
_session_config = {
    "cleanup_files": False,  # DISABLED by default - always
    "wordpress_cs": False,  # DISABLED by default - always
    "wp_dev": False,  # DISABLED by default - NOT reset
    "laravel_dev": False,  # DISABLED by default - NOT reset
}
_session_lock = threading.Lock()


def get_additional_instructions_config() -> dict:
    """
    Gets the configuration for additional instructions.
    It now uses fixed default values and only maintains temporary changes in the session.
    It also includes custom instructions.
    """
    config = _session_config.copy()

    # Add status of custom instructions
    custom_instructions = load_custom_instructions()
    for instruction in custom_instructions:
        instruction_id = instruction["id"]
        # If not in the state, use False as default
        config[f"custom_{instruction_id}"] = _custom_instructions_state.get(
            instruction_id, False
        )

    return config


def reset_session_config():
    """Resets the configuration to the default values"""
    global _session_config, _custom_instructions_state
    _session_config = {
        "cleanup_files": False,  # DISABLED by default - always
        "wordpress_cs": False,  # DISABLED by default - always
        # wp_dev and laravel_dev are NOT reset - they are maintained during the session
        "wp_dev": _session_config.get("wp_dev", False),
        "laravel_dev": _session_config.get("laravel_dev", False),
    }

    # 🔧 FIX: Preserve persistent custom instructions
    # Only reset non-persistent ones, keep persistent ones
    custom_instructions = load_custom_instructions()
    for instruction in custom_instructions:
        instruction_id = instruction["id"]
        if instruction.get("persistent", False):
            # Persistent: maintain current state
            # Do nothing, keep the value in _custom_instructions_state
            pass
        else:
            # NOT persistent: reset to False
            _custom_instructions_state[instruction_id] = False


def update_session_config(config: dict):
    """Updates the temporary session configuration"""
    global _session_config, _custom_instructions_state

    # Separate standard configuration from custom instructions
    standard_config = {}
    custom_config = {}

    for key, value in config.items():
        if key.startswith("custom_"):
            instruction_id = key.replace("custom_", "")
            custom_config[instruction_id] = value
        else:
            standard_config[key] = value

    # Update configurations with locks
    with _session_lock:
        _session_config.update(standard_config)
    with _custom_state_lock:
        _custom_instructions_state.update(custom_config)


# The save functions are no longer necessary - temporary session configuration is used

# ============================================================================
# CUSTOM INSTRUCTIONS SYSTEM
# ============================================================================


def get_custom_instructions_file() -> Path:
    """Gets the path of the custom instructions file"""
    script_dir = Path(__file__).parent.absolute()
    config_dir = script_dir / "config"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "custom_instructions.json"


def load_custom_instructions() -> list:
    """Loads the custom instructions from the JSON file with validation and safe fallback"""
    file_path = get_custom_instructions_file()
    try:
        if not file_path.exists():
            logger.info(f"Custom instructions file not found: {file_path}")
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Custom instructions JSON root is not an object; resetting")
            return []
        instructions = data.get("instructions", [])
        if not isinstance(instructions, list):
            logger.warning(
                "Custom instructions 'instructions' is not a list; resetting"
            )
            return []
        valid = []
        for inst in instructions:
            if not isinstance(inst, dict):
                continue
            if not {"id", "titulo", "prompt", "persistent"}.issubset(inst.keys()):
                continue
            valid.append(inst)
        return valid
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in custom instructions: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading custom instructions: {e}")
        return []


def save_custom_instructions(instructions: list) -> bool:
    """Saves the custom instructions atomically with backup and validation"""
    try:
        if not isinstance(instructions, list):
            raise ValueError("instructions must be a list")
        file_path = get_custom_instructions_file()
        tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        data = {"instructions": instructions}
        # Write temp
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # Backup existing
        if file_path.exists():
            try:
                if backup_path.exists():
                    os.remove(backup_path)
                os.replace(file_path, backup_path)
            except Exception:
                pass
        # Move temp into place
        os.replace(tmp_path, file_path)
        return True
    except Exception as e:
        logger.error(f"Error saving custom instructions: {e}")
        try:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False


def create_custom_instruction(titulo: str, prompt: str, persistent: bool) -> dict:
    """Creates a new custom instruction"""
    return {
        "id": str(uuid.uuid4()),
        "titulo": titulo,
        "prompt": prompt,
        "persistent": persistent,
    }


def add_custom_instruction(titulo: str, prompt: str, persistent: bool) -> bool:
    """Adds a new custom instruction"""
    instructions = load_custom_instructions()
    new_instruction = create_custom_instruction(titulo, prompt, persistent)
    instructions.append(new_instruction)
    return save_custom_instructions(instructions)


def update_custom_instruction(
    instruction_id: str, titulo: str, prompt: str, persistent: bool
) -> bool:
    """Updates an existing custom instruction"""
    instructions = load_custom_instructions()
    for instruction in instructions:
        if instruction["id"] == instruction_id:
            instruction["titulo"] = titulo
            instruction["prompt"] = prompt
            instruction["persistent"] = persistent
            return save_custom_instructions(instructions)
    return False


def delete_custom_instruction(instruction_id: str) -> bool:
    """Deletes a custom instruction"""
    instructions = load_custom_instructions()
    instructions = [inst for inst in instructions if inst["id"] != instruction_id]
    return save_custom_instructions(instructions)


# Global variables to maintain custom instructions state
_custom_instructions_state = {}
_custom_state_lock = threading.Lock()

# Internal functions to control checkbox configuration (NOT tools)
# These functions only control what text is added to the prompt, they are not MCP tools


def toggle_cleanup_files(enabled: bool) -> str:
    """Activates or deactivates the file cleanup instruction (internal function, not a tool).

    Args:
        enabled: True to activate, False to deactivate

    Returns:
        Confirmation message of the change
    """
    global _session_config
    _session_config["cleanup_files"] = enabled
    status = "activated" if enabled else "deactivated"
    return f"✅ Cleanup Files {status}. " + (
        "An instruction will be added to delete irrelevant files."
        if enabled
        else "No cleanup instruction will be added."
    )


def toggle_wordpress_cs(enabled: bool) -> str:
    """Activates or deactivates the WordPress Coding Standards instruction (internal function, not a tool).

    Args:
        enabled: True to activate, False to deactivate

    Returns:
        Confirmation message of the change
    """
    global _session_config
    _session_config["wordpress_cs"] = enabled
    status = "activated" if enabled else "deactivated"
    return f"✅ WordPress CS {status}. " + (
        "An instruction will be added about WordPress standards and sanitization."
        if enabled
        else "No WordPress CS instruction will be added."
    )


def toggle_wp_dev(enabled: bool) -> str:
    """Activates or deactivates the WordPress Development instructions (internal function, not a tool).

    Args:
        enabled: True to activate, False to deactivate

    Returns:
        Confirmation message of the change
    """
    global _session_config
    _session_config["wp_dev"] = enabled
    status = "activated" if enabled else "deactivated"
    return f"✅ WP Dev {status}. " + (
        "An instruction will be added about WordPress best practices."
        if enabled
        else "No WP Dev instruction will be added."
    )


def toggle_laravel_dev(enabled: bool) -> str:
    """Activates or deactivates the Laravel Development instructions (internal function, not a tool).

    Args:
        enabled: True to activate, False to deactivate

    Returns:
        Confirmation message of the change
    """
    global _session_config
    _session_config["laravel_dev"] = enabled
    status = "activated" if enabled else "deactivated"
    return f"✅ Laravel Dev {status}. " + (
        "An instruction will be added about Laravel best practices."
        if enabled
        else "No Laravel Dev instruction will be added."
    )


# Memory save tool - for saving new memory entries
@mcp.tool()
async def memory_save(
    event_type: Literal["milestone", "bug_solved", "user_preference"],
    description: str,
    project_dir: str,
    ctx: Context,
) -> str:
    """Save important development events to the current project's memory database.

    Creates a structured memory database with separate folders for each unique project
    and categorized storage for different event types.

    Args:
        event_type: Type of event to save (milestone, bug_solved, user_preference)
        description: Event description
        project_dir: Absolute path to the client's project root directory (REQUIRED)
        ctx: FastMCP Context for logging and access to client capabilities

    Note: The project_dir parameter is necessary because the FastMCP Context does not provide
    direct access to the client's working directory. The user must explicitly specify
    their project path.
    """
    logger.info("=" * 60)
    logger.info("MEMORY DATABASE TRANSACTION INITIATED - memory_save")
    logger.info(f"Event type: {event_type}")
    logger.info(f"Description length: {len(description)} characters")
    logger.info(f"Description preview: {description[:200]}...")
    logger.info(f"Project dir: {project_dir}")
    logger.info(f"Context provided: {ctx is not None}")
    logger.debug(f"Current thread: {threading.current_thread().name}")
    logger.info("=" * 60)

    await ctx.info(f"Saving event {event_type} in project: {project_dir}")
    logger.debug("Context.info call successful in memory_save")

    try:
        # Step 1: Setup memory database structure
        # Use MCP server's directory as base
        mcp_server_dir = Path(__file__).parent.absolute()
        memory_base_dir = mcp_server_dir / "memory"
        memory_base_dir.mkdir(exist_ok=True)

        # Create unique folder name from project path hash (normalize to lowercase)
        normalized_project_dir = project_dir.replace("\\", "/").lower()
        project_hash = hashlib.md5(normalized_project_dir.encode()).hexdigest()[:8]
        project_memory_dir = memory_base_dir / f"project_{project_hash}"
        project_memory_dir.mkdir(exist_ok=True)

        # Step 2: Update index.json to track project mappings
        index_file = memory_base_dir / "index.json"
        index_data = {}

        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load index.json: {e}")
                index_data = {}

        # Update index with current project
        index_data[project_hash] = {
            "project_path": project_dir,
            "last_updated": datetime.now().isoformat(),
            "event_counts": index_data.get(project_hash, {}).get(
                "event_counts", {"milestone": 0, "bug_solved": 0, "user_preference": 0}
            ),
        }

        # Increment event count
        index_data[project_hash]["event_counts"][event_type] += 1

        # Save updated index
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

        # Step 3: Save the memory entry with embedding support
        timestamp = datetime.now().isoformat()
        event_prefix = {
            "milestone": "🎯 MILESTONE",
            "bug_solved": "🐛 BUG SOLVED",
            "user_preference": "👤 USER PREFERENCE",
        }

        # Create structured memory entry
        memory_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "event_type": event_type,
            "title": f"{event_prefix[event_type]}",
            "description": description,
            "embedding": None,  # Will be computed later
        }

        # Define memory file path before caching logic
        memory_file = project_memory_dir / f"{event_type}s.json"

        # Generate embedding for the description with caching
        try:
            # Check if we already have a cached embedding for this exact text
            text_hash = hashlib.md5(description.encode("utf-8")).hexdigest()

            # Look for existing entry with same text hash to reuse embedding
            cached_embedding = None
            if memory_file.exists():
                try:
                    with open(memory_file, "r", encoding="utf-8") as f:
                        existing_entries_for_cache = json.load(f)

                    for entry in existing_entries_for_cache:
                        entry_text_hash = hashlib.md5(
                            entry.get("description", "").encode("utf-8")
                        ).hexdigest()
                        if entry_text_hash == text_hash and entry.get("embedding"):
                            cached_embedding = entry["embedding"]
                            logger.info("Found cached embedding for identical text")
                            break
                except Exception:
                    pass  # Continue with fresh embedding if cache check fails

            if cached_embedding:
                memory_entry["embedding"] = cached_embedding
                memory_entry["text_hash"] = text_hash
                logger.info("Reused cached embedding for memory entry")
            else:
                embedding = await get_embedding_with_cache(description)
                memory_entry["embedding"] = embedding
                memory_entry["text_hash"] = text_hash
                logger.info(
                    f"Generated new {EMBEDDING_PROVIDER} embedding for memory entry"
                )

        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
            # Continue without embedding - fallback to text search
            memory_entry["text_hash"] = hashlib.md5(
                description.encode("utf-8")
            ).hexdigest()

        # Load existing entries
        existing_entries = []
        if memory_file.exists():
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    existing_entries = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load existing entries: {e}")
                existing_entries = []

        # Add new entry
        existing_entries.append(memory_entry)

        # Save updated entries
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(existing_entries, f, indent=2, ensure_ascii=False)

        # Step 4: Log success and return result
        total_events = sum(index_data[project_hash]["event_counts"].values())
        result_message = (
            f"✅ Memory saved successfully!\n"
            f"📁 Project: {project_hash} ({Path(project_dir).name})\n"
            f"📝 File: {memory_file.name}\n"
            f"📊 Total events for this project: {total_events}\n"
            f"🗂️ Database location: {memory_base_dir}"
        )

        logger.info(f"Memory entry saved: {memory_file}")
        logger.info(f"Project index updated: {index_file}")
        await ctx.info(result_message)

        return result_message

    except Exception as e:
        error_msg = f"❌ Failed to save memory entry: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return error_msg


# Memory call tool - RAG-based retrieval
@mcp.tool()
async def memory_call(
    project_dir: str,
    ctx: Context,
    query: str = "",
    event_type: Literal["milestone", "bug_solved", "user_preference", "all"] = "all",
    limit: int = None,
) -> str:
    """Retrieve relevant memory entries using RAG (Retrieval-Augmented Generation).

    Uses semantic search to find the most relevant memory entries based on the query.
    Falls back to recent entries if no query is provided.

    Args:
        project_dir: Absolute path to the client's project root directory (REQUIRED)
        ctx: FastMCP Context for logging and access to client capabilities
        query: Search query to find relevant memories (optional)
        event_type: Type of events to retrieve (milestone, bug_solved, user_preference, all)
        limit: Maximum number of entries to retrieve (default: from env MEMORY_RAG_TOP_K)

    Returns:
        Formatted memory entries with relevance scores and timestamps
    """
    # Set default limit from environment
    if limit is None:
        limit = MEMORY_RAG_TOP_K
        logger.debug(f"Using default limit from MEMORY_RAG_TOP_K: {limit}")
    else:
        logger.debug(f"Using provided limit: {limit}")

    logger.info("=" * 60)
    logger.info("RAG MEMORY RETRIEVAL INITIATED - memory_call")
    logger.info(f"Project dir: {project_dir}")
    logger.info(f"Query: {query}")
    logger.info(f"Query length: {len(query)} characters")
    logger.info(f"Event type filter: {event_type}")
    logger.info(f"Context provided: {ctx is not None}")
    logger.debug(f"Current thread: {threading.current_thread().name}")
    logger.info(f"Limit: {limit}")
    logger.info("=" * 60)

    await ctx.info(
        f"Retrieving memory from project: {project_dir} with query: '{query}'"
    )

    try:
        # Get relevant memories using RAG
        relevant_memories = await get_relevant_memories(
            project_dir, query, event_type, limit, ctx
        )

        if "error" in relevant_memories:
            error_msg = f"❌ {relevant_memories['error']}"
            logger.warning(error_msg)
            await ctx.warning(error_msg)
            return error_msg

        # Format the response
        result = f"## 📚 Project Memory: {relevant_memories['project_name']}\n\n"
        result += f"**Project Hash**: {relevant_memories['project_hash']}\n"
        result += f"**Last Updated**: {relevant_memories['last_updated']}\n"

        if query:
            result += f'**Search Query**: "{query}"\n\n'

        # Add event counts
        counts = relevant_memories.get("event_counts", {})
        if any(counts.values()):
            result += "**Event Summary**:\n"
            for event, count in counts.items():
                if count > 0:
                    result += f"• {event.replace('_', ' ').title()}: {count}\n"
            result += "\n"

        # Add relevant memory entries
        memories = relevant_memories.get("relevant_entries", [])

        if memories:
            result += f"### Most Relevant Memories (Top {len(memories)})\n"
            for i, entry in enumerate(memories, 1):
                timestamp = entry.get("timestamp", "Unknown")
                # Format timestamp for display
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    formatted_time = timestamp

                event_type_display = (
                    entry.get("event_type", "unknown").replace("_", " ").title()
                )
                title = entry.get("title", "")
                description = entry.get("description", "")
                relevance = entry.get("relevance_score", 0.0)

                result += f"\n**{i}. {title}** ({event_type_display})\n"
                result += f"📅 **Time**: {formatted_time}\n"
                if query and relevance > 0:
                    result += f"🎯 **Relevance**: {relevance:.3f}\n"
                result += f"📝 **Details**: {description}\n"
        else:
            result += "No relevant memories found.\n"

        logger.info(f"RAG memory retrieval successful: {len(memories)} entries found")
        await ctx.info(f"Retrieved {len(memories)} relevant memory entries")

        return result

    except Exception as e:
        error_msg = f"❌ Failed to retrieve memory: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return error_msg


async def get_relevant_memories(
    project_dir: str, query: str, event_type: str, limit: int, ctx: Context
) -> Dict[str, Any]:
    """
    Get relevant memories using RAG (Retrieval-Augmented Generation).

    Args:
        project_dir: Absolute path to the project directory
        query: Search query for semantic similarity
        event_type: Filter by event type or "all"
        limit: Maximum number of entries to return
        ctx: FastMCP Context for logging

    Returns:
        Dictionary containing relevant memory entries with scores
    """
    try:
        mcp_server_dir = Path(__file__).parent.absolute()
        memory_base_dir = mcp_server_dir / "memory"

        if not memory_base_dir.exists():
            return {"error": "Memory database not found"}

        # Generate project hash (normalize to lowercase for consistency)
        normalized_project_dir = project_dir.replace("\\", "/").lower()
        project_hash = hashlib.md5(normalized_project_dir.encode()).hexdigest()[:8]
        project_memory_dir = memory_base_dir / f"project_{project_hash}"

        if not project_memory_dir.exists():
            return {"error": f"No memory found for project {Path(project_dir).name}"}

        # Read index data
        index_file = memory_base_dir / "index.json"
        index_data = {}
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
            except Exception:
                pass

        project_info = index_data.get(project_hash, {})

        # Collect all memory entries
        all_entries = []
        event_types_to_search = (
            ["milestone", "bug_solved", "user_preference"]
            if event_type == "all"
            else [event_type]
        )

        for et in event_types_to_search:
            memory_file = project_memory_dir / f"{et}s.json"
            if memory_file.exists():
                try:
                    with open(memory_file, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                        all_entries.extend(entries)
                except Exception as e:
                    logger.warning(f"Failed to load {memory_file}: {e}")

        if not all_entries:
            return {
                "project_hash": project_hash,
                "project_path": project_dir,
                "project_name": Path(project_dir).name,
                "last_updated": project_info.get("last_updated", "Unknown"),
                "event_counts": project_info.get("event_counts", {}),
                "relevant_entries": [],
            }

        # Perform RAG search if query is provided
        if query.strip():
            await ctx.info("Performing semantic search...")
            relevant_entries = await perform_semantic_search(
                all_entries, query, limit, ctx
            )
        else:
            # No query - return most recent entries
            await ctx.info("No query provided, returning recent entries...")
            # Sort by timestamp (most recent first)
            sorted_entries = sorted(
                all_entries, key=lambda x: x.get("timestamp", ""), reverse=True
            )
            relevant_entries = sorted_entries[:limit]
            # Add dummy relevance scores
            for entry in relevant_entries:
                entry["relevance_score"] = 1.0

        return {
            "project_hash": project_hash,
            "project_path": project_dir,
            "project_name": Path(project_dir).name,
            "last_updated": project_info.get("last_updated", "Unknown"),
            "event_counts": project_info.get("event_counts", {}),
            "relevant_entries": relevant_entries,
        }

    except Exception as e:
        return {"error": f"Failed to retrieve relevant memories: {str(e)}"}


async def perform_semantic_search(
    entries: List[Dict], query: str, limit: int, ctx: Context
) -> List[Dict]:
    """
    Perform semantic search on memory entries using embeddings.

    Args:
        entries: List of memory entries with embeddings
        query: Search query
        limit: Maximum number of results
        ctx: FastMCP Context for logging

    Returns:
        List of relevant entries with relevance scores
    """
    try:
        # Generate query embedding using configured provider
        if EMBEDDING_PROVIDER == "openai" and not OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured for semantic search")
        elif EMBEDDING_PROVIDER == "gemini" and not GEMINI_API_KEY:
            raise ValueError("Gemini API key not configured for semantic search")

        query_embedding = await get_embedding_with_cache(query)

        # Calculate similarities
        scored_entries = []
        entries_with_embeddings = 0

        for entry in entries:
            if entry.get("embedding"):
                try:
                    entry_embedding = entry["embedding"]
                    similarity = cosine_similarity(query_embedding, entry_embedding)

                    # Create a copy of the entry with relevance score
                    scored_entry = entry.copy()
                    scored_entry["relevance_score"] = float(similarity)
                    scored_entries.append(scored_entry)
                    entries_with_embeddings += 1

                except Exception as e:
                    logger.warning(
                        f"Failed to calculate similarity for entry {entry.get('id', 'unknown')}: {e}"
                    )
            else:
                # Fallback to text search for entries without embeddings
                description = entry.get("description", "").lower()
                query_lower = query.lower()

                # Simple text matching score
                if query_lower in description:
                    words_match = sum(
                        1 for word in query_lower.split() if word in description
                    )
                    total_words = len(query_lower.split())
                    text_score = words_match / total_words if total_words > 0 else 0

                    scored_entry = entry.copy()
                    scored_entry["relevance_score"] = (
                        text_score * 0.5
                    )  # Lower score for text matching
                    scored_entries.append(scored_entry)

        await ctx.info(
            f"Processed {entries_with_embeddings} entries with embeddings, {len(scored_entries)} total matches"
        )

        # Sort by relevance score (highest first)
        scored_entries.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        # Return top results
        return scored_entries[:limit]

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        await ctx.error(f"Semantic search failed: {e}")
        # Don't fallback - raise error so user knows API key is required
        raise


def get_project_memory(project_dir: str) -> Dict[str, Any]:
    """
    Helper function to retrieve memory data for a specific project.
    Used internally by ask_to_leader_project to provide context.

    Args:
        project_dir: Absolute path to the project directory

    Returns:
        Dictionary containing project memory data
    """
    try:
        mcp_server_dir = Path(__file__).parent.absolute()
        memory_base_dir = mcp_server_dir / "memory"

        if not memory_base_dir.exists():
            return {"error": "Memory database not found"}

        # Generate project hash (normalize to lowercase for consistency)
        normalized_project_dir = project_dir.replace("\\", "/").lower()
        project_hash = hashlib.md5(normalized_project_dir.encode()).hexdigest()[:8]
        project_memory_dir = memory_base_dir / f"project_{project_hash}"

        if not project_memory_dir.exists():
            return {"error": f"No memory found for project {Path(project_dir).name}"}

        # Read index data
        index_file = memory_base_dir / "index.json"
        index_data = {}
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
            except Exception:
                pass

        project_info = index_data.get(project_hash, {})

        # Read memory files
        memory_data = {
            "project_hash": project_hash,
            "project_path": project_dir,
            "project_name": Path(project_dir).name,
            "last_updated": project_info.get("last_updated", "Unknown"),
            "event_counts": project_info.get("event_counts", {}),
            "memories": {},
        }

        # Read each category file (now JSON format)
        for event_type in ["milestone", "bug_solved", "user_preference"]:
            memory_file = project_memory_dir / f"{event_type}s.json"
            if memory_file.exists():
                try:
                    with open(memory_file, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                        if entries:
                            # Get last 5 entries for context, format for display
                            recent_entries = (
                                entries[-5:] if len(entries) > 5 else entries
                            )
                            formatted_entries = []
                            for entry in recent_entries:
                                timestamp = entry.get("timestamp", "Unknown")
                                try:
                                    dt = datetime.fromisoformat(
                                        timestamp.replace("Z", "+00:00")
                                    )
                                    formatted_time = dt.strftime("%Y-%m-%d %H:%M")
                                except:
                                    formatted_time = timestamp

                                title = entry.get("title", "")
                                description = entry.get("description", "")
                                formatted_entry = (
                                    f"[{formatted_time}] {title}: {description}"
                                )
                                formatted_entries.append(formatted_entry)

                            memory_data["memories"][event_type] = formatted_entries
                        else:
                            memory_data["memories"][event_type] = []
                except Exception as e:
                    logger.warning(f"Failed to load {memory_file}: {e}")
                    memory_data["memories"][event_type] = []
            else:
                # Check for legacy .txt files and migrate them
                legacy_file = project_memory_dir / f"{event_type}s.txt"
                if legacy_file.exists():
                    try:
                        with open(legacy_file, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            if content:
                                lines = content.split("\n")
                                memory_data["memories"][event_type] = (
                                    lines[-5:] if len(lines) > 5 else lines
                                )
                            else:
                                memory_data["memories"][event_type] = []
                    except Exception:
                        memory_data["memories"][event_type] = []
                else:
                    memory_data["memories"][event_type] = []

        return memory_data

    except Exception as e:
        return {"error": f"Failed to retrieve project memory: {str(e)}"}


# New ask_to_leader_project tool with robust error handling
@mcp.tool()
async def ask_to_leader_project(
    agent_comment: str, ctx: Context, project_dir: str = None
) -> str:
    """
    Tool for the AI agent to consult the project leader when finishing work.
    Shows a graphical interface to receive feedback and allows AI improvement.

    Args:
        agent_comment: Agent's comment about the completed work
        ctx: FastMCP Context for logging
        project_dir: Project path (REQUIRED on first call, then cached for session)

    Returns:
        Project leader's response
    """
    global _cached_project_dir

    try:
        logger.info("=" * 80)
        logger.info("STARTING ask_to_leader_project")
        logger.info(f"Agent comment length: {len(agent_comment)} characters")
        logger.info(f"Agent comment preview: {agent_comment[:100]}...")
        logger.info(f"Project dir parameter: {project_dir}")
        logger.info(f"Cached project dir: {_cached_project_dir}")
        logger.info(f"Context object provided: {ctx is not None}")

        await ctx.info("Starting consultation with the project leader...")
        logger.debug("Context.info call successful")

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
            await ctx.error(
                "❌ AI agent must pass workspace path on first call to ask_to_leader_project"
            )
            return "❌ Error: No project directory provided. AI agent must pass workspace path."

        # Check if auto-stop is enabled
        auto_stop_enabled = os.getenv("APP_AUTO_STOP", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        if auto_stop_enabled:
            logger.info("Auto-stop enabled - bypassing UI and focusing cursor")
            await ctx.info("Auto-stop mode: Focusing cursor and stopping execution...")

            # Focus cursor and send stop hotkey
            try:
                if HAS_FOCUS_CURSOR:
                    success = focus_cursor_and_send_hotkey()
                    if success:
                        logger.info(
                            "Successfully focused cursor and sent stop hotkey in auto-stop mode"
                        )
                        await ctx.info(
                            "✅ Auto-stop: Successfully focused cursor and sent stop signal"
                        )
                        return "🛑 Auto-stop mode: Focused cursor and sent stop signal. Task completed."
                    else:
                        logger.warning("Failed to focus cursor in auto-stop mode")
                        await ctx.warning(
                            "⚠️ Auto-stop: Failed to focus cursor - continuing without stop signal"
                        )
                        return "⚠️ Auto-stop mode: Failed to focus cursor. Task completed without stop signal."
                else:
                    logger.warning(
                        "Focus cursor functionality not available in auto-stop mode"
                    )
                    await ctx.warning(
                        "⚠️ Auto-stop: Focus cursor functionality not available"
                    )
                    return "⚠️ Auto-stop mode: Focus cursor functionality not available. Task completed."
            except Exception as e:
                logger.error(f"Error in auto-stop mode: {e}")
                await ctx.error(f"Error in auto-stop mode: {e}")
                return f"❌ Auto-stop mode error: {e}. Task completed."

        # Show the feedback interface for leader consultation (non-blocking)

        # CRITICAL FIX: Use subprocess instead of asyncio.to_thread()
        # Qt/PyQt6 requires GUI to run on main thread or in separate process
        # asyncio.to_thread() runs in worker thread which causes random Qt crashes
        try:
            logger.info("Launching UI in subprocess (Qt threading requirement)...")
            logger.debug(f"Current thread: {threading.current_thread().name}")
            logger.debug(
                f"Parameters: agent_comment_length={len(agent_comment)}, project_dir={project_base_dir}"
            )

            # Run UI in subprocess to avoid Qt threading issues
            import subprocess
            import tempfile

            # Get path to invoke_ui.py
            script_dir = Path(__file__).parent.absolute()
            invoke_ui_script = script_dir / "invoke_ui.py"

            if not invoke_ui_script.exists():
                error_msg = f"invoke_ui.py not found at {invoke_ui_script}"
                logger.error(error_msg)
                await ctx.error(f"❌ {error_msg}")
                return f"❌ {error_msg}"

            logger.debug(f"invoke_ui.py path: {invoke_ui_script}")
            logger.debug(f"Python executable: {sys.executable}")

            subprocess_env = os.environ.copy()
            if platform.system() == "Linux":
                xauthority_path = Path.home() / ".Xauthority"
                if not subprocess_env.get("XAUTHORITY") and xauthority_path.exists():
                    subprocess_env["XAUTHORITY"] = str(xauthority_path)
                    logger.debug(
                        f"XAUTHORITY was missing; defaulting to {xauthority_path}"
                    )
                runtime_dir = Path(f"/run/user/{os.getuid()}")
                if not subprocess_env.get("XDG_RUNTIME_DIR") and runtime_dir.exists():
                    subprocess_env["XDG_RUNTIME_DIR"] = str(runtime_dir)
                    logger.debug(
                        f"XDG_RUNTIME_DIR was missing; defaulting to {runtime_dir}"
                    )
                if (
                    not subprocess_env.get("DBUS_SESSION_BUS_ADDRESS")
                    and runtime_dir.exists()
                ):
                    bus_path = runtime_dir / "bus"
                    if bus_path.exists():
                        subprocess_env["DBUS_SESSION_BUS_ADDRESS"] = (
                            f"unix:path={bus_path}"
                        )
                        logger.debug(
                            f"DBUS_SESSION_BUS_ADDRESS was missing; defaulting to unix:path={bus_path}"
                        )
                if subprocess_env.get("WAYLAND_DISPLAY"):
                    subprocess_env.setdefault("QT_QPA_PLATFORM", "wayland")
                    logger.debug(
                        "Detected Wayland session; preferring QT_QPA_PLATFORM=wayland"
                    )
                elif subprocess_env.get("DISPLAY"):
                    logger.debug(
                        f"Detected X11 session; using DISPLAY={subprocess_env.get('DISPLAY')}"
                    )
                else:
                    x11_socket = Path("/tmp/.X11-unix/X0")
                    wayland_socket = Path(f"/run/user/{os.getuid()}/wayland-0")
                    if x11_socket.exists():
                        subprocess_env.setdefault("DISPLAY", ":0")
                        logger.debug(
                            "DISPLAY was missing; defaulting to DISPLAY=:0 because /tmp/.X11-unix/X0 exists"
                        )
                    if wayland_socket.exists():
                        subprocess_env.setdefault("WAYLAND_DISPLAY", "wayland-0")
                        subprocess_env.setdefault("QT_QPA_PLATFORM", "wayland")
                        logger.debug(
                            f"WAYLAND_DISPLAY was missing; defaulting to WAYLAND_DISPLAY=wayland-0 because {wayland_socket} exists"
                        )
                    if not subprocess_env.get("DISPLAY") and not subprocess_env.get(
                        "WAYLAND_DISPLAY"
                    ):
                        logger.debug(
                            "No DISPLAY or WAYLAND_DISPLAY detected; still attempting Qt launcher and will fall back only on real launch failure"
                        )

            # Write agent_comment to temp file to avoid command line length limits
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".md", delete=False
            ) as tmp:
                tmp.write(agent_comment)
                tmp_path = tmp.name

            logger.debug(f"Wrote agent comment to temp file: {tmp_path}")

            try:
                # Run subprocess with temp file
                await ctx.info("Opening feedback dialog...")
                logger.info("Starting subprocess...")

                # Run in subprocess - blocks until UI closes
                result = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(invoke_ui_script),
                    str(project_base_dir),
                    "-",  # Read from stdin
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=subprocess_env,
                )

                # Send agent_comment via stdin
                logger.debug("Sending agent comment via stdin...")
                stdout, stderr = await result.communicate(
                    input=agent_comment.encode("utf-8")
                )

                logger.info(
                    f"Subprocess completed with return code: {result.returncode}"
                )

                if result.returncode != 0:
                    error_output = stderr.decode("utf-8", errors="replace")
                    logger.error(f"UI subprocess failed: {error_output}")
                    await ctx.error(f"❌ UI error: {error_output[:200]}")
                    return f"❌ UI subprocess failed: {error_output[:200]}"

                # Parse response from stdout
                stdout_text = stdout.decode("utf-8", errors="replace")
                logger.debug(f"Subprocess stdout length: {len(stdout_text)}")

                # Extract response between markers
                if (
                    "===UI_RESPONSE_START===" in stdout_text
                    and "===UI_RESPONSE_END===" in stdout_text
                ):
                    start_marker = "===UI_RESPONSE_START==="
                    end_marker = "===UI_RESPONSE_END==="
                    start_idx = stdout_text.index(start_marker) + len(start_marker)
                    end_idx = stdout_text.index(end_marker)
                    response = stdout_text[start_idx:end_idx].strip()
                    logger.debug(f"Extracted response length: {len(response)}")
                else:
                    logger.warning("Response markers not found in subprocess output")
                    response = ""

                if stderr:
                    stderr_text = stderr.decode("utf-8", errors="replace")
                    if stderr_text.strip():
                        logger.warning(f"Subprocess stderr: {stderr_text[:500]}")

            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                    logger.debug(f"Deleted temp file: {tmp_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to delete temp file: {cleanup_error}")

            logger.debug(f"Response is None: {response is None}")
            logger.debug(f"Response is empty string: {response == ''}")

            if not response:
                logger.warning("No response from leader (empty or None)")
                await ctx.info("No response from leader - continuing without feedback")
                return "⚠️ Could not get a response from the project leader. Continuing without feedback."

            logger.info(f"Response obtained: {response[:100]}...")
            logger.debug(f"Full response length: {len(response)}")

        except Exception as e:
            logger.error(
                f"Unexpected exception launching UI subprocess: {e}", exc_info=True
            )
            logger.debug(f"Exception type: {type(e).__name__}")
            logger.debug(f"Exception args: {e.args}")
            await ctx.error(f"Error showing interface: {e}")
            return f"❌ Error showing interface: {e}. Continuing without feedback."

        # NOTE: Auto-save to memory has been REMOVED (architectural issue)
        # REASON: MCP tools should NOT call other MCP tools internally
        # - Creates tight coupling between tools
        # - Violates separation of concerns
        # - MCP architecture: tools are called by LLM/client, not by each other
        # - The protocol already requires LLM to call memory_save separately
        # PROPER FLOW: LLM calls memory_save → then calls ask_to_leader_project
        # If auto-save is needed, it should be handled at the LLM/orchestration layer, not within tools

        logger.info(f"Final response returned: {response[:200]}...")
        logger.info("=" * 80)

        # Determine instruction message - provide structured format template
        if "?" in response:
            # Leader asked a question - provide simple answer format
            instruction_line = """Complete this turn's transaction by calling mcp:senior-tools:ask_to_leader_project with:

Answer: [Your direct response to the leader's question]

Note: Keep your answer concise and focused on addressing the specific question asked."""
        else:
            # Leader provided feedback or acknowledgment - provide comprehensive report format
            instruction_line = """Complete this turn's transaction by calling mcp:senior-tools:ask_to_leader_project with a comprehensive report using this structure:

## Summary
[One-line description of what was accomplished]

## Changes Made
[List each modified file with specific changes. Always show actual code, never just line numbers]
- **relative/path/to/file.ext**: [Brief description of what changed]
  - OLD: `actual old code snippet here`
  - NEW: `actual new code snippet here`
  - Context: [Why this change was needed]

## Technical Details
[Explain implementation decisions and technical approaches]
- [Key architectural or design decisions made]
- [Libraries, patterns, or algorithms used]
- [Performance or security considerations]
- [Trade-offs evaluated]

## Results
[Describe measurable outcomes and what now works]
- [Specific functionality that works now]
- [Problems that are fixed]
- [Improvements or metrics]
- [Validation/testing performed]

## What to Do Next / Things to Consider
[Proactive guidance for future work]
- [Immediate follow-up actions needed]
- [Potential side effects or risks to watch]
- [Future improvements or optimizations to consider]
- [Related areas that might need updates]

IMPORTANT GUIDELINES:
✅ Use relative file paths from project root (e.g., src/utils/helper.py)
✅ Show actual code snippets, not "changed lines X-Y"
✅ Include OLD vs NEW code for clarity
✅ Be specific about what changed and why
✅ Provide actionable next steps
✅ Mention any side effects or risks
❌ Don't use absolute paths
❌ Don't reference line numbers without showing code
❌ Don't be vague ("updated file X")
❌ Don't skip sections - use all 5 sections"""

        return f"Leader's response: {response}\n\n{instruction_line}"

    except Exception as e:
        await ctx.error(f"Error in ask_to_leader_project: {e}")
        return f"Error consulting project leader: {e}. Continuing without feedback."


@mcp.tool()
async def init_agent_files(
    target_directory: str, config_folder: str, ctx: Context
) -> str:
    """
    Initialize agent configuration files in a dynamic folder structure.
    Creates configuration files in the specified folder (e.g., .cursor, .augment, etc.)

    Args:
        target_directory: The directory where you want to create the configuration files
        config_folder: The configuration folder name (e.g., ".cursor", ".augment", "config")
        ctx: FastMCP Context for logging

    Returns:
        Status message about the file creation
    """
    try:
        logger.info(f"Agent files initialization requested for: {target_directory}")
        logger.info(f"Configuration folder: {config_folder}")
        await ctx.info(
            f"Setting up agent configuration files in: {target_directory}/{config_folder}"
        )

        # Determine the target directory
        base_dir = Path(target_directory)
        logger.info(f"Using target directory: {base_dir}")

        # Define the configuration directory structure based on folder type
        config_dir = base_dir / config_folder

        # Create appropriate subdirectories based on config folder type
        if config_folder in [".cursor", "cursor"]:
            commands_dir = config_dir / "commands"
            rules_dir = config_dir / "rules"
            commands_dir.mkdir(parents=True, exist_ok=True)
            rules_dir.mkdir(parents=True, exist_ok=True)

            # Create Cursor-specific files
            command_file = commands_dir / ".always_call_leader.md"
            rules_file = rules_dir / "always_call_leader.mdc"

        elif config_folder in [".augment", "augment"]:
            rules_dir = config_dir / "rules"
            rules_dir.mkdir(parents=True, exist_ok=True)

            # Create Augment-specific files (only rules file)
            rules_file = rules_dir / "always_call_leader.md"
            command_file = None  # No command file for Augment

        else:
            # Generic configuration folder
            config_dir.mkdir(parents=True, exist_ok=True)
            command_file = config_dir / "always_call_leader.md"
            rules_file = config_dir / "agent_rules.md"

        logger.info(f"Created configuration directory structure in: {config_dir}")

        # Define command content
        command_content = "Complete this turn's transaction by calling mcp:senior-tools:ask_to_leader_project with: '[What you did]: [Result]. [Any risks/follow-ups]'"

        # Load content from agent_rules.md
        try:
            rules_path = Path(__file__).parent / "config" / "agent_rules.md"
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_content = f.read()

            if not rules_content:
                logger.error("❌ Could not load rules content from agent_rules.md")
                return "❌ Failed to load rules content from agent_rules.md"

            logger.info("✅ Successfully loaded content from config/agent_rules.md")

        except Exception as e:
            logger.error(f"❌ Error loading content from agent_rules.md: {e}")
            return f"❌ Error loading rules: {e}"

        # Create/update files
        files_created = []
        files_updated = []

        # Command file (only if defined)
        if command_file is not None:
            try:
                if not command_file.exists():
                    with open(command_file, "w", encoding="utf-8") as f:
                        f.write(command_content)
                        f.flush()
                        os.fsync(f.fileno())  # Ensure data is written to disk
                    files_created.append(str(command_file.relative_to(base_dir)))
                    logger.info(f"Created command file: {command_file}")
                else:
                    with open(command_file, "r", encoding="utf-8") as f:
                        existing_content = f.read()
                    # Compare without stripping to preserve exact content
                    if existing_content != command_content:
                        with open(command_file, "w", encoding="utf-8") as f:
                            f.write(command_content)
                            f.flush()
                            os.fsync(f.fileno())
                        files_updated.append(str(command_file.relative_to(base_dir)))
                        logger.info(f"Updated command file: {command_file}")
            except IOError as e:
                error_msg = f"Failed to write command file {command_file}: {e}"
                logger.error(error_msg)
                raise IOError(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error with command file {command_file}: {e}"
                logger.error(error_msg)
                raise

        # Rules file (always created)
        try:
            if not rules_file.exists():
                with open(rules_file, "w", encoding="utf-8") as f:
                    f.write(rules_content)
                    f.flush()
                    os.fsync(f.fileno())  # Ensure data is written to disk
                files_created.append(str(rules_file.relative_to(base_dir)))
                logger.info(f"Created new rules file: {rules_file}")
            else:
                with open(rules_file, "r", encoding="utf-8") as f:
                    existing_content = f.read()

                # Debug logging
                logger.info(f"Checking existing rules file: {rules_file}")
                logger.info(f"Existing content length: {len(existing_content)} chars")
                logger.info(f"New content length: {len(rules_content)} chars")

                # Compare without stripping to preserve exact content
                if existing_content != rules_content:
                    logger.info(f"Content differs - updating rules file")
                    with open(rules_file, "w", encoding="utf-8") as f:
                        f.write(rules_content)
                        f.flush()
                        os.fsync(f.fileno())
                    files_updated.append(str(rules_file.relative_to(base_dir)))
                else:
                    logger.info(f"Content matches - no update needed")
        except IOError as e:
            error_msg = f"Failed to write rules file {rules_file}: {e}"
            logger.error(error_msg)
            raise IOError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error with rules file {rules_file}: {e}"
            logger.error(error_msg)
            raise

        # Generate result message
        result_parts = []
        if files_created:
            result_parts.append(f"Created: {', '.join(files_created)}")
        if files_updated:
            result_parts.append(f"Updated: {', '.join(files_updated)}")

        if result_parts:
            message = (
                f"✅ Agent files initialized successfully in {config_folder}/\n"
                + "\n".join(result_parts)
            )
        else:
            message = f"✅ All agent files already exist with correct content in {config_folder}/"

        logger.info(message)
        await ctx.info(message)
        return message

    except Exception as e:
        error_msg = f"Error initializing agent files: {e}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


@mcp.tool()
async def get_embedding_cache_stats(ctx: Context) -> str:
    """
    Get detailed embedding cache statistics (L3 fix - exposed as MCP tool)

    Returns:
        Formatted string with cache statistics including:
        - hits/misses and hit rate
        - total cached entries
        - evictions and expirations
        - cache file size
        - estimated API calls and cost savings
    """
    try:
        stats = get_cache_statistics_internal()

        if "error" in stats:
            error_msg = f"Failed to get cache statistics: {stats['error']}"
            await ctx.error(error_msg)
            return f"❌ {error_msg}"

        # Format as readable string
        result = f"""
📊 Embedding Cache Statistics

**Performance:**
- Cache Hits: {stats['hits']}
- Cache Misses: {stats['misses']}
- Hit Rate: {stats['hit_rate']}%
- API Calls Saved: {stats['estimated_api_calls_saved']}

**Storage:**
- Total Entries: {stats['total_entries']} / {stats['max_entries']}
- Cache Size: {stats['size_mb']} MB
- Evictions: {stats['evictions']}
- Expirations: {stats['expirations']}

**Configuration:**
- Provider: {stats['provider']}
- TTL: {stats['ttl_days']} days
- Enabled: {stats['enabled']}
- Cost Savings: ${stats['estimated_cost_savings_usd']} USD
"""

        await ctx.info("Cache statistics retrieved successfully")
        return result.strip()

    except Exception as e:
        error_msg = f"Failed to get cache statistics: {e}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


def show_feedback_interface(
    agent_comment: str, ctx: Context = None, project_dir: str = None
) -> str:
    """Show Qt6 graphical interface for leader feedback

    DEPRECATED FUNCTION: This function is no longer used in the current subprocess
    architecture. It was part of the old asyncio.to_thread() implementation that
    caused Qt threading crashes. The new implementation uses subprocess execution
    via invoke_ui.py script for thread-safe Qt operations.

    NOTE: Context (ctx) parameter is NOT thread-safe and should not be used in
    threaded environments. The subprocess approach avoids this issue entirely.
    """

    logger.info("=" * 80)
    logger.info("ENTERING show_feedback_interface")
    logger.info(f"Agent comment length: {len(agent_comment)}")
    logger.info(
        f"Context provided: {ctx is not None} (should be None for thread safety)"
    )
    logger.info(f"Project dir: {project_dir}")
    logger.info(f"Current thread: {threading.current_thread().name}")
    logger.info(f"Thread ID: {threading.get_ident()}")

    try:
        # Play notification sound when invoked from MCP
        # NOTE: This function is deprecated and should not be used in the current
        # subprocess architecture. Use invoke_ui.py subprocess instead.
        logger.debug("Starting notification sound thread...")
        play_notification_sound_threaded()
        logger.info("Notification sound thread started for feedback interface")

        logger.info("Using Qt6 interface with glass morphism")
        logger.debug(
            f"Calling create_modern_feedback_dialog with project_dir: {project_dir}"
        )
        response = create_modern_feedback_dialog(agent_comment, project_dir)
        logger.debug(
            f"create_modern_feedback_dialog returned, response length: {len(response) if response else 0}"
        )

        if response:
            logger.info(f"Response obtained: {response[:100]}...")
            return response
        else:
            logger.warning("User cancelled or provided no response")
            return ""

    except Exception as e:
        logger.error(f"Error in Qt6 interface: {e}")
        raise Exception(f"Qt6 interface failed: {e}. Please ensure PyQt6 is installed.")


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("INICIANDO SERVIDOR MCP - senior_tools")
    logger.info("=" * 80)
    logger.info(f"Process ID: {os.getpid()}")
    logger.info(f"Current directory: {os.getcwd()}")
    logger.info(f"Script location: {__file__}")
    logger.info("Ejecutando mcp.run()...")
    logger.info("MCP server will now start and listen for requests...")
    logger.info("=" * 80)

    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("=" * 80)
        logger.info("MCP server interrupted by user (Ctrl+C)")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"MCP server crashed with exception: {e}", exc_info=True)
        logger.error("=" * 80)
        raise
    finally:
        logger.info("=" * 80)
        logger.info("Servidor MCP finalizado")
        logger.info("=" * 80)
