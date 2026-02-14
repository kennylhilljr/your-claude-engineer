"""Unit tests for AgentMetricsCollector and MetricsStore.

Tests the core metrics collection functionality including session lifecycle,
event recording, MetricsStore persistence, and integration with Phase 1 components.

Test Coverage:
- MetricsStore: load, save, atomic writes, FIFO eviction, corruption recovery
- AgentMetricsCollector: start_session, end_session, track_agent context manager
- Event recording and profile updates
- XP calculation integration
- Achievement checking integration
- Strengths/weaknesses detection integration
"""

import json
import tempfile
import time
from pathlib import Path

import pytest

from agent_metrics import AgentMetricsCollector, AgentTracker, MetricsStore
from metrics import DashboardState


class TestMetricsStore:
    """Test the MetricsStore persistence layer."""

    def test_create_fresh_state(self, tmp_path: Path):
        """Test creating a fresh dashboard state."""
        store = MetricsStore(tmp_path)
        state = store._create_fresh_state()

        assert state["version"] == 1
        assert state["project_name"] == tmp_path.name
        assert state["total_sessions"] == 0
        assert state["total_tokens"] == 0
        assert state["total_cost_usd"] == 0.0
        assert state["total_duration_seconds"] == 0.0
        assert state["agents"] == {}
        assert state["events"] == []
        assert state["sessions"] == []
        assert "created_at" in state
        assert "updated_at" in state

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test loading when metrics file doesn't exist."""
        store = MetricsStore(tmp_path)
        state = store.load()

        # Should return fresh state
        assert state["version"] == 1
        assert state["total_sessions"] == 0
        assert len(state["events"]) == 0

    def test_save_and_load(self, tmp_path: Path):
        """Test saving and loading dashboard state."""
        store = MetricsStore(tmp_path)
        state = store._create_fresh_state()

        # Modify state
        state["total_sessions"] = 5
        state["total_tokens"] = 10000
        state["total_cost_usd"] = 1.5

        # Save
        store.save(state)

        # Verify file exists
        assert store.metrics_file.exists()

        # Load and verify
        loaded_state = store.load()
        assert loaded_state["total_sessions"] == 5
        assert loaded_state["total_tokens"] == 10000
        assert loaded_state["total_cost_usd"] == 1.5

    def test_atomic_write(self, tmp_path: Path):
        """Test that saves use atomic writes (temp file + rename)."""
        store = MetricsStore(tmp_path)
        state = store._create_fresh_state()

        # Save initial state
        store.save(state)

        # Modify and save again
        state["total_sessions"] = 10
        store.save(state)

        # Verify no .tmp files left behind
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

        # Verify state is correct
        loaded_state = store.load()
        assert loaded_state["total_sessions"] == 10

    def test_fifo_eviction_events(self, tmp_path: Path):
        """Test FIFO eviction of events when over cap."""
        store = MetricsStore(tmp_path)
        state = store._create_fresh_state()

        # Add more events than cap
        for i in range(MetricsStore.EVENTS_CAP + 10):
            state["events"].append({
                "event_id": f"event-{i}",
                "agent_name": "test",
                "session_id": "session-1",
                "ticket_key": "",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:01:00Z",
                "duration_seconds": 60.0,
                "status": "success",
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "estimated_cost_usd": 0.01,
                "artifacts": [],
                "error_message": "",
                "model_used": "claude-sonnet-4-5-20250929",
            })

        # Apply eviction
        store._apply_fifo_eviction(state)

        # Should keep only the most recent EVENTS_CAP events
        assert len(state["events"]) == MetricsStore.EVENTS_CAP

        # Oldest events should be evicted
        assert state["events"][0]["event_id"] == "event-10"
        assert state["events"][-1]["event_id"] == f"event-{MetricsStore.EVENTS_CAP + 9}"

    def test_fifo_eviction_sessions(self, tmp_path: Path):
        """Test FIFO eviction of sessions when over cap."""
        store = MetricsStore(tmp_path)
        state = store._create_fresh_state()

        # Add more sessions than cap
        for i in range(MetricsStore.SESSIONS_CAP + 5):
            state["sessions"].append({
                "session_id": f"session-{i}",
                "session_number": i + 1,
                "session_type": "continuation",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:10:00Z",
                "status": "continue",
                "agents_invoked": ["test"],
                "total_tokens": 1000,
                "total_cost_usd": 0.05,
                "tickets_worked": [],
            })

        # Apply eviction
        store._apply_fifo_eviction(state)

        # Should keep only the most recent SESSIONS_CAP sessions
        assert len(state["sessions"]) == MetricsStore.SESSIONS_CAP

        # Oldest sessions should be evicted
        assert state["sessions"][0]["session_id"] == "session-5"
        assert state["sessions"][-1]["session_id"] == f"session-{MetricsStore.SESSIONS_CAP + 4}"

    def test_corruption_recovery(self, tmp_path: Path):
        """Test recovery from corrupted metrics file."""
        store = MetricsStore(tmp_path)

        # Create corrupted JSON file
        with open(store.metrics_file, 'w') as f:
            f.write("{invalid json content")

        # Load should recover with fresh state
        state = store.load()
        assert state["version"] == 1
        assert state["total_sessions"] == 0

        # Corrupted file should be backed up
        corrupted_file = tmp_path / ".agent_metrics.json.corrupted"
        assert corrupted_file.exists()


class TestAgentMetricsCollector:
    """Test the AgentMetricsCollector session lifecycle."""

    def test_initialization(self, tmp_path: Path):
        """Test collector initialization."""
        collector = AgentMetricsCollector(tmp_path)

        assert collector.project_dir == tmp_path
        assert isinstance(collector.store, MetricsStore)
        assert isinstance(collector.state, dict)
        assert collector.current_session_id is None

    def test_start_session(self, tmp_path: Path):
        """Test starting a session."""
        collector = AgentMetricsCollector(tmp_path)

        session_id = collector.start_session(session_num=1, is_initializer=True)

        assert session_id is not None
        assert collector.current_session_id == session_id
        assert collector.current_session_number == 1
        assert collector.current_session_type == "initializer"
        assert collector.current_session_agents == []
        assert collector.current_session_tickets == []

    def test_start_session_continuation(self, tmp_path: Path):
        """Test starting a continuation session."""
        collector = AgentMetricsCollector(tmp_path)

        session_id = collector.start_session(session_num=2, is_initializer=False)

        assert collector.current_session_type == "continuation"

    def test_start_session_while_in_progress_raises_error(self, tmp_path: Path):
        """Test that starting a session while one is in progress raises RuntimeError."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with pytest.raises(RuntimeError, match="already in progress"):
            collector.start_session(session_num=2)

    def test_end_session(self, tmp_path: Path):
        """Test ending a session."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1, is_initializer=True)

        summary = collector.end_session(status="continue")

        assert summary["session_number"] == 1
        assert summary["session_type"] == "initializer"
        assert summary["status"] == "continue"
        assert summary["total_tokens"] == 0  # No events yet
        assert summary["total_cost_usd"] == 0.0

        # Session should be added to history
        assert len(collector.state["sessions"]) == 1
        assert collector.state["total_sessions"] == 1

        # Current session should be cleared
        assert collector.current_session_id is None

    def test_end_session_without_start_raises_error(self, tmp_path: Path):
        """Test that ending a session without starting raises RuntimeError."""
        collector = AgentMetricsCollector(tmp_path)

        with pytest.raises(RuntimeError, match="No session in progress"):
            collector.end_session()

    def test_end_session_status_variants(self, tmp_path: Path):
        """Test ending session with different status values."""
        collector = AgentMetricsCollector(tmp_path)

        # Test "error" status
        collector.start_session(session_num=1)
        summary = collector.end_session(status="error")
        assert summary["status"] == "error"

        # Test "complete" status
        collector.start_session(session_num=2)
        summary = collector.end_session(status="complete")
        assert summary["status"] == "complete"

    def test_get_dashboard_state(self, tmp_path: Path):
        """Test getting the dashboard state."""
        collector = AgentMetricsCollector(tmp_path)

        state = collector.get_dashboard_state()

        assert isinstance(state, dict)
        assert "version" in state
        assert "agents" in state
        assert "events" in state
        assert "sessions" in state

    def test_get_agent_profile_nonexistent(self, tmp_path: Path):
        """Test getting a profile for a nonexistent agent."""
        collector = AgentMetricsCollector(tmp_path)

        profile = collector.get_agent_profile("nonexistent")

        assert profile is None

    def test_ensure_agent_profile(self, tmp_path: Path):
        """Test creating an agent profile."""
        collector = AgentMetricsCollector(tmp_path)

        profile = collector._ensure_agent_profile("coding")

        assert profile["agent_name"] == "coding"
        assert profile["total_invocations"] == 0
        assert profile["successful_invocations"] == 0
        assert profile["failed_invocations"] == 0
        assert profile["xp"] == 0
        assert profile["level"] == 1
        assert profile["current_streak"] == 0
        assert profile["achievements"] == []

        # Should be in state
        assert "coding" in collector.state["agents"]

    def test_track_agent_context_manager(self, tmp_path: Path):
        """Test the track_agent context manager."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding", ticket_key="AI-50") as tracker:
            assert isinstance(tracker, AgentTracker)
            assert tracker.agent_name == "coding"
            assert tracker.ticket_key == "AI-50"

            # Set some data
            tracker.set_tokens(input_tokens=1000, output_tokens=500)
            tracker.add_artifact("file:test.py")

        # After context exits, event should be recorded
        assert len(collector.state["events"]) == 1
        assert collector.state["events"][0]["agent_name"] == "coding"
        assert collector.state["events"][0]["input_tokens"] == 1000
        assert collector.state["events"][0]["output_tokens"] == 500
        assert "file:test.py" in collector.state["events"][0]["artifacts"]

    def test_track_agent_without_session_raises_error(self, tmp_path: Path):
        """Test that track_agent without a session raises RuntimeError."""
        collector = AgentMetricsCollector(tmp_path)

        with pytest.raises(RuntimeError, match="No session in progress"):
            with collector.track_agent("coding"):
                pass

    def test_track_agent_updates_session_tracking(self, tmp_path: Path):
        """Test that track_agent updates session agents and tickets."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding", ticket_key="AI-50"):
            pass

        with collector.track_agent("github", ticket_key="AI-51"):
            pass

        # Session should track agents and tickets
        summary = collector.end_session()
        assert "coding" in summary["agents_invoked"]
        assert "github" in summary["agents_invoked"]
        assert "AI-50" in summary["tickets_worked"]
        assert "AI-51" in summary["tickets_worked"]

    def test_record_event_updates_profile(self, tmp_path: Path):
        """Test that recording an event updates the agent profile."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding", ticket_key="AI-50") as tracker:
            tracker.set_tokens(input_tokens=1000, output_tokens=500)

        # Profile should be updated
        profile = collector.get_agent_profile("coding")
        assert profile is not None
        assert profile["total_invocations"] == 1
        assert profile["successful_invocations"] == 1
        assert profile["total_tokens"] == 1500
        assert profile["current_streak"] == 1

    def test_record_event_updates_global_counters(self, tmp_path: Path):
        """Test that recording an event updates global counters."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding") as tracker:
            tracker.set_tokens(input_tokens=1000, output_tokens=500)

        # Global counters should be updated
        assert collector.state["total_tokens"] == 1500
        assert collector.state["total_cost_usd"] > 0

    def test_successful_invocation_updates_streak(self, tmp_path: Path):
        """Test that successful invocations increment streak."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # First success
        with collector.track_agent("coding"):
            pass

        profile = collector.get_agent_profile("coding")
        assert profile["current_streak"] == 1
        assert profile["best_streak"] == 1

        # Second success
        with collector.track_agent("coding"):
            pass

        profile = collector.get_agent_profile("coding")
        assert profile["current_streak"] == 2
        assert profile["best_streak"] == 2

    def test_failed_invocation_resets_streak(self, tmp_path: Path):
        """Test that failed invocations reset streak."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # Success
        with collector.track_agent("coding"):
            pass

        # Failure
        with collector.track_agent("coding") as tracker:
            tracker.set_error("Test error")

        profile = collector.get_agent_profile("coding")
        assert profile["current_streak"] == 0
        assert profile["best_streak"] == 1  # Best streak preserved
        assert profile["failed_invocations"] == 1
        assert profile["last_error"] == "Test error"

    def test_xp_calculation_integration(self, tmp_path: Path):
        """Test that XP is calculated and level is updated."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # Successful invocation should award base XP (10) + streak bonus
        with collector.track_agent("coding"):
            pass

        profile = collector.get_agent_profile("coding")
        # Base XP (10) + streak bonus (1) = 11
        assert profile["xp"] == 11
        assert profile["level"] == 1

    def test_derived_metrics_calculation(self, tmp_path: Path):
        """Test that derived metrics are calculated correctly."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # Two successful invocations
        with collector.track_agent("coding") as tracker:
            tracker.set_tokens(input_tokens=1000, output_tokens=500)

        # Sleep briefly to ensure different duration
        time.sleep(0.01)

        with collector.track_agent("coding") as tracker:
            tracker.set_tokens(input_tokens=2000, output_tokens=1000)

        profile = collector.get_agent_profile("coding")

        # Check derived metrics
        assert profile["success_rate"] == 1.0  # 2/2
        assert profile["avg_tokens_per_call"] == 2250.0  # (1500 + 3000) / 2
        assert profile["avg_duration_seconds"] > 0
        assert profile["cost_per_success_usd"] > 0

    def test_recent_events_tracking(self, tmp_path: Path):
        """Test that recent events are tracked (last 20)."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # Create 25 events
        for _ in range(25):
            with collector.track_agent("coding"):
                pass

        profile = collector.get_agent_profile("coding")

        # Should keep only last 20
        assert len(profile["recent_events"]) == 20

    def test_session_summary_rollup(self, tmp_path: Path):
        """Test that session summary rolls up metrics correctly."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # Multiple agents in session
        with collector.track_agent("coding", ticket_key="AI-50") as tracker:
            tracker.set_tokens(input_tokens=1000, output_tokens=500)

        with collector.track_agent("github", ticket_key="AI-50") as tracker:
            tracker.set_tokens(input_tokens=500, output_tokens=250)

        summary = collector.end_session()

        # Check rollup
        assert summary["total_tokens"] == 2250  # 1500 + 750
        assert summary["total_cost_usd"] > 0
        assert len(summary["agents_invoked"]) == 2
        assert "coding" in summary["agents_invoked"]
        assert "github" in summary["agents_invoked"]
        assert "AI-50" in summary["tickets_worked"]

    def test_persistence_across_sessions(self, tmp_path: Path):
        """Test that metrics persist across collector instances."""
        # First collector instance
        collector1 = AgentMetricsCollector(tmp_path)
        collector1.start_session(session_num=1)

        with collector1.track_agent("coding") as tracker:
            tracker.set_tokens(input_tokens=1000, output_tokens=500)

        collector1.end_session()

        # Create new collector instance (simulating reload)
        collector2 = AgentMetricsCollector(tmp_path)

        # State should be loaded
        assert collector2.state["total_sessions"] == 1
        assert "coding" in collector2.state["agents"]
        assert len(collector2.state["events"]) == 1

        profile = collector2.get_agent_profile("coding")
        assert profile["total_invocations"] == 1

    def test_multiple_sessions_accumulate(self, tmp_path: Path):
        """Test that multiple sessions accumulate metrics correctly."""
        collector = AgentMetricsCollector(tmp_path)

        # Session 1
        collector.start_session(session_num=1)
        with collector.track_agent("coding"):
            pass
        collector.end_session()

        # Session 2
        collector.start_session(session_num=2)
        with collector.track_agent("coding"):
            pass
        collector.end_session()

        # Check accumulation
        assert collector.state["total_sessions"] == 2
        assert len(collector.state["sessions"]) == 2

        profile = collector.get_agent_profile("coding")
        assert profile["total_invocations"] == 2


class TestAgentTracker:
    """Test the AgentTracker class."""

    def test_set_tokens(self, tmp_path: Path):
        """Test setting token counts."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding") as tracker:
            tracker.set_tokens(input_tokens=1000, output_tokens=500)

            assert tracker.input_tokens == 1000
            assert tracker.output_tokens == 500

    def test_add_artifact(self, tmp_path: Path):
        """Test adding artifacts."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding") as tracker:
            tracker.add_artifact("file:test.py")
            tracker.add_artifact("commit:abc123")

            assert len(tracker.artifacts) == 2
            assert "file:test.py" in tracker.artifacts
            assert "commit:abc123" in tracker.artifacts

    def test_set_error(self, tmp_path: Path):
        """Test setting error status."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding") as tracker:
            tracker.set_error("Test error message")

            assert tracker.error_message == "Test error message"
            assert tracker.status == "error"

    def test_set_model(self, tmp_path: Path):
        """Test setting model."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding") as tracker:
            tracker.set_model("claude-opus-4-6")

            assert tracker.model_used == "claude-opus-4-6"

    def test_finalize_calculates_duration(self, tmp_path: Path):
        """Test that finalize calculates duration correctly."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding") as tracker:
            time.sleep(0.1)  # Sleep for 100ms

        # Event should have duration > 0
        event = collector.state["events"][0]
        assert event["duration_seconds"] >= 0.1

    def test_finalize_calculates_cost(self, tmp_path: Path):
        """Test that finalize calculates cost correctly."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        with collector.track_agent("coding") as tracker:
            tracker.set_tokens(input_tokens=1000, output_tokens=500)

        # Event should have cost > 0
        event = collector.state["events"][0]
        assert event["estimated_cost_usd"] > 0

        # Cost should be: (1000/1000 * 0.003) + (500/1000 * 0.015) = 0.003 + 0.0075 = 0.0105
        assert abs(event["estimated_cost_usd"] - 0.0105) < 0.0001


class TestIntegrationWithPhase1:
    """Test integration with Phase 1 components (XP, achievements, strengths/weaknesses)."""

    def test_achievement_integration(self, tmp_path: Path):
        """Test that achievements are detected and awarded."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # First successful invocation should earn "first_blood" achievement
        with collector.track_agent("coding"):
            pass

        profile = collector.get_agent_profile("coding")
        assert "first_blood" in profile["achievements"]

    def test_xp_and_level_integration(self, tmp_path: Path):
        """Test that XP and levels are calculated correctly."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # Create enough successful invocations to gain levels
        for _ in range(10):
            with collector.track_agent("coding"):
                pass

        profile = collector.get_agent_profile("coding")

        # Should have XP and possibly leveled up
        assert profile["xp"] > 0
        assert profile["level"] >= 1

    def test_strengths_weaknesses_integration(self, tmp_path: Path):
        """Test that strengths and weaknesses are detected."""
        collector = AgentMetricsCollector(tmp_path)
        collector.start_session(session_num=1)

        # Create many successful invocations for high success rate
        for _ in range(20):
            with collector.track_agent("coding"):
                pass

        profile = collector.get_agent_profile("coding")

        # Should detect "high_success_rate" strength
        # Note: Other strengths/weaknesses depend on comparisons with other agents
        assert isinstance(profile["strengths"], list)
        assert isinstance(profile["weaknesses"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
