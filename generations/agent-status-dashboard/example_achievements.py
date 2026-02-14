"""Example usage of the achievement checking system.

This demonstrates how to integrate achievement checking into the
AgentMetricsCollector workflow.
"""

from datetime import datetime
from metrics import AgentEvent, AgentProfile
from achievements import (
    check_all_achievements,
    get_achievement_name,
    get_achievement_description,
    get_all_achievement_ids,
)


def create_example_profile() -> AgentProfile:
    """Create an example agent profile."""
    return {
        "agent_name": "coding",
        "total_invocations": 10,
        "successful_invocations": 9,
        "failed_invocations": 1,
        "total_tokens": 50000,
        "total_cost_usd": 0.75,
        "total_duration_seconds": 450.0,
        "commits_made": 5,
        "prs_created": 2,
        "prs_merged": 1,
        "files_created": 3,
        "files_modified": 12,
        "lines_added": 450,
        "lines_removed": 120,
        "tests_written": 8,
        "issues_created": 0,
        "issues_completed": 2,
        "messages_sent": 0,
        "reviews_completed": 0,
        "success_rate": 0.9,
        "avg_duration_seconds": 45.0,
        "avg_tokens_per_call": 5000.0,
        "cost_per_success_usd": 0.083,
        "xp": 150,
        "level": 3,
        "current_streak": 10,
        "best_streak": 10,
        "achievements": ["first_blood"],
        "strengths": ["fast_execution", "high_success_rate"],
        "weaknesses": [],
        "recent_events": [],
        "last_error": "",
        "last_active": datetime.utcnow().isoformat() + "Z",
    }


def create_example_event() -> AgentEvent:
    """Create an example agent event."""
    now = datetime.utcnow()
    return {
        "event_id": "example-event-123",
        "agent_name": "coding",
        "session_id": "session-42",
        "ticket_key": "AI-49",
        "started_at": now.isoformat() + "Z",
        "ended_at": now.isoformat() + "Z",
        "duration_seconds": 45.0,
        "status": "success",
        "input_tokens": 2500,
        "output_tokens": 2500,
        "total_tokens": 5000,
        "estimated_cost_usd": 0.075,
        "artifacts": ["file:achievements.py", "file:test_achievements.py"],
        "error_message": "",
        "model_used": "claude-sonnet-4-5",
    }


def example_basic_achievement_check():
    """Example 1: Basic achievement checking after an event."""
    print("=" * 70)
    print("Example 1: Basic Achievement Checking")
    print("=" * 70)

    profile = create_example_profile()
    current_event = create_example_event()
    all_events = [current_event]  # In reality, this would be all historical events
    session_events = [current_event]

    print(f"\nAgent: {profile['agent_name']}")
    print(f"Current Streak: {profile['current_streak']}")
    print(f"Successful Invocations: {profile['successful_invocations']}")
    print(f"Existing Achievements: {profile['achievements']}")

    # Check for new achievements
    newly_earned = check_all_achievements(
        profile,
        current_event,
        all_events,
        session_events
    )

    print(f"\nNewly Earned Achievements: {newly_earned}")

    for achievement_id in newly_earned:
        name = get_achievement_name(achievement_id)
        desc = get_achievement_description(achievement_id)
        print(f"  🏆 {name}: {desc}")


def example_achievement_progression():
    """Example 2: Achievement progression over multiple events."""
    print("\n" + "=" * 70)
    print("Example 2: Achievement Progression")
    print("=" * 70)

    profile = create_example_profile()
    profile["achievements"] = []  # Start fresh
    profile["successful_invocations"] = 0
    profile["total_invocations"] = 0
    profile["current_streak"] = 0

    print("\nSimulating agent invocations...")

    # Simulate 10 successful invocations
    all_events = []
    for i in range(10):
        event = create_example_event()
        event["event_id"] = f"event-{i}"
        all_events.append(event)

        # Update profile
        profile["total_invocations"] += 1
        profile["successful_invocations"] += 1
        profile["current_streak"] += 1

        # Check achievements
        newly_earned = check_all_achievements(
            profile,
            event,
            all_events,
            all_events
        )

        if newly_earned:
            print(f"\nAfter event {i + 1}:")
            for achievement_id in newly_earned:
                name = get_achievement_name(achievement_id)
                print(f"  🏆 Earned: {name}")
                profile["achievements"].append(achievement_id)

    print(f"\nFinal Achievement Count: {len(profile['achievements'])}")
    print(f"Achievements: {profile['achievements']}")


def example_list_all_achievements():
    """Example 3: List all available achievements."""
    print("\n" + "=" * 70)
    print("Example 3: All Available Achievements")
    print("=" * 70)

    all_ids = get_all_achievement_ids()

    print(f"\nTotal Achievements: {len(all_ids)}\n")

    for achievement_id in all_ids:
        name = get_achievement_name(achievement_id)
        desc = get_achievement_description(achievement_id)
        print(f"🏆 {name}")
        print(f"   ID: {achievement_id}")
        print(f"   Condition: {desc}")
        print()


def example_integration_with_metrics_collector():
    """Example 4: How to integrate with AgentMetricsCollector."""
    print("\n" + "=" * 70)
    print("Example 4: Integration Pattern")
    print("=" * 70)

    print("""
Integration with AgentMetricsCollector:

```python
class AgentMetricsCollector:
    def _record_event(self, event: AgentEvent):
        # ... existing code to record event ...

        # Get agent profile
        profile = self.state["agents"][event["agent_name"]]

        # Get all events for this agent
        agent_events = [
            e for e in self.state["events"]
            if e["agent_name"] == event["agent_name"]
        ]

        # Get current session events
        session_events = [
            e for e in self.state["events"]
            if e["session_id"] == event["session_id"]
        ]

        # Check for newly earned achievements
        newly_earned = check_all_achievements(
            profile,
            event,
            agent_events,
            session_events
        )

        # Add new achievements to profile
        for achievement_id in newly_earned:
            if achievement_id not in profile["achievements"]:
                profile["achievements"].append(achievement_id)

                # Optional: Log achievement
                achievement_name = get_achievement_name(achievement_id)
                print(f"🏆 {profile['agent_name']} earned: {achievement_name}")

        # Save updated state
        self._save_state()
```

Key Points:
1. Call check_all_achievements() after each event is recorded
2. Pass the complete event history for accurate checking
3. Update the profile with newly earned achievements
4. Persist the updated profile to disk
5. Never re-award achievements that are already earned
    """)


def main():
    """Run all examples."""
    example_basic_achievement_check()
    example_achievement_progression()
    example_list_all_achievements()
    example_integration_with_metrics_collector()

    print("\n" + "=" * 70)
    print("Examples Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
