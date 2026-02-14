"""Integration tests for achievement persistence and lifecycle.

Tests cover:
- Achievement persistence across sessions
- Achievement progression (earning multiple achievements over time)
- Integration with AgentProfile updates
- Real-world scenarios with complete event streams
"""

import unittest
from datetime import datetime
from typing import List
from metrics import AgentEvent, AgentProfile, DashboardState
from achievements import (
    check_all_achievements,
    get_all_achievement_ids,
)


def create_event_stream(
    agent_name: str,
    num_events: int,
    statuses: List[str] = None,
    durations: List[float] = None,
    costs: List[float] = None,
    ticket_keys: List[str] = None,
    timestamps: List[str] = None,
) -> List[AgentEvent]:
    """Create a stream of events for integration testing."""
    events = []

    for i in range(num_events):
        status = statuses[i] if statuses and i < len(statuses) else "success"
        duration = durations[i] if durations and i < len(durations) else 60.0
        cost = costs[i] if costs and i < len(costs) else 0.01
        ticket = ticket_keys[i] if ticket_keys and i < len(ticket_keys) else f"AI-{i}"
        timestamp = timestamps[i] if timestamps and i < len(timestamps) else None

        if timestamp is None:
            now = datetime.utcnow()
            timestamp = now.isoformat() + "Z"

        event = {
            "event_id": f"event-{i}",
            "agent_name": agent_name,
            "session_id": "session-1",
            "ticket_key": ticket,
            "started_at": timestamp,
            "ended_at": timestamp,
            "duration_seconds": duration,
            "status": status,
            "input_tokens": 500,
            "output_tokens": 500,
            "total_tokens": 1000,
            "estimated_cost_usd": cost,
            "artifacts": [],
            "error_message": "" if status == "success" else "Test error",
            "model_used": "claude-sonnet-4-5",
        }
        events.append(event)

    return events


def simulate_agent_profile_update(
    profile: AgentProfile,
    event: AgentEvent,
) -> AgentProfile:
    """Simulate updating an agent profile with a new event."""
    # Update counters
    profile["total_invocations"] += 1

    if event["status"] == "success":
        profile["successful_invocations"] += 1
        profile["current_streak"] += 1
        profile["best_streak"] = max(profile["best_streak"], profile["current_streak"])
    else:
        profile["failed_invocations"] += 1
        profile["current_streak"] = 0

    profile["total_tokens"] += event["total_tokens"]
    profile["total_cost_usd"] += event["estimated_cost_usd"]
    profile["total_duration_seconds"] += event["duration_seconds"]

    # Update derived metrics
    if profile["total_invocations"] > 0:
        profile["success_rate"] = profile["successful_invocations"] / profile["total_invocations"]
        profile["avg_duration_seconds"] = profile["total_duration_seconds"] / profile["total_invocations"]
        profile["avg_tokens_per_call"] = profile["total_tokens"] / profile["total_invocations"]

    if profile["successful_invocations"] > 0:
        profile["cost_per_success_usd"] = profile["total_cost_usd"] / profile["successful_invocations"]

    profile["last_active"] = event["ended_at"]

    return profile


def create_initial_profile(agent_name: str) -> AgentProfile:
    """Create a fresh agent profile."""
    return {
        "agent_name": agent_name,
        "total_invocations": 0,
        "successful_invocations": 0,
        "failed_invocations": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "total_duration_seconds": 0.0,
        "commits_made": 0,
        "prs_created": 0,
        "prs_merged": 0,
        "files_created": 0,
        "files_modified": 0,
        "lines_added": 0,
        "lines_removed": 0,
        "tests_written": 0,
        "issues_created": 0,
        "issues_completed": 0,
        "messages_sent": 0,
        "reviews_completed": 0,
        "success_rate": 0.0,
        "avg_duration_seconds": 0.0,
        "avg_tokens_per_call": 0.0,
        "cost_per_success_usd": 0.0,
        "xp": 0,
        "level": 1,
        "current_streak": 0,
        "best_streak": 0,
        "achievements": [],
        "strengths": [],
        "weaknesses": [],
        "recent_events": [],
        "last_error": "",
        "last_active": datetime.utcnow().isoformat() + "Z",
    }


class TestAchievementProgression(unittest.TestCase):
    """Test achievement progression over an agent's lifetime."""

    def test_first_invocation_lifecycle(self):
        """Test earning first_blood on the very first invocation."""
        profile = create_initial_profile("coding")
        events = create_event_stream("coding", 1)

        # Process first event
        event = events[0]
        profile = simulate_agent_profile_update(profile, event)

        earned = check_all_achievements(profile, event, events, events)

        self.assertIn("first_blood", earned)
        self.assertEqual(len(earned), 1)  # Only first_blood

        # Add to profile
        profile["achievements"].extend(earned)

        # Process second event - should not re-earn first_blood
        events2 = create_event_stream("coding", 1)
        event2 = events2[0]
        profile = simulate_agent_profile_update(profile, event2)

        earned2 = check_all_achievements(profile, event2, events + events2, events2)

        self.assertNotIn("first_blood", earned2)

    def test_progression_to_century_club(self):
        """Test earning first_blood, then progressing to century_club."""
        profile = create_initial_profile("coding")
        all_events = []

        # First event - earn first_blood
        events1 = create_event_stream("coding", 1)
        profile = simulate_agent_profile_update(profile, events1[0])
        all_events.extend(events1)

        earned = check_all_achievements(profile, events1[0], all_events, events1)
        self.assertIn("first_blood", earned)
        profile["achievements"].extend(earned)

        # Progress through 99 more events
        for i in range(2, 101):
            events = create_event_stream("coding", 1)
            event = events[0]
            profile = simulate_agent_profile_update(profile, event)
            all_events.append(event)

            earned = check_all_achievements(profile, event, all_events, events)
            profile["achievements"].extend(earned)

        # Should now have both achievements
        self.assertIn("first_blood", profile["achievements"])
        self.assertIn("century_club", profile["achievements"])
        self.assertIn("marathon", profile["achievements"])

    def test_multiple_achievements_in_single_session(self):
        """Test earning multiple achievements in one session."""
        profile = create_initial_profile("coding")

        # Create a perfect day scenario (10 successes, all fast, different tickets)
        events = create_event_stream(
            "coding",
            10,
            statuses=["success"] * 10,
            durations=[25.0] * 10,
            costs=[0.005] * 10,
            ticket_keys=[f"AI-{i}" for i in range(10)]
        )

        for event in events:
            profile = simulate_agent_profile_update(profile, event)

        # Check achievements after the 10th event
        earned = check_all_achievements(profile, events[-1], events, events)

        # Should earn: first_blood, perfect_day, speed_demon, streak_10, polyglot
        self.assertIn("first_blood", earned)
        self.assertIn("perfect_day", earned)
        self.assertIn("speed_demon", earned)
        self.assertIn("streak_10", earned)
        self.assertIn("polyglot", earned)

    def test_comeback_kid_scenario(self):
        """Test earning comeback_kid after multiple failures."""
        profile = create_initial_profile("coding")

        # Create error sequence followed by success
        events = create_event_stream(
            "coding",
            4,
            statuses=["error", "error", "error", "success"]
        )

        for event in events:
            profile = simulate_agent_profile_update(profile, event)

        # Check achievements after the recovery
        earned = check_all_achievements(profile, events[-1], events, events)

        # Should earn: first_blood (first success) and comeback_kid
        self.assertIn("first_blood", earned)
        self.assertIn("comeback_kid", earned)

    def test_streak_progression(self):
        """Test earning streak achievements progressively."""
        profile = create_initial_profile("coding")
        all_events = []

        # Build up to streak_10
        for i in range(10):
            events = create_event_stream("coding", 1, statuses=["success"])
            event = events[0]
            profile = simulate_agent_profile_update(profile, event)
            all_events.append(event)

            earned = check_all_achievements(profile, event, all_events, events)
            profile["achievements"].extend(earned)

        # Should have streak_10 but not streak_25
        self.assertIn("streak_10", profile["achievements"])
        self.assertNotIn("streak_25", profile["achievements"])

        # Continue to streak_25
        for i in range(15):
            events = create_event_stream("coding", 1, statuses=["success"])
            event = events[0]
            profile = simulate_agent_profile_update(profile, event)
            all_events.append(event)

            earned = check_all_achievements(profile, event, all_events, events)
            profile["achievements"].extend(earned)

        # Should now have both
        self.assertIn("streak_10", profile["achievements"])
        self.assertIn("streak_25", profile["achievements"])

        # Total achievements should not duplicate streak_10
        self.assertEqual(profile["achievements"].count("streak_10"), 1)


class TestAchievementPersistence(unittest.TestCase):
    """Test that achievements persist correctly across sessions."""

    def test_achievements_persist_in_profile(self):
        """Test that earned achievements stay in the profile."""
        profile = create_initial_profile("coding")
        events = create_event_stream("coding", 1)

        # Earn first_blood
        profile = simulate_agent_profile_update(profile, events[0])
        earned = check_all_achievements(profile, events[0], events, events)
        profile["achievements"].extend(earned)

        # Verify it's in the profile
        self.assertIn("first_blood", profile["achievements"])

        # Simulate saving and loading (achievement list should persist)
        saved_achievements = profile["achievements"].copy()

        # Create new profile with saved achievements
        new_profile = create_initial_profile("coding")
        new_profile["achievements"] = saved_achievements
        new_profile["successful_invocations"] = 1
        new_profile["total_invocations"] = 1

        # Should not re-earn first_blood
        new_events = create_event_stream("coding", 1)
        new_profile = simulate_agent_profile_update(new_profile, new_events[0])
        earned2 = check_all_achievements(new_profile, new_events[0], new_events, new_events)

        self.assertNotIn("first_blood", earned2)

    def test_all_achievements_can_be_earned(self):
        """Test that all 12 achievements can theoretically be earned."""
        all_achievement_ids = get_all_achievement_ids()
        self.assertEqual(len(all_achievement_ids), 12)

        profile = create_initial_profile("coding")
        all_events = []

        # Earn first_blood
        events = create_event_stream("coding", 1)
        profile = simulate_agent_profile_update(profile, events[0])
        all_events.extend(events)
        earned = check_all_achievements(profile, events[0], all_events, events)
        profile["achievements"].extend(earned)

        # Earn century_club and marathon (100 invocations)
        for i in range(99):
            events = create_event_stream("coding", 1)
            profile = simulate_agent_profile_update(profile, events[0])
            all_events.extend(events)
            earned = check_all_achievements(profile, events[0], all_events, events)
            profile["achievements"].extend(earned)

        # Earn streak_25
        profile["current_streak"] = 25
        events = create_event_stream("coding", 1)
        earned = check_all_achievements(profile, events[0], all_events, events)
        profile["achievements"].extend(earned)

        # Earn polyglot (5 different tickets)
        polyglot_events = create_event_stream(
            "coding", 5,
            ticket_keys=["AI-1", "AI-2", "AI-3", "AI-4", "AI-5"]
        )
        all_events.extend(polyglot_events)
        earned = check_all_achievements(profile, polyglot_events[0], all_events, [])
        profile["achievements"].extend(earned)

        # Earn speed_demon
        speed_events = create_event_stream("coding", 5, durations=[25.0] * 5)
        for event in speed_events:
            profile = simulate_agent_profile_update(profile, event)
        all_events.extend(speed_events)
        earned = check_all_achievements(profile, speed_events[-1], all_events, [])
        profile["achievements"].extend(earned)

        # Earn penny_pincher (50 cheap successes)
        cheap_events = create_event_stream("coding", 50, costs=[0.005] * 50)
        for event in cheap_events:
            profile = simulate_agent_profile_update(profile, event)
        all_events.extend(cheap_events)
        earned = check_all_achievements(profile, cheap_events[-1], all_events, [])
        profile["achievements"].extend(earned)

        # Earn big_spender
        expensive_event = create_event_stream("coding", 1, costs=[1.50])[0]
        profile = simulate_agent_profile_update(profile, expensive_event)
        all_events.append(expensive_event)
        earned = check_all_achievements(profile, expensive_event, all_events, [])
        profile["achievements"].extend(earned)

        # Earn night_owl
        night_event = create_event_stream(
            "coding", 1,
            timestamps=["2026-02-14T02:00:00Z"]
        )[0]
        earned = check_all_achievements(profile, night_event, all_events, [])
        profile["achievements"].extend(earned)

        # Earn comeback_kid
        comeback_events = create_event_stream(
            "coding", 4,
            statuses=["error", "error", "error", "success"]
        )
        for event in comeback_events:
            profile = simulate_agent_profile_update(profile, event)
        all_events.extend(comeback_events)
        earned = check_all_achievements(profile, comeback_events[-1], all_events, [])
        profile["achievements"].extend(earned)

        # Earn perfect_day
        perfect_events = create_event_stream("coding", 10, statuses=["success"] * 10)
        for event in perfect_events:
            profile = simulate_agent_profile_update(profile, event)
        earned = check_all_achievements(profile, perfect_events[-1], all_events, perfect_events)
        profile["achievements"].extend(earned)

        # Remove duplicates
        unique_achievements = list(set(profile["achievements"]))

        # Should have earned all 12 achievements
        self.assertEqual(len(unique_achievements), 12)
        for achievement_id in all_achievement_ids:
            self.assertIn(achievement_id, unique_achievements)


class TestRealWorldScenarios(unittest.TestCase):
    """Test realistic agent usage scenarios."""

    def test_coding_agent_typical_session(self):
        """Simulate a typical coding agent session."""
        profile = create_initial_profile("coding")
        all_events = []

        # Session 1: 5 successful file modifications
        session1_events = create_event_stream(
            "coding", 5,
            statuses=["success"] * 5,
            durations=[45.0, 60.0, 55.0, 50.0, 48.0],
            costs=[0.015, 0.02, 0.018, 0.016, 0.014],
            ticket_keys=["AI-49"] * 5
        )

        for event in session1_events:
            profile = simulate_agent_profile_update(profile, event)
            all_events.append(event)

            earned = check_all_achievements(profile, event, all_events, session1_events)
            profile["achievements"].extend(earned)

        # Should have first_blood and streak_10 once we get there
        self.assertIn("first_blood", profile["achievements"])

        # Continue with more events to reach streak_10
        session2_events = create_event_stream(
            "coding", 5,
            statuses=["success"] * 5,
            ticket_keys=["AI-50"] * 5
        )

        for event in session2_events:
            profile = simulate_agent_profile_update(profile, event)
            all_events.append(event)

            earned = check_all_achievements(profile, event, all_events, session2_events)
            profile["achievements"].extend(earned)

        # Should have earned streak_10
        self.assertIn("streak_10", profile["achievements"])
        self.assertEqual(profile["current_streak"], 10)

    def test_agent_with_failures_and_recovery(self):
        """Simulate an agent that encounters failures and recovers."""
        profile = create_initial_profile("github")
        all_events = []

        # Start with successes
        events = create_event_stream("github", 2, statuses=["success"] * 2)
        for event in events:
            profile = simulate_agent_profile_update(profile, event)
            all_events.append(event)
            earned = check_all_achievements(profile, event, all_events, events)
            profile["achievements"].extend(earned)

        # Hit errors
        error_events = create_event_stream("github", 3, statuses=["error"] * 3)
        for event in error_events:
            profile = simulate_agent_profile_update(profile, event)
            all_events.append(event)

        # Recover with success
        recovery_event = create_event_stream("github", 1, statuses=["success"])[0]
        profile = simulate_agent_profile_update(profile, recovery_event)
        all_events.append(recovery_event)

        earned = check_all_achievements(profile, recovery_event, all_events, [recovery_event])
        profile["achievements"].extend(earned)

        # Should have comeback_kid
        self.assertIn("comeback_kid", profile["achievements"])
        self.assertEqual(profile["current_streak"], 1)  # Streak reset and restarted

    def test_high_volume_agent(self):
        """Simulate a high-volume agent reaching marathon."""
        profile = create_initial_profile("slack")
        all_events = []

        # Process 100 invocations
        for i in range(100):
            events = create_event_stream(
                "slack", 1,
                statuses=["success"],
                durations=[5.0],  # Slack is fast
                costs=[0.002],  # Slack is cheap
                ticket_keys=[f"AI-{i % 20}"]  # Reuse tickets
            )

            profile = simulate_agent_profile_update(profile, events[0])
            all_events.append(events[0])

            earned = check_all_achievements(profile, events[0], all_events, events)
            profile["achievements"].extend(earned)

        # Should have multiple achievements
        unique_achievements = list(set(profile["achievements"]))

        self.assertIn("first_blood", unique_achievements)
        self.assertIn("century_club", unique_achievements)
        self.assertIn("marathon", unique_achievements)
        self.assertIn("penny_pincher", unique_achievements)  # All events are cheap
        self.assertIn("polyglot", unique_achievements)  # 20 different tickets
        self.assertIn("streak_25", unique_achievements)  # 100 consecutive successes


if __name__ == "__main__":
    unittest.main()
