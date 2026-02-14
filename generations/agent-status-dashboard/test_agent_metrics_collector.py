"""Comprehensive tests for AgentMetricsCollector.

Tests verify:
1. Session lifecycle (start_session, end_session)
2. Successful agent tracking via context manager
3. Failed agent tracking (exceptions)
4. Event recording and persistence
5. Token/cost calculations
6. Agent profile updates
7. Session summary generation
8. Edge cases and error handling
"""

import tempfile
import time
import unittest
from pathlib import Path

from agent_metrics_collector import (
    AgentMetricsCollector,
    AgentTracker,
    _calculate_cost,
    _create_empty_profile,
    _update_agent_profile,
)
from metrics import AgentEvent


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions."""

    def test_calculate_cost_sonnet(self):
        """Test cost calculation for Sonnet model."""
        # Sonnet pricing: $0.003 input, $0.015 output per 1K tokens
        cost = _calculate_cost("claude-sonnet-4-5", 1000, 2000)

        # Expected: (1000/1000 * 0.003) + (2000/1000 * 0.015) = 0.003 + 0.030 = 0.033
        self.assertAlmostEqual(cost, 0.033, places=6)

    def test_calculate_cost_opus(self):
        """Test cost calculation for Opus model."""
        # Opus pricing: $0.015 input, $0.075 output per 1K tokens
        cost = _calculate_cost("claude-opus-4-6", 1000, 1000)

        # Expected: (1000/1000 * 0.015) + (1000/1000 * 0.075) = 0.015 + 0.075 = 0.090
        self.assertAlmostEqual(cost, 0.090, places=6)

    def test_calculate_cost_haiku(self):
        """Test cost calculation for Haiku model."""
        # Haiku pricing: $0.0008 input, $0.004 output per 1K tokens
        cost = _calculate_cost("claude-haiku-4-5", 5000, 3000)

        # Expected: (5000/1000 * 0.0008) + (3000/1000 * 0.004) = 0.004 + 0.012 = 0.016
        self.assertAlmostEqual(cost, 0.016, places=6)

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model uses default pricing."""
        # Unknown model should use default Sonnet pricing
        cost = _calculate_cost("unknown-model", 1000, 2000)

        # Should match Sonnet pricing
        expected = _calculate_cost("claude-sonnet-4-5", 1000, 2000)
        self.assertAlmostEqual(cost, expected, places=6)

    def test_create_empty_profile(self):
        """Test creating an empty agent profile."""
        profile = _create_empty_profile("coding")

        # Verify structure
        self.assertEqual(profile["agent_name"], "coding")
        self.assertEqual(profile["total_invocations"], 0)
        self.assertEqual(profile["successful_invocations"], 0)
        self.assertEqual(profile["failed_invocations"], 0)
        self.assertEqual(profile["total_tokens"], 0)
        self.assertEqual(profile["total_cost_usd"], 0.0)
        self.assertEqual(profile["current_streak"], 0)
        self.assertEqual(profile["best_streak"], 0)
        self.assertEqual(len(profile["recent_events"]), 0)
        self.assertEqual(len(profile["achievements"]), 0)

    def test_update_agent_profile_success(self):
        """Test updating profile with a successful event."""
        profile = _create_empty_profile("coding")

        event: AgentEvent = {
            "event_id": "event-1",
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-46",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:05:00Z",
            "duration_seconds": 300.0,
            "status": "success",
            "input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 3000,
            "estimated_cost_usd": 0.033,
            "artifacts": ["file:foo.py"],
            "error_message": "",
            "model_used": "claude-sonnet-4-5",
        }

        updated = _update_agent_profile(profile, event)

        # Verify counters
        self.assertEqual(updated["total_invocations"], 1)
        self.assertEqual(updated["successful_invocations"], 1)
        self.assertEqual(updated["failed_invocations"], 0)
        self.assertEqual(updated["total_tokens"], 3000)
        self.assertAlmostEqual(updated["total_cost_usd"], 0.033, places=6)
        self.assertEqual(updated["total_duration_seconds"], 300.0)

        # Verify streak
        self.assertEqual(updated["current_streak"], 1)
        self.assertEqual(updated["best_streak"], 1)

        # Verify derived metrics
        self.assertAlmostEqual(updated["success_rate"], 1.0, places=6)
        self.assertAlmostEqual(updated["avg_duration_seconds"], 300.0, places=6)
        self.assertAlmostEqual(updated["avg_tokens_per_call"], 3000.0, places=6)
        self.assertAlmostEqual(updated["cost_per_success_usd"], 0.033, places=6)

        # Verify recent events
        self.assertEqual(len(updated["recent_events"]), 1)
        self.assertEqual(updated["recent_events"][0], "event-1")
        self.assertEqual(updated["last_error"], "")

    def test_update_agent_profile_error(self):
        """Test updating profile with a failed event."""
        profile = _create_empty_profile("coding")

        # First add a success to establish a streak
        success_event: AgentEvent = {
            "event_id": "event-1",
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-46",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:05:00Z",
            "duration_seconds": 300.0,
            "status": "success",
            "input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 3000,
            "estimated_cost_usd": 0.033,
            "artifacts": [],
            "error_message": "",
            "model_used": "claude-sonnet-4-5",
        }
        profile = _update_agent_profile(profile, success_event)
        self.assertEqual(profile["current_streak"], 1)

        # Now add an error event
        error_event: AgentEvent = {
            "event_id": "event-2",
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-46",
            "started_at": "2026-02-14T10:10:00Z",
            "ended_at": "2026-02-14T10:11:00Z",
            "duration_seconds": 60.0,
            "status": "error",
            "input_tokens": 500,
            "output_tokens": 100,
            "total_tokens": 600,
            "estimated_cost_usd": 0.003,
            "artifacts": [],
            "error_message": "Test error",
            "model_used": "claude-sonnet-4-5",
        }

        updated = _update_agent_profile(profile, error_event)

        # Verify counters
        self.assertEqual(updated["total_invocations"], 2)
        self.assertEqual(updated["successful_invocations"], 1)
        self.assertEqual(updated["failed_invocations"], 1)

        # Verify streak was broken
        self.assertEqual(updated["current_streak"], 0)
        self.assertEqual(updated["best_streak"], 1)  # Best streak preserved

        # Verify error was recorded
        self.assertEqual(updated["last_error"], "Test error")

        # Verify derived metrics
        self.assertAlmostEqual(updated["success_rate"], 0.5, places=6)

    def test_update_agent_profile_artifact_counting(self):
        """Test that artifacts are counted correctly."""
        profile = _create_empty_profile("coding")

        event: AgentEvent = {
            "event_id": "event-1",
            "agent_name": "coding",
            "session_id": "session-1",
            "ticket_key": "AI-46",
            "started_at": "2026-02-14T10:00:00Z",
            "ended_at": "2026-02-14T10:05:00Z",
            "duration_seconds": 300.0,
            "status": "success",
            "input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 3000,
            "estimated_cost_usd": 0.033,
            "artifacts": [
                "commit:abc123",
                "file:created:foo.py",
                "file:modified:bar.py",
                "pr:created:#42",
                "issue:created:AI-47",
                "message:channel-general",
            ],
            "error_message": "",
            "model_used": "claude-sonnet-4-5",
        }

        updated = _update_agent_profile(profile, event)

        # Verify artifact counters
        self.assertEqual(updated["commits_made"], 1)
        self.assertEqual(updated["files_created"], 1)
        self.assertEqual(updated["files_modified"], 1)
        self.assertEqual(updated["prs_created"], 1)
        self.assertEqual(updated["issues_created"], 1)
        self.assertEqual(updated["messages_sent"], 1)

    def test_update_agent_profile_recent_events_cap(self):
        """Test that recent_events is capped at 20."""
        profile = _create_empty_profile("coding")

        # Add 25 events
        for i in range(25):
            event: AgentEvent = {
                "event_id": f"event-{i}",
                "agent_name": "coding",
                "session_id": "session-1",
                "ticket_key": "AI-46",
                "started_at": "2026-02-14T10:00:00Z",
                "ended_at": "2026-02-14T10:05:00Z",
                "duration_seconds": 300.0,
                "status": "success",
                "input_tokens": 1000,
                "output_tokens": 2000,
                "total_tokens": 3000,
                "estimated_cost_usd": 0.033,
                "artifacts": [],
                "error_message": "",
                "model_used": "claude-sonnet-4-5",
            }
            profile = _update_agent_profile(profile, event)

        # Verify only last 20 are kept
        self.assertEqual(len(profile["recent_events"]), 20)
        self.assertEqual(profile["recent_events"][0], "event-5")
        self.assertEqual(profile["recent_events"][-1], "event-24")


class TestAgentTracker(unittest.TestCase):
    """Test AgentTracker helper class."""

    def test_tracker_initialization(self):
        """Test tracker initialization."""
        tracker = AgentTracker(
            event_id="event-1",
            agent_name="coding",
            session_id="session-1",
            ticket_key="AI-46",
            model_used="claude-sonnet-4-5",
            started_at="2026-02-14T10:00:00Z",
        )

        self.assertEqual(tracker.event_id, "event-1")
        self.assertEqual(tracker.agent_name, "coding")
        self.assertEqual(tracker.input_tokens, 0)
        self.assertEqual(tracker.output_tokens, 0)
        self.assertEqual(len(tracker.artifacts), 0)
        self.assertEqual(tracker.status, "success")
        self.assertEqual(tracker.error_message, "")

    def test_add_tokens(self):
        """Test adding tokens to tracker."""
        tracker = AgentTracker(
            event_id="event-1",
            agent_name="coding",
            session_id="session-1",
            ticket_key="AI-46",
            model_used="claude-sonnet-4-5",
            started_at="2026-02-14T10:00:00Z",
        )

        tracker.add_tokens(1000, 2000)
        self.assertEqual(tracker.input_tokens, 1000)
        self.assertEqual(tracker.output_tokens, 2000)

        # Add more tokens (should accumulate)
        tracker.add_tokens(500, 300)
        self.assertEqual(tracker.input_tokens, 1500)
        self.assertEqual(tracker.output_tokens, 2300)

    def test_add_artifact(self):
        """Test adding artifacts to tracker."""
        tracker = AgentTracker(
            event_id="event-1",
            agent_name="coding",
            session_id="session-1",
            ticket_key="AI-46",
            model_used="claude-sonnet-4-5",
            started_at="2026-02-14T10:00:00Z",
        )

        tracker.add_artifact("file:foo.py")
        self.assertEqual(len(tracker.artifacts), 1)
        self.assertEqual(tracker.artifacts[0], "file:foo.py")

        tracker.add_artifact("commit:abc123")
        self.assertEqual(len(tracker.artifacts), 2)

    def test_set_error(self):
        """Test setting error on tracker."""
        tracker = AgentTracker(
            event_id="event-1",
            agent_name="coding",
            session_id="session-1",
            ticket_key="AI-46",
            model_used="claude-sonnet-4-5",
            started_at="2026-02-14T10:00:00Z",
        )

        tracker.set_error("Test error message")
        self.assertEqual(tracker.status, "error")
        self.assertEqual(tracker.error_message, "Test error message")

    def test_finalize(self):
        """Test finalizing tracker to create event."""
        tracker = AgentTracker(
            event_id="event-1",
            agent_name="coding",
            session_id="session-1",
            ticket_key="AI-46",
            model_used="claude-sonnet-4-5",
            started_at="2026-02-14T10:00:00Z",
        )

        tracker.add_tokens(1000, 2000)
        tracker.add_artifact("file:foo.py")

        # Small delay to ensure duration is measured
        time.sleep(0.01)

        event = tracker.finalize()

        # Verify event structure
        self.assertEqual(event["event_id"], "event-1")
        self.assertEqual(event["agent_name"], "coding")
        self.assertEqual(event["session_id"], "session-1")
        self.assertEqual(event["ticket_key"], "AI-46")
        self.assertEqual(event["status"], "success")
        self.assertEqual(event["input_tokens"], 1000)
        self.assertEqual(event["output_tokens"], 2000)
        self.assertEqual(event["total_tokens"], 3000)
        self.assertGreater(event["duration_seconds"], 0.0)
        self.assertEqual(len(event["artifacts"]), 1)
        self.assertEqual(event["model_used"], "claude-sonnet-4-5")
        self.assertGreater(event["estimated_cost_usd"], 0.0)


class TestAgentMetricsCollector(unittest.TestCase):
    """Test AgentMetricsCollector class."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.collector = AgentMetricsCollector(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test collector initialization."""
        self.assertEqual(self.collector.project_name, "test-project")
        self.assertIsNotNone(self.collector.store)
        self.assertEqual(len(self.collector._active_sessions), 0)

    def test_start_session(self):
        """Test starting a session."""
        session_id = self.collector.start_session(session_type="initializer")

        # Verify session was created
        self.assertIsNotNone(session_id)
        self.assertIn(session_id, self.collector._active_sessions)

        session_info = self.collector._active_sessions[session_id]
        self.assertEqual(session_info["session_type"], "initializer")
        self.assertEqual(session_info["session_number"], 1)
        self.assertEqual(len(session_info["agents_invoked"]), 0)
        self.assertEqual(session_info["total_tokens"], 0)

    def test_start_multiple_sessions(self):
        """Test starting multiple sessions increments session number."""
        session_id1 = self.collector.start_session(session_type="initializer")
        self.collector.end_session(session_id1, status="complete")

        session_id2 = self.collector.start_session(session_type="continuation")

        session_info = self.collector._active_sessions[session_id2]
        self.assertEqual(session_info["session_number"], 2)

    def test_end_session(self):
        """Test ending a session."""
        session_id = self.collector.start_session(session_type="initializer")

        # End session
        self.collector.end_session(session_id, status="complete")

        # Verify session was removed from active sessions
        self.assertNotIn(session_id, self.collector._active_sessions)

        # Verify session was saved to state
        state = self.collector.get_state()
        self.assertEqual(len(state["sessions"]), 1)
        self.assertEqual(state["sessions"][0]["session_id"], session_id)
        self.assertEqual(state["sessions"][0]["status"], "complete")
        self.assertEqual(state["total_sessions"], 1)

    def test_end_session_invalid_id(self):
        """Test ending a non-existent session raises error."""
        with self.assertRaises(ValueError) as context:
            self.collector.end_session("invalid-session-id")

        self.assertIn("not an active session", str(context.exception))

    def test_track_agent_success(self):
        """Test tracking a successful agent delegation."""
        session_id = self.collector.start_session(session_type="initializer")

        with self.collector.track_agent(
            "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(1000, 2000)
            tracker.add_artifact("file:foo.py")

        # Verify event was recorded
        state = self.collector.get_state()
        self.assertEqual(len(state["events"]), 1)

        event = state["events"][0]
        self.assertEqual(event["agent_name"], "coding")
        self.assertEqual(event["ticket_key"], "AI-46")
        self.assertEqual(event["status"], "success")
        self.assertEqual(event["input_tokens"], 1000)
        self.assertEqual(event["output_tokens"], 2000)
        self.assertEqual(event["total_tokens"], 3000)
        self.assertIn("file:foo.py", event["artifacts"])

        # Verify agent profile was created/updated
        self.assertIn("coding", state["agents"])
        profile = state["agents"]["coding"]
        self.assertEqual(profile["total_invocations"], 1)
        self.assertEqual(profile["successful_invocations"], 1)

        # Verify session was updated
        session_info = self.collector._active_sessions[session_id]
        self.assertIn("coding", session_info["agents_invoked"])
        self.assertIn("AI-46", session_info["tickets_worked"])

    def test_track_agent_with_exception(self):
        """Test tracking an agent that raises an exception."""
        session_id = self.collector.start_session(session_type="initializer")

        # Track agent that raises exception
        with self.assertRaises(ValueError):
            with self.collector.track_agent(
                "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id
            ) as tracker:
                tracker.add_tokens(500, 100)
                raise ValueError("Test error")

        # Verify event was still recorded with error status
        state = self.collector.get_state()
        self.assertEqual(len(state["events"]), 1)

        event = state["events"][0]
        self.assertEqual(event["agent_name"], "coding")
        self.assertEqual(event["status"], "error")
        self.assertEqual(event["error_message"], "Test error")
        self.assertEqual(event["input_tokens"], 500)
        self.assertEqual(event["output_tokens"], 100)

        # Verify profile shows failed invocation
        profile = state["agents"]["coding"]
        self.assertEqual(profile["total_invocations"], 1)
        self.assertEqual(profile["successful_invocations"], 0)
        self.assertEqual(profile["failed_invocations"], 1)
        self.assertEqual(profile["last_error"], "Test error")

    def test_track_agent_auto_session(self):
        """Test tracking agent without explicit session creates temporary session."""
        with self.collector.track_agent("coding", "AI-46", "claude-sonnet-4-5") as tracker:
            tracker.add_tokens(1000, 1000)

        # Verify event was recorded
        state = self.collector.get_state()
        self.assertEqual(len(state["events"]), 1)

        # Verify a session was created and closed
        self.assertEqual(len(state["sessions"]), 1)
        self.assertEqual(state["sessions"][0]["status"], "complete")

        # Verify no active sessions remain
        self.assertEqual(len(self.collector._active_sessions), 0)

    def test_track_agent_cost_calculation(self):
        """Test that costs are calculated correctly."""
        with self.collector.track_agent("coding", "AI-46", "claude-sonnet-4-5") as tracker:
            tracker.add_tokens(1000, 2000)

        state = self.collector.get_state()
        event = state["events"][0]

        # Expected cost for Sonnet: (1000/1000 * 0.003) + (2000/1000 * 0.015) = 0.033
        self.assertAlmostEqual(event["estimated_cost_usd"], 0.033, places=6)

        # Verify global counters
        self.assertAlmostEqual(state["total_cost_usd"], 0.033, places=6)

    def test_track_agent_global_counters(self):
        """Test that global counters are updated correctly."""
        with self.collector.track_agent("coding", "AI-46", "claude-sonnet-4-5") as tracker:
            tracker.add_tokens(1000, 2000)

        state = self.collector.get_state()

        # Verify global counters
        self.assertEqual(state["total_tokens"], 3000)
        self.assertGreater(state["total_cost_usd"], 0.0)
        self.assertGreater(state["total_duration_seconds"], 0.0)

    def test_multiple_agents_in_session(self):
        """Test tracking multiple agents in one session."""
        session_id = self.collector.start_session(session_type="initializer")

        # Track first agent
        with self.collector.track_agent(
            "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(1000, 2000)

        # Track second agent
        with self.collector.track_agent(
            "github", "AI-46", "claude-haiku-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(500, 500)

        # End session
        self.collector.end_session(session_id, status="complete")

        # Verify session summary
        state = self.collector.get_state()
        session = state["sessions"][0]

        self.assertEqual(len(session["agents_invoked"]), 2)
        self.assertIn("coding", session["agents_invoked"])
        self.assertIn("github", session["agents_invoked"])
        self.assertEqual(session["total_tokens"], 4000)
        self.assertIn("AI-46", session["tickets_worked"])

        # Verify both agent profiles exist
        self.assertIn("coding", state["agents"])
        self.assertIn("github", state["agents"])

    def test_session_summary_fields(self):
        """Test that session summary has all required fields."""
        session_id = self.collector.start_session(session_type="initializer")

        with self.collector.track_agent(
            "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(1000, 1000)

        self.collector.end_session(session_id, status="complete")

        state = self.collector.get_state()
        session = state["sessions"][0]

        # Verify all required fields
        self.assertIn("session_id", session)
        self.assertIn("session_number", session)
        self.assertIn("session_type", session)
        self.assertIn("started_at", session)
        self.assertIn("ended_at", session)
        self.assertIn("status", session)
        self.assertIn("agents_invoked", session)
        self.assertIn("total_tokens", session)
        self.assertIn("total_cost_usd", session)
        self.assertIn("tickets_worked", session)

        # Verify types
        self.assertEqual(session["session_type"], "initializer")
        self.assertEqual(session["status"], "complete")
        self.assertTrue(session["started_at"].endswith("Z"))
        self.assertTrue(session["ended_at"].endswith("Z"))

    def test_persistence_across_instances(self):
        """Test that data persists across collector instances."""
        # Create first collector and add data
        with self.collector.track_agent("coding", "AI-46", "claude-sonnet-4-5") as tracker:
            tracker.add_tokens(1000, 1000)

        # Create new collector instance with same directory
        new_collector = AgentMetricsCollector(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

        # Verify data was persisted
        state = new_collector.get_state()
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(len(state["agents"]), 1)
        self.assertIn("coding", state["agents"])

    def test_get_state(self):
        """Test get_state() returns current dashboard state."""
        state1 = self.collector.get_state()

        # Initial state should be empty
        self.assertEqual(len(state1["events"]), 0)
        self.assertEqual(len(state1["agents"]), 0)

        # Add an event
        with self.collector.track_agent("coding", "AI-46", "claude-sonnet-4-5") as tracker:
            tracker.add_tokens(1000, 1000)

        # Get state again
        state2 = self.collector.get_state()
        self.assertEqual(len(state2["events"]), 1)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.collector = AgentMetricsCollector(
            project_name="test-project",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_track_agent_zero_tokens(self):
        """Test tracking agent with zero tokens."""
        with self.collector.track_agent("coding", "AI-46", "claude-sonnet-4-5") as tracker:
            # Don't add any tokens
            pass

        state = self.collector.get_state()
        event = state["events"][0]

        self.assertEqual(event["input_tokens"], 0)
        self.assertEqual(event["output_tokens"], 0)
        self.assertEqual(event["total_tokens"], 0)
        self.assertEqual(event["estimated_cost_usd"], 0.0)

    def test_track_agent_no_artifacts(self):
        """Test tracking agent with no artifacts."""
        with self.collector.track_agent("coding", "AI-46", "claude-sonnet-4-5") as tracker:
            tracker.add_tokens(1000, 1000)
            # Don't add any artifacts

        state = self.collector.get_state()
        event = state["events"][0]

        self.assertEqual(len(event["artifacts"]), 0)

    def test_multiple_tickets_in_session(self):
        """Test tracking multiple tickets in one session."""
        session_id = self.collector.start_session(session_type="initializer")

        with self.collector.track_agent(
            "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(1000, 1000)

        with self.collector.track_agent(
            "coding", "AI-47", "claude-sonnet-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(1000, 1000)

        self.collector.end_session(session_id, status="complete")

        state = self.collector.get_state()
        session = state["sessions"][0]

        self.assertEqual(len(session["tickets_worked"]), 2)
        self.assertIn("AI-46", session["tickets_worked"])
        self.assertIn("AI-47", session["tickets_worked"])

    def test_session_error_status(self):
        """Test ending session with error status."""
        session_id = self.collector.start_session(session_type="initializer")
        self.collector.end_session(session_id, status="error")

        state = self.collector.get_state()
        session = state["sessions"][0]

        self.assertEqual(session["status"], "error")

    def test_continuation_session_type(self):
        """Test creating a continuation session."""
        session_id = self.collector.start_session(session_type="continuation")

        session_info = self.collector._active_sessions[session_id]
        self.assertEqual(session_info["session_type"], "continuation")

    def test_nested_track_agent_not_supported(self):
        """Test that nested track_agent calls work but create separate events."""
        # This isn't really "supported" behavior but should handle gracefully
        session_id = self.collector.start_session(session_type="initializer")

        with self.collector.track_agent(
            "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id
        ) as tracker1:
            tracker1.add_tokens(1000, 1000)

            # Inner track_agent (different agent)
            with self.collector.track_agent(
                "github", "AI-46", "claude-sonnet-4-5", session_id=session_id
            ) as tracker2:
                tracker2.add_tokens(500, 500)

        # Both events should be recorded
        state = self.collector.get_state()
        self.assertEqual(len(state["events"]), 2)


class TestIntegration(unittest.TestCase):
    """Integration tests simulating real usage."""

    def setUp(self):
        """Create temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.collector = AgentMetricsCollector(
            project_name="agent-status-dashboard",
            metrics_dir=Path(self.temp_dir)
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_typical_workflow(self):
        """Test a typical workflow: session with multiple agents."""
        # Start session
        session_id = self.collector.start_session(session_type="initializer")

        # Track coding agent
        with self.collector.track_agent(
            "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(2000, 3000)
            tracker.add_artifact("file:created:agent_metrics_collector.py")
            tracker.add_artifact("file:created:test_agent_metrics_collector.py")

        # Track github agent
        with self.collector.track_agent(
            "github", "AI-46", "claude-haiku-4-5", session_id=session_id
        ) as tracker:
            tracker.add_tokens(500, 500)
            tracker.add_artifact("commit:abc123")
            tracker.add_artifact("pr:created:#46")

        # End session
        self.collector.end_session(session_id, status="complete")

        # Verify final state
        state = self.collector.get_state()

        # Verify events
        self.assertEqual(len(state["events"]), 2)

        # Verify agents
        self.assertEqual(len(state["agents"]), 2)
        self.assertIn("coding", state["agents"])
        self.assertIn("github", state["agents"])

        # Verify session
        self.assertEqual(len(state["sessions"]), 1)
        session = state["sessions"][0]
        self.assertEqual(len(session["agents_invoked"]), 2)
        self.assertEqual(session["total_tokens"], 6000)

        # Verify global counters
        self.assertEqual(state["total_sessions"], 1)
        self.assertEqual(state["total_tokens"], 6000)
        self.assertGreater(state["total_cost_usd"], 0.0)

    def test_multiple_sessions_workflow(self):
        """Test workflow with multiple sessions."""
        # Session 1
        session_id1 = self.collector.start_session(session_type="initializer")
        with self.collector.track_agent(
            "coding", "AI-46", "claude-sonnet-4-5", session_id=session_id1
        ) as tracker:
            tracker.add_tokens(1000, 1000)
        self.collector.end_session(session_id1, status="complete")

        # Session 2
        session_id2 = self.collector.start_session(session_type="continuation")
        with self.collector.track_agent(
            "github", "AI-46", "claude-sonnet-4-5", session_id=session_id2
        ) as tracker:
            tracker.add_tokens(1000, 1000)
        self.collector.end_session(session_id2, status="complete")

        # Verify final state
        state = self.collector.get_state()
        self.assertEqual(len(state["sessions"]), 2)
        self.assertEqual(state["total_sessions"], 2)
        self.assertEqual(len(state["events"]), 2)


if __name__ == "__main__":
    unittest.main()
