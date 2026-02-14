"""Unit and integration tests for MetricsStore.

Tests verify:
1. Basic write/read operations
2. Atomic write behavior (verify temp file, rename)
3. FIFO eviction when limits exceeded
4. Corruption recovery scenarios
5. Edge cases (empty state, missing file, etc.)
6. Thread-safety (basic verification)
"""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from metrics import AgentEvent, AgentProfile, DashboardState, SessionSummary
from metrics_store import MetricsStore


class TestMetricsStoreBasics(unittest.TestCase):
    """Test basic MetricsStore operations."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = MetricsStore(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_empty_state(self):
        """Test loading when no file exists creates empty state."""
        state = self.store.load()

        # Verify structure
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["project_name"], "test-project")
        self.assertEqual(state["total_sessions"], 0)
        self.assertEqual(state["total_tokens"], 0)
        self.assertEqual(state["total_cost_usd"], 0.0)
        self.assertEqual(len(state["agents"]), 0)
        self.assertEqual(len(state["events"]), 0)
        self.assertEqual(len(state["sessions"]), 0)

        # Verify timestamps are present
        self.assertIn("created_at", state)
        self.assertIn("updated_at", state)
        self.assertTrue(state["created_at"].endswith("Z"))

    def test_save_and_load(self):
        """Test basic save and load cycle."""
        # Create state
        state = self.store.load()
        state["total_sessions"] = 5
        state["total_tokens"] = 10000
        state["total_cost_usd"] = 3.50

        # Save
        self.store.save(state)

        # Verify file was created
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        self.assertTrue(metrics_file.exists())

        # Load and verify
        loaded_state = self.store.load()
        self.assertEqual(loaded_state["total_sessions"], 5)
        self.assertEqual(loaded_state["total_tokens"], 10000)
        self.assertEqual(loaded_state["total_cost_usd"], 3.50)

    def test_save_with_complete_state(self):
        """Test saving a complete state with all fields populated."""
        # Create agent profile
        profile: AgentProfile = {
            "agent_name": "coding",
            "total_invocations": 10,
            "successful_invocations": 9,
            "failed_invocations": 1,
            "total_tokens": 5000,
            "total_cost_usd": 0.50,
            "total_duration_seconds": 100.0,
            "commits_made": 0,
            "prs_created": 0,
            "prs_merged": 0,
            "files_created": 5,
            "files_modified": 3,
            "lines_added": 200,
            "lines_removed": 50,
            "tests_written": 2,
            "issues_created": 0,
            "issues_completed": 0,
            "messages_sent": 0,
            "reviews_completed": 0,
            "success_rate": 0.9,
            "avg_duration_seconds": 10.0,
            "avg_tokens_per_call": 500.0,
            "cost_per_success_usd": 0.056,
            "xp": 900,
            "level": 3,
            "current_streak": 5,
            "best_streak": 7,
            "achievements": ["first_blood"],
            "strengths": ["fast"],
            "weaknesses": [],
            "recent_events": ["event-1", "event-2"],
            "last_error": "",
            "last_active": "2026-02-14T10:00:00Z",
        }

        # Create event
        event: AgentEvent = {
            "event_id": "event-1",
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-45",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:05:00Z",
            "duration_seconds": 300.0,
            "status": "success",
            "input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 3000,
            "estimated_cost_usd": 0.09,
            "artifacts": ["file:metrics_store.py"],
            "error_message": "",
            "model_used": "claude-sonnet-4-5",
        }

        # Create session
        session: SessionSummary = {
            "session_id": "session-1",
            "session_number": 1,
            "session_type": "initializer",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:30:00Z",
            "status": "complete",
            "agents_invoked": ["coding"],
            "total_tokens": 3000,
            "total_cost_usd": 0.09,
            "tickets_worked": ["AI-45"],
        }

        # Create full state
        state = self.store.load()
        state["agents"]["coding"] = profile
        state["events"].append(event)
        state["sessions"].append(session)
        state["total_sessions"] = 1

        # Save and reload
        self.store.save(state)
        loaded = self.store.load()

        # Verify all data preserved
        self.assertIn("coding", loaded["agents"])
        self.assertEqual(len(loaded["events"]), 1)
        self.assertEqual(len(loaded["sessions"]), 1)
        self.assertEqual(loaded["events"][0]["event_id"], "event-1")
        self.assertEqual(loaded["sessions"][0]["session_id"], "session-1")

    def test_updated_at_timestamp(self):
        """Test that updated_at timestamp is updated on save."""
        state = self.store.load()
        original_updated = state["updated_at"]

        # Wait a bit to ensure timestamp changes
        time.sleep(0.01)

        # Save
        self.store.save(state)

        # Load and verify timestamp changed
        loaded = self.store.load()
        self.assertNotEqual(loaded["updated_at"], original_updated)


class TestAtomicWrites(unittest.TestCase):
    """Test atomic write behavior."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = MetricsStore(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_temp_file_created_during_write(self):
        """Test that a temp file is created and then renamed."""
        # We can't easily intercept the temp file mid-write,
        # but we can verify the final result is atomic
        state = self.store.load()
        state["total_sessions"] = 100

        self.store.save(state)

        # Verify no temp files remain after save
        temp_files = list(Path(self.temp_dir).glob('.agent_metrics_*.tmp'))
        self.assertEqual(len(temp_files), 0)

        # Verify main file exists
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        self.assertTrue(metrics_file.exists())

    def test_backup_file_created(self):
        """Test that backup file is created when overwriting existing file."""
        # Create initial state
        state = self.store.load()
        state["total_sessions"] = 1
        self.store.save(state)

        # Modify and save again
        state["total_sessions"] = 2
        self.store.save(state)

        # Verify backup file exists
        backup_file = Path(self.temp_dir) / MetricsStore.BACKUP_FILE
        self.assertTrue(backup_file.exists())

        # Verify backup contains old data
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
        self.assertEqual(backup_data["total_sessions"], 1)

        # Verify main file contains new data
        loaded = self.store.load()
        self.assertEqual(loaded["total_sessions"], 2)

    def test_file_remains_valid_json_during_save(self):
        """Test that the main file is never in an invalid state."""
        # Create initial state
        state = self.store.load()
        state["total_sessions"] = 1
        self.store.save(state)

        # Verify file is valid JSON
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        with open(metrics_file, 'r') as f:
            data = json.load(f)  # Should not raise
        self.assertEqual(data["total_sessions"], 1)


class TestFIFOEviction(unittest.TestCase):
    """Test FIFO eviction for events and sessions."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = MetricsStore(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_event(self, event_id: str) -> AgentEvent:
        """Helper to create a test event."""
        return {
            "event_id": event_id,
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-45",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:05:00Z",
            "duration_seconds": 300.0,
            "status": "success",
            "input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 3000,
            "estimated_cost_usd": 0.09,
            "artifacts": [],
            "error_message": "",
            "model_used": "claude-sonnet-4-5",
        }

    def _create_test_session(self, session_id: str, session_number: int) -> SessionSummary:
        """Helper to create a test session."""
        return {
            "session_id": session_id,
            "session_number": session_number,
            "session_type": "initializer",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:30:00Z",
            "status": "complete",
            "agents_invoked": ["coding"],
            "total_tokens": 3000,
            "total_cost_usd": 0.09,
            "tickets_worked": ["AI-45"],
        }

    def test_events_eviction(self):
        """Test that events are evicted when exceeding MAX_EVENTS."""
        state = self.store.load()

        # Add MAX_EVENTS + 10 events
        num_events = MetricsStore.MAX_EVENTS + 10
        for i in range(num_events):
            event = self._create_test_event(f"event-{i}")
            state["events"].append(event)

        # Save (should trigger eviction)
        self.store.save(state)

        # Load and verify only last MAX_EVENTS remain
        loaded = self.store.load()
        self.assertEqual(len(loaded["events"]), MetricsStore.MAX_EVENTS)

        # Verify it's the last MAX_EVENTS (newest ones)
        self.assertEqual(loaded["events"][0]["event_id"], f"event-{num_events - MetricsStore.MAX_EVENTS}")
        self.assertEqual(loaded["events"][-1]["event_id"], f"event-{num_events - 1}")

    def test_sessions_eviction(self):
        """Test that sessions are evicted when exceeding MAX_SESSIONS."""
        state = self.store.load()

        # Add MAX_SESSIONS + 5 sessions
        num_sessions = MetricsStore.MAX_SESSIONS + 5
        for i in range(num_sessions):
            session = self._create_test_session(f"session-{i}", i)
            state["sessions"].append(session)

        # Save (should trigger eviction)
        self.store.save(state)

        # Load and verify only last MAX_SESSIONS remain
        loaded = self.store.load()
        self.assertEqual(len(loaded["sessions"]), MetricsStore.MAX_SESSIONS)

        # Verify it's the last MAX_SESSIONS (newest ones)
        self.assertEqual(loaded["sessions"][0]["session_id"], f"session-{num_sessions - MetricsStore.MAX_SESSIONS}")
        self.assertEqual(loaded["sessions"][-1]["session_id"], f"session-{num_sessions - 1}")

    def test_no_eviction_when_under_limit(self):
        """Test that no eviction occurs when under the limit."""
        state = self.store.load()

        # Add fewer than MAX_EVENTS
        for i in range(10):
            event = self._create_test_event(f"event-{i}")
            state["events"].append(event)

        # Add fewer than MAX_SESSIONS
        for i in range(5):
            session = self._create_test_session(f"session-{i}", i)
            state["sessions"].append(session)

        # Save
        self.store.save(state)

        # Load and verify all data preserved
        loaded = self.store.load()
        self.assertEqual(len(loaded["events"]), 10)
        self.assertEqual(len(loaded["sessions"]), 5)


class TestCorruptionRecovery(unittest.TestCase):
    """Test corruption recovery scenarios."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = MetricsStore(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_recover_from_corrupted_main_file(self):
        """Test recovery from corrupted main file using backup."""
        # Create valid state and save twice to create backup
        state = self.store.load()
        state["total_sessions"] = 42
        self.store.save(state)

        # Save again to create backup (backup is created on second save)
        state["total_sessions"] = 42  # Keep same value
        self.store.save(state)

        # Now corrupt main file
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        with open(metrics_file, 'w') as f:
            f.write("{ invalid json !!!")

        # Load should recover from backup
        loaded = self.store.load()
        self.assertEqual(loaded["total_sessions"], 42)

    def test_recover_from_invalid_json(self):
        """Test recovery when main file has invalid JSON."""
        # Write invalid JSON to main file
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        with open(metrics_file, 'w') as f:
            f.write("not json at all")

        # Load should create fresh state
        loaded = self.store.load()
        self.assertEqual(loaded["total_sessions"], 0)
        self.assertEqual(loaded["project_name"], "test-project")

    def test_recover_from_invalid_structure(self):
        """Test recovery when JSON is valid but structure is wrong."""
        # Write valid JSON but wrong structure
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        with open(metrics_file, 'w') as f:
            json.dump({"some": "data", "but": "wrong"}, f)

        # Load should create fresh state
        loaded = self.store.load()
        self.assertEqual(loaded["total_sessions"], 0)
        self.assertIn("agents", loaded)
        self.assertIn("events", loaded)

    def test_both_files_corrupted(self):
        """Test recovery when both main and backup files are corrupted."""
        # Create valid state to create backup
        state = self.store.load()
        state["total_sessions"] = 10
        self.store.save(state)

        # Corrupt both files
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        backup_file = Path(self.temp_dir) / MetricsStore.BACKUP_FILE

        with open(metrics_file, 'w') as f:
            f.write("corrupted")
        with open(backup_file, 'w') as f:
            f.write("also corrupted")

        # Load should create fresh state
        loaded = self.store.load()
        self.assertEqual(loaded["total_sessions"], 0)

    def test_missing_required_fields(self):
        """Test recovery when required fields are missing."""
        # Write JSON with missing fields
        metrics_file = Path(self.temp_dir) / MetricsStore.METRICS_FILE
        with open(metrics_file, 'w') as f:
            json.dump({
                "version": 1,
                "project_name": "test",
                # Missing required fields
            }, f)

        # Load should create fresh state
        loaded = self.store.load()
        self.assertIn("agents", loaded)
        self.assertIn("events", loaded)
        self.assertIn("sessions", loaded)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = MetricsStore(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_state_round_trip(self):
        """Test saving and loading empty state."""
        state = self.store.load()

        # Should be empty
        self.assertEqual(len(state["events"]), 0)
        self.assertEqual(len(state["sessions"]), 0)

        # Save and reload
        self.store.save(state)
        loaded = self.store.load()

        self.assertEqual(len(loaded["events"]), 0)
        self.assertEqual(len(loaded["sessions"]), 0)

    def test_unicode_support(self):
        """Test that unicode characters are handled correctly."""
        state = self.store.load()

        # Add event with unicode
        event: AgentEvent = {
            "event_id": "event-unicode",
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-45",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:05:00Z",
            "duration_seconds": 300.0,
            "status": "success",
            "input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 3000,
            "estimated_cost_usd": 0.09,
            "artifacts": ["file:测试.py", "file:тест.py", "file:🎉.py"],
            "error_message": "",
            "model_used": "claude-sonnet-4-5",
        }
        state["events"].append(event)

        # Save and reload
        self.store.save(state)
        loaded = self.store.load()

        # Verify unicode preserved
        self.assertEqual(len(loaded["events"]), 1)
        self.assertIn("file:测试.py", loaded["events"][0]["artifacts"])
        self.assertIn("file:тест.py", loaded["events"][0]["artifacts"])
        self.assertIn("file:🎉.py", loaded["events"][0]["artifacts"])

    def test_get_stats(self):
        """Test get_stats() method."""
        # Initial stats (no files)
        stats = self.store.get_stats()
        self.assertFalse(stats["metrics_file_exists"])
        self.assertFalse(stats["backup_file_exists"])

        # Create and save state (first save)
        state = self.store.load()
        state["total_sessions"] = 5

        # Add some events
        for i in range(3):
            event: AgentEvent = {
                "event_id": f"event-{i}",
                "agent_name": "coding",
                "session_id": "session-1",
                "ticket_key": "AI-45",
                "started_at": "2026-02-14T10:00:00Z",
                "ended_at": "2026-02-14T10:05:00Z",
                "duration_seconds": 300.0,
                "status": "success",
                "input_tokens": 1000,
                "output_tokens": 2000,
                "total_tokens": 3000,
                "estimated_cost_usd": 0.09,
                "artifacts": [],
                "error_message": "",
                "model_used": "claude-sonnet-4-5",
            }
            state["events"].append(event)

        self.store.save(state)

        # Save again to create backup
        self.store.save(state)

        # Get stats again
        stats = self.store.get_stats()
        self.assertTrue(stats["metrics_file_exists"])
        self.assertTrue(stats["backup_file_exists"])
        self.assertEqual(stats["event_count"], 3)
        self.assertGreater(stats["metrics_file_size_bytes"], 0)


class TestThreadSafety(unittest.TestCase):
    """Test basic thread safety."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = MetricsStore(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_concurrent_saves(self):
        """Test concurrent saves from multiple threads."""
        # Initialize state
        state = self.store.load()
        self.store.save(state)

        errors = []

        def save_increment():
            """Load, increment, and save in a thread."""
            try:
                for _ in range(5):
                    state = self.store.load()
                    state["total_sessions"] += 1
                    self.store.save(state)
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = []
        for _ in range(3):
            t = threading.Thread(target=save_increment)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Should have no errors
        self.assertEqual(len(errors), 0)

        # Final state should have incremented (though exact count may vary due to race conditions)
        final_state = self.store.load()
        self.assertGreater(final_state["total_sessions"], 0)


class TestMetricsStoreIntegration(unittest.TestCase):
    """Integration tests simulating real usage patterns."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = MetricsStore(
            project_name="agent-status-dashboard",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_typical_workflow(self):
        """Test a typical workflow: create, add events, save, reload."""
        # 1. Load initial state
        state = self.store.load()
        self.assertEqual(state["total_sessions"], 0)

        # 2. Add some data
        state["total_sessions"] = 1
        state["total_tokens"] = 5000
        state["total_cost_usd"] = 0.15

        # Create and add event
        event: AgentEvent = {
            "event_id": "event-001",
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-45",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:05:00Z",
            "duration_seconds": 300.0,
            "status": "success",
            "input_tokens": 2000,
            "output_tokens": 3000,
            "total_tokens": 5000,
            "estimated_cost_usd": 0.15,
            "artifacts": ["file:metrics_store.py", "file:test_metrics_store.py"],
            "error_message": "",
            "model_used": "claude-sonnet-4-5",
        }
        state["events"].append(event)

        # 3. Save
        self.store.save(state)

        # 4. Create new store instance (simulating restart)
        new_store = MetricsStore(
            project_name="agent-status-dashboard",
            metrics_dir=Path(self.temp_dir)
        )

        # 5. Load and verify
        loaded = new_store.load()
        self.assertEqual(loaded["total_sessions"], 1)
        self.assertEqual(loaded["total_tokens"], 5000)
        self.assertEqual(len(loaded["events"]), 1)
        self.assertEqual(loaded["events"][0]["event_id"], "event-001")

    def test_multiple_sessions_workflow(self):
        """Test workflow with multiple sessions over time."""
        # Session 1
        state = self.store.load()
        state["total_sessions"] = 1

        session1: SessionSummary = {
            "session_id": "session-1",
            "session_number": 1,
            "session_type": "initializer",
            "started_at": "2026-02-14T09:00:00Z",
            "ended_at": "2026-02-14T09:30:00Z",
            "status": "complete",
            "agents_invoked": ["coding"],
            "total_tokens": 5000,
            "total_cost_usd": 0.15,
            "tickets_worked": ["AI-45"],
        }
        state["sessions"].append(session1)
        self.store.save(state)

        # Session 2
        state = self.store.load()
        state["total_sessions"] = 2

        session2: SessionSummary = {
            "session_id": "session-2",
            "session_number": 2,
            "session_type": "continuation",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:15:00Z",
            "status": "complete",
            "agents_invoked": ["github"],
            "total_tokens": 3000,
            "total_cost_usd": 0.09,
            "tickets_worked": ["AI-45"],
        }
        state["sessions"].append(session2)
        self.store.save(state)

        # Verify both sessions preserved
        loaded = self.store.load()
        self.assertEqual(len(loaded["sessions"]), 2)
        self.assertEqual(loaded["sessions"][0]["session_id"], "session-1")
        self.assertEqual(loaded["sessions"][1]["session_id"], "session-2")


if __name__ == "__main__":
    unittest.main()
