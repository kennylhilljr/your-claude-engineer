"""MetricsStore - JSON persistence layer for Agent Status Dashboard.

This module provides the MetricsStore class which handles:
- Loading/saving DashboardState to/from .agent_metrics.json
- Atomic writes using write-then-rename pattern (write to temp file, then rename)
- FIFO eviction: keep last 500 events, last 50 sessions
- Corruption recovery: if JSON is invalid, restore from .bak file or create fresh state
- Thread-safe operations using file-based locking

The MetricsStore integrates with the TypedDict types from metrics.py and provides
a reliable persistence layer for the dashboard's metrics data.
"""

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from metrics import DashboardState


class MetricsStore:
    """Thread-safe JSON persistence layer for dashboard metrics.

    Manages loading, saving, and maintaining the .agent_metrics.json file with:
    - Atomic writes to prevent data corruption during writes
    - FIFO eviction to cap storage at 500 events and 50 sessions
    - Automatic backup and recovery from corrupted JSON files
    - Thread-safe operations via lock file mechanism

    Usage:
        store = MetricsStore(project_name="my-project")
        state = store.load()
        state["total_sessions"] += 1
        store.save(state)
    """

    # FIFO limits
    MAX_EVENTS = 500
    MAX_SESSIONS = 50

    # File paths
    METRICS_FILE = ".agent_metrics.json"
    BACKUP_FILE = ".agent_metrics.json.bak"
    LOCK_FILE = ".agent_metrics.lock"

    def __init__(self, project_name: str, metrics_dir: Optional[Path] = None):
        """Initialize MetricsStore.

        Args:
            project_name: Name of the project for the dashboard
            metrics_dir: Directory to store metrics files (default: current directory)
        """
        self.project_name = project_name
        self.metrics_dir = Path(metrics_dir) if metrics_dir else Path.cwd()
        self.metrics_path = self.metrics_dir / self.METRICS_FILE
        self.backup_path = self.metrics_dir / self.BACKUP_FILE
        self.lock_path = self.metrics_dir / self.LOCK_FILE

        # Thread lock for in-process synchronization
        self._thread_lock = threading.Lock()

    def _acquire_lock(self) -> None:
        """Acquire file lock for cross-process synchronization.

        Creates a lock file to prevent concurrent writes from multiple processes.
        Uses a simple lock file mechanism - in production, consider using fcntl or similar.
        """
        # Wait for lock to be available (simple spin-lock)
        max_attempts = 100
        attempt = 0
        while self.lock_path.exists() and attempt < max_attempts:
            import time
            time.sleep(0.01)  # 10ms
            attempt += 1

        if attempt >= max_attempts:
            # Force remove stale lock
            self.lock_path.unlink(missing_ok=True)

        # Create lock file
        self.lock_path.touch()

    def _release_lock(self) -> None:
        """Release file lock."""
        self.lock_path.unlink(missing_ok=True)

    def _create_empty_state(self) -> DashboardState:
        """Create a fresh empty DashboardState.

        Returns:
            A new DashboardState with initialized fields and zero counters
        """
        now = datetime.utcnow().isoformat() + "Z"

        return {
            "version": 1,
            "project_name": self.project_name,
            "created_at": now,
            "updated_at": now,
            "total_sessions": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_duration_seconds": 0.0,
            "agents": {},
            "events": [],
            "sessions": [],
        }

    def _apply_fifo_eviction(self, state: DashboardState) -> DashboardState:
        """Apply FIFO eviction to keep storage bounded.

        Keeps only the last MAX_EVENTS events and MAX_SESSIONS sessions.
        Older entries are removed in FIFO order.

        Args:
            state: DashboardState to apply eviction to

        Returns:
            Modified state with eviction applied
        """
        # Evict old events (keep last MAX_EVENTS)
        if len(state["events"]) > self.MAX_EVENTS:
            state["events"] = state["events"][-self.MAX_EVENTS:]

        # Evict old sessions (keep last MAX_SESSIONS)
        if len(state["sessions"]) > self.MAX_SESSIONS:
            state["sessions"] = state["sessions"][-self.MAX_SESSIONS:]

        return state

    def _validate_state(self, data: dict) -> bool:
        """Validate that loaded data has required DashboardState structure.

        Args:
            data: Dictionary loaded from JSON file

        Returns:
            True if data has all required fields, False otherwise
        """
        required_fields = [
            "version", "project_name", "created_at", "updated_at",
            "total_sessions", "total_tokens", "total_cost_usd", "total_duration_seconds",
            "agents", "events", "sessions"
        ]

        for field in required_fields:
            if field not in data:
                return False

        # Type checks for critical fields
        if not isinstance(data["agents"], dict):
            return False
        if not isinstance(data["events"], list):
            return False
        if not isinstance(data["sessions"], list):
            return False

        return True

    def load(self) -> DashboardState:
        """Load DashboardState from disk with corruption recovery.

        Attempts to load from .agent_metrics.json. If the file is corrupted:
        1. Try to restore from .agent_metrics.json.bak
        2. If backup is also corrupted, create a fresh empty state

        Returns:
            DashboardState loaded from disk or freshly created
        """
        with self._thread_lock:
            self._acquire_lock()
            try:
                # Try to load main file
                if self.metrics_path.exists():
                    try:
                        with open(self.metrics_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        # Validate structure
                        if self._validate_state(data):
                            return data  # type: ignore
                        else:
                            # Structure invalid, try backup
                            raise ValueError("Invalid state structure")

                    except (json.JSONDecodeError, ValueError) as e:
                        # Main file is corrupted, try backup
                        if self.backup_path.exists():
                            try:
                                with open(self.backup_path, 'r', encoding='utf-8') as f:
                                    data = json.load(f)

                                if self._validate_state(data):
                                    # Successfully recovered from backup
                                    # Save it back to main file
                                    with open(self.metrics_path, 'w', encoding='utf-8') as f:
                                        json.dump(data, f, indent=2)
                                    return data  # type: ignore
                            except (json.JSONDecodeError, ValueError):
                                pass  # Backup also corrupted

                        # Both files corrupted or backup doesn't exist
                        # Create fresh state
                        pass

                # No file exists or all recovery attempts failed - create fresh state
                return self._create_empty_state()

            finally:
                self._release_lock()

    def save(self, state: DashboardState) -> None:
        """Save DashboardState to disk with atomic write.

        Uses write-then-rename pattern to ensure atomicity:
        1. Apply FIFO eviction to keep storage bounded
        2. Write to temporary file
        3. Create backup of existing file
        4. Atomically rename temp file to main file

        This ensures that the main file is never in a partially-written state.

        Args:
            state: DashboardState to save
        """
        with self._thread_lock:
            self._acquire_lock()
            try:
                # Update timestamp
                state["updated_at"] = datetime.utcnow().isoformat() + "Z"

                # Apply FIFO eviction
                state = self._apply_fifo_eviction(state)

                # Write to temporary file first (atomic write pattern)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.metrics_dir,
                    prefix='.agent_metrics_',
                    suffix='.tmp'
                )

                try:
                    # Write JSON to temp file
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        json.dump(state, f, indent=2, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())  # Ensure data is written to disk

                    # Create backup of existing file before overwriting
                    if self.metrics_path.exists():
                        # Copy existing file to backup
                        with open(self.metrics_path, 'r', encoding='utf-8') as src:
                            backup_data = src.read()
                        with open(self.backup_path, 'w', encoding='utf-8') as dst:
                            dst.write(backup_data)

                    # Atomically rename temp file to main file
                    # On POSIX systems, rename is atomic
                    os.replace(temp_path, self.metrics_path)

                except Exception as e:
                    # Clean up temp file on error
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise e

            finally:
                self._release_lock()

    def get_stats(self) -> dict:
        """Get storage statistics.

        Returns:
            Dictionary with file sizes, event count, session count, etc.
        """
        stats = {
            "metrics_file_exists": self.metrics_path.exists(),
            "backup_file_exists": self.backup_path.exists(),
            "metrics_file_size_bytes": 0,
            "backup_file_size_bytes": 0,
            "event_count": 0,
            "session_count": 0,
            "agent_count": 0,
        }

        if self.metrics_path.exists():
            stats["metrics_file_size_bytes"] = self.metrics_path.stat().st_size

        if self.backup_path.exists():
            stats["backup_file_size_bytes"] = self.backup_path.stat().st_size

        # Load state to get counts
        try:
            state = self.load()
            stats["event_count"] = len(state["events"])
            stats["session_count"] = len(state["sessions"])
            stats["agent_count"] = len(state["agents"])
        except Exception:
            pass

        return stats
