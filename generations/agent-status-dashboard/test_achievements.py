"""Comprehensive tests for achievement detection system.

Tests cover:
- All 12 achievement triggers with multiple scenarios
- Edge cases: boundary conditions, already earned, missing data
- Integration with AgentProfile and AgentEvent types
- Achievement metadata functions (names, descriptions)
"""

import unittest
from datetime import datetime, timedelta
from metrics import AgentEvent, AgentProfile
from achievements import (
    check_first_blood,
    check_century_club,
    check_perfect_day,
    check_speed_demon,
    check_comeback_kid,
    check_big_spender,
    check_penny_pincher,
    check_marathon,
    check_polyglot,
    check_night_owl,
    check_streak_10,
    check_streak_25,
    check_all_achievements,
    get_achievement_name,
    get_achievement_description,
    get_all_achievement_ids,
)


def create_test_event(
    agent_name: str = "coding",
    status: str = "success",
    duration_seconds: float = 60.0,
    cost_usd: float = 0.01,
    ticket_key: str = "AI-49",
    started_at: str = None,
) -> AgentEvent:
    """Helper to create test events."""
    if started_at is None:
        now = datetime.utcnow()
        started_at = now.isoformat() + "Z"

    return {
        "event_id": f"test-event-{datetime.utcnow().timestamp()}",
        "agent_name": agent_name,
        "session_id": "test-session",
        "ticket_key": ticket_key,
        "started_at": started_at,
        "ended_at": (datetime.utcnow() + timedelta(seconds=duration_seconds)).isoformat() + "Z",
        "duration_seconds": duration_seconds,
        "status": status,
        "input_tokens": 500,
        "output_tokens": 500,
        "total_tokens": 1000,
        "estimated_cost_usd": cost_usd,
        "artifacts": [],
        "error_message": "" if status == "success" else "Test error",
        "model_used": "claude-sonnet-4-5",
    }


def create_test_profile(
    agent_name: str = "coding",
    successful_invocations: int = 0,
    total_invocations: int = 0,
    current_streak: int = 0,
    achievements: list = None,
) -> AgentProfile:
    """Helper to create test agent profiles."""
    if achievements is None:
        achievements = []

    return {
        "agent_name": agent_name,
        "total_invocations": total_invocations,
        "successful_invocations": successful_invocations,
        "failed_invocations": total_invocations - successful_invocations,
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
        "current_streak": current_streak,
        "best_streak": 0,
        "achievements": achievements,
        "strengths": [],
        "weaknesses": [],
        "recent_events": [],
        "last_error": "",
        "last_active": datetime.utcnow().isoformat() + "Z",
    }


class TestFirstBlood(unittest.TestCase):
    """Tests for first_blood achievement."""

    def test_first_success_earns_achievement(self):
        """First successful invocation earns first_blood."""
        profile = create_test_profile(successful_invocations=1)
        self.assertTrue(check_first_blood(profile))

    def test_zero_successes_no_achievement(self):
        """Zero successful invocations does not earn first_blood."""
        profile = create_test_profile(successful_invocations=0)
        self.assertFalse(check_first_blood(profile))

    def test_already_earned_no_duplicate(self):
        """Already having first_blood prevents duplicate award."""
        profile = create_test_profile(
            successful_invocations=5,
            achievements=["first_blood"]
        )
        self.assertFalse(check_first_blood(profile))

    def test_multiple_successes_earns_if_not_earned(self):
        """Multiple successes earn first_blood if not already earned."""
        profile = create_test_profile(successful_invocations=10)
        self.assertTrue(check_first_blood(profile))


class TestCenturyClub(unittest.TestCase):
    """Tests for century_club achievement."""

    def test_exactly_100_successes(self):
        """Exactly 100 successful invocations earns century_club."""
        profile = create_test_profile(successful_invocations=100)
        self.assertTrue(check_century_club(profile))

    def test_over_100_successes(self):
        """Over 100 successful invocations earns century_club."""
        profile = create_test_profile(successful_invocations=150)
        self.assertTrue(check_century_club(profile))

    def test_99_successes_no_achievement(self):
        """99 successful invocations does not earn century_club."""
        profile = create_test_profile(successful_invocations=99)
        self.assertFalse(check_century_club(profile))

    def test_already_earned_no_duplicate(self):
        """Already having century_club prevents duplicate award."""
        profile = create_test_profile(
            successful_invocations=100,
            achievements=["century_club"]
        )
        self.assertFalse(check_century_club(profile))


class TestPerfectDay(unittest.TestCase):
    """Tests for perfect_day achievement."""

    def test_10_successes_in_session(self):
        """10 successful invocations in one session earns perfect_day."""
        events = [create_test_event("coding", "success") for _ in range(10)]
        profile = create_test_profile()
        self.assertTrue(check_perfect_day(events, "coding", profile))

    def test_more_than_10_successes(self):
        """More than 10 successful invocations earns perfect_day."""
        events = [create_test_event("coding", "success") for _ in range(15)]
        profile = create_test_profile()
        self.assertTrue(check_perfect_day(events, "coding", profile))

    def test_9_successes_no_achievement(self):
        """9 successful invocations does not earn perfect_day."""
        events = [create_test_event("coding", "success") for _ in range(9)]
        profile = create_test_profile()
        self.assertFalse(check_perfect_day(events, "coding", profile))

    def test_10_invocations_with_error(self):
        """10 invocations with any error does not earn perfect_day."""
        events = [create_test_event("coding", "success") for _ in range(9)]
        events.append(create_test_event("coding", "error"))
        profile = create_test_profile()
        self.assertFalse(check_perfect_day(events, "coding", profile))

    def test_already_earned_no_duplicate(self):
        """Already having perfect_day prevents duplicate award."""
        events = [create_test_event("coding", "success") for _ in range(10)]
        profile = create_test_profile(achievements=["perfect_day"])
        self.assertFalse(check_perfect_day(events, "coding", profile))

    def test_filters_by_agent_name(self):
        """Only counts events for the specified agent."""
        events = [create_test_event("coding", "success") for _ in range(5)]
        events.extend([create_test_event("github", "success") for _ in range(5)])
        profile = create_test_profile()
        self.assertFalse(check_perfect_day(events, "coding", profile))


class TestSpeedDemon(unittest.TestCase):
    """Tests for speed_demon achievement."""

    def test_5_fast_successes(self):
        """5 consecutive completions under 30s earns speed_demon."""
        events = [create_test_event(duration_seconds=25.0) for _ in range(5)]
        profile = create_test_profile()
        self.assertTrue(check_speed_demon(events, profile))

    def test_exactly_30_seconds_no_achievement(self):
        """Events at exactly 30s do not earn speed_demon."""
        events = [create_test_event(duration_seconds=30.0) for _ in range(5)]
        profile = create_test_profile()
        self.assertFalse(check_speed_demon(events, profile))

    def test_4_fast_successes_not_enough(self):
        """Only 4 fast completions does not earn speed_demon."""
        events = [create_test_event(duration_seconds=25.0) for _ in range(4)]
        profile = create_test_profile()
        self.assertFalse(check_speed_demon(events, profile))

    def test_one_slow_breaks_streak(self):
        """One slow completion in last 5 prevents achievement."""
        events = [create_test_event(duration_seconds=25.0) for _ in range(4)]
        events.append(create_test_event(duration_seconds=35.0))
        profile = create_test_profile()
        self.assertFalse(check_speed_demon(events, profile))

    def test_error_breaks_streak(self):
        """Error in last 5 prevents achievement."""
        events = [create_test_event(duration_seconds=25.0) for _ in range(4)]
        events.append(create_test_event(status="error", duration_seconds=25.0))
        profile = create_test_profile()
        self.assertFalse(check_speed_demon(events, profile))

    def test_already_earned_no_duplicate(self):
        """Already having speed_demon prevents duplicate award."""
        events = [create_test_event(duration_seconds=25.0) for _ in range(5)]
        profile = create_test_profile(achievements=["speed_demon"])
        self.assertFalse(check_speed_demon(events, profile))

    def test_checks_only_last_5(self):
        """Only the last 5 events are checked."""
        events = [create_test_event(duration_seconds=50.0) for _ in range(5)]
        events.extend([create_test_event(duration_seconds=25.0) for _ in range(5)])
        profile = create_test_profile()
        self.assertTrue(check_speed_demon(events, profile))


class TestComebackKid(unittest.TestCase):
    """Tests for comeback_kid achievement."""

    def test_success_after_3_errors(self):
        """Success immediately after 3 consecutive errors earns comeback_kid."""
        events = [
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="success"),
        ]
        profile = create_test_profile()
        self.assertTrue(check_comeback_kid(events, profile))

    def test_success_after_more_than_3_errors(self):
        """Success after 4+ consecutive errors earns comeback_kid."""
        events = [
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="success"),
        ]
        profile = create_test_profile()
        self.assertTrue(check_comeback_kid(events, profile))

    def test_success_after_2_errors_not_enough(self):
        """Success after only 2 errors does not earn comeback_kid."""
        events = [
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="success"),
        ]
        profile = create_test_profile()
        self.assertFalse(check_comeback_kid(events, profile))

    def test_timeout_counts_as_error(self):
        """Timeout status counts toward error streak."""
        events = [
            create_test_event(status="timeout"),
            create_test_event(status="error"),
            create_test_event(status="blocked"),
            create_test_event(status="success"),
        ]
        profile = create_test_profile()
        self.assertTrue(check_comeback_kid(events, profile))

    def test_last_event_must_be_success(self):
        """Last event must be success to earn comeback_kid."""
        events = [
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="error"),
        ]
        profile = create_test_profile()
        self.assertFalse(check_comeback_kid(events, profile))

    def test_already_earned_no_duplicate(self):
        """Already having comeback_kid prevents duplicate award."""
        events = [
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="success"),
        ]
        profile = create_test_profile(achievements=["comeback_kid"])
        self.assertFalse(check_comeback_kid(events, profile))

    def test_success_in_middle_breaks_streak(self):
        """Success in the middle breaks the error streak."""
        events = [
            create_test_event(status="error"),
            create_test_event(status="success"),
            create_test_event(status="error"),
            create_test_event(status="error"),
            create_test_event(status="success"),
        ]
        profile = create_test_profile()
        self.assertFalse(check_comeback_kid(events, profile))


class TestBigSpender(unittest.TestCase):
    """Tests for big_spender achievement."""

    def test_cost_over_1_dollar(self):
        """Single invocation over $1.00 earns big_spender."""
        event = create_test_event(cost_usd=1.50)
        profile = create_test_profile()
        self.assertTrue(check_big_spender(event, profile))

    def test_exactly_1_dollar_no_achievement(self):
        """Exactly $1.00 does not earn big_spender."""
        event = create_test_event(cost_usd=1.00)
        profile = create_test_profile()
        self.assertFalse(check_big_spender(event, profile))

    def test_under_1_dollar_no_achievement(self):
        """Under $1.00 does not earn big_spender."""
        event = create_test_event(cost_usd=0.99)
        profile = create_test_profile()
        self.assertFalse(check_big_spender(event, profile))

    def test_already_earned_no_duplicate(self):
        """Already having big_spender prevents duplicate award."""
        event = create_test_event(cost_usd=2.00)
        profile = create_test_profile(achievements=["big_spender"])
        self.assertFalse(check_big_spender(event, profile))


class TestPennyPincher(unittest.TestCase):
    """Tests for penny_pincher achievement."""

    def test_50_cheap_successes(self):
        """50+ successes under $0.01 earns penny_pincher."""
        events = [create_test_event(cost_usd=0.005) for _ in range(50)]
        profile = create_test_profile()
        self.assertTrue(check_penny_pincher(events, profile))

    def test_more_than_50_cheap_successes(self):
        """More than 50 cheap successes earns penny_pincher."""
        events = [create_test_event(cost_usd=0.009) for _ in range(60)]
        profile = create_test_profile()
        self.assertTrue(check_penny_pincher(events, profile))

    def test_49_cheap_successes_not_enough(self):
        """49 cheap successes does not earn penny_pincher."""
        events = [create_test_event(cost_usd=0.005) for _ in range(49)]
        profile = create_test_profile()
        self.assertFalse(check_penny_pincher(events, profile))

    def test_exactly_1_cent_no_achievement(self):
        """Events at exactly $0.01 do not count."""
        events = [create_test_event(cost_usd=0.01) for _ in range(50)]
        profile = create_test_profile()
        self.assertFalse(check_penny_pincher(events, profile))

    def test_only_counts_successes(self):
        """Only successful events count toward penny_pincher."""
        events = [create_test_event(status="success", cost_usd=0.005) for _ in range(25)]
        events.extend([create_test_event(status="error", cost_usd=0.005) for _ in range(25)])
        profile = create_test_profile()
        self.assertFalse(check_penny_pincher(events, profile))

    def test_already_earned_no_duplicate(self):
        """Already having penny_pincher prevents duplicate award."""
        events = [create_test_event(cost_usd=0.005) for _ in range(50)]
        profile = create_test_profile(achievements=["penny_pincher"])
        self.assertFalse(check_penny_pincher(events, profile))

    def test_mixed_costs_counts_only_cheap(self):
        """Only counts events under $0.01."""
        events = [create_test_event(cost_usd=0.005) for _ in range(30)]
        events.extend([create_test_event(cost_usd=0.05) for _ in range(30)])
        profile = create_test_profile()
        self.assertFalse(check_penny_pincher(events, profile))


class TestMarathon(unittest.TestCase):
    """Tests for marathon achievement."""

    def test_100_total_invocations(self):
        """100+ total invocations earns marathon."""
        profile = create_test_profile(total_invocations=100)
        self.assertTrue(check_marathon(profile))

    def test_more_than_100_invocations(self):
        """More than 100 invocations earns marathon."""
        profile = create_test_profile(total_invocations=150)
        self.assertTrue(check_marathon(profile))

    def test_99_invocations_not_enough(self):
        """99 invocations does not earn marathon."""
        profile = create_test_profile(total_invocations=99)
        self.assertFalse(check_marathon(profile))

    def test_already_earned_no_duplicate(self):
        """Already having marathon prevents duplicate award."""
        profile = create_test_profile(
            total_invocations=100,
            achievements=["marathon"]
        )
        self.assertFalse(check_marathon(profile))


class TestPolyglot(unittest.TestCase):
    """Tests for polyglot achievement."""

    def test_5_different_tickets(self):
        """Agent used across 5+ different tickets earns polyglot."""
        events = [create_test_event(ticket_key=f"AI-{i}") for i in range(5)]
        profile = create_test_profile()
        self.assertTrue(check_polyglot(events, profile))

    def test_more_than_5_tickets(self):
        """More than 5 different tickets earns polyglot."""
        events = [create_test_event(ticket_key=f"AI-{i}") for i in range(10)]
        profile = create_test_profile()
        self.assertTrue(check_polyglot(events, profile))

    def test_4_tickets_not_enough(self):
        """Only 4 different tickets does not earn polyglot."""
        events = [create_test_event(ticket_key=f"AI-{i}") for i in range(4)]
        profile = create_test_profile()
        self.assertFalse(check_polyglot(events, profile))

    def test_duplicate_tickets_not_counted(self):
        """Duplicate ticket keys are only counted once."""
        events = []
        for _ in range(10):
            events.append(create_test_event(ticket_key="AI-1"))
            events.append(create_test_event(ticket_key="AI-2"))
        profile = create_test_profile()
        self.assertFalse(check_polyglot(events, profile))

    def test_empty_tickets_ignored(self):
        """Empty ticket keys are ignored."""
        events = [create_test_event(ticket_key=f"AI-{i}") for i in range(3)]
        events.extend([create_test_event(ticket_key="") for _ in range(10)])
        profile = create_test_profile()
        self.assertFalse(check_polyglot(events, profile))

    def test_already_earned_no_duplicate(self):
        """Already having polyglot prevents duplicate award."""
        events = [create_test_event(ticket_key=f"AI-{i}") for i in range(5)]
        profile = create_test_profile(achievements=["polyglot"])
        self.assertFalse(check_polyglot(events, profile))


class TestNightOwl(unittest.TestCase):
    """Tests for night_owl achievement."""

    def test_midnight_hour(self):
        """Invocation at midnight earns night_owl."""
        event = create_test_event(started_at="2026-02-14T00:30:00Z")
        profile = create_test_profile()
        self.assertTrue(check_night_owl(event, profile))

    def test_early_morning_hours(self):
        """Invocation between 00:00-05:00 earns night_owl."""
        for hour in range(0, 5):
            event = create_test_event(started_at=f"2026-02-14T{hour:02d}:30:00Z")
            profile = create_test_profile()
            self.assertTrue(check_night_owl(event, profile), f"Failed for hour {hour}")

    def test_5am_no_achievement(self):
        """Invocation at 05:00 does not earn night_owl."""
        event = create_test_event(started_at="2026-02-14T05:00:00Z")
        profile = create_test_profile()
        self.assertFalse(check_night_owl(event, profile))

    def test_daytime_hours_no_achievement(self):
        """Invocation during daytime does not earn night_owl."""
        for hour in range(6, 24):
            event = create_test_event(started_at=f"2026-02-14T{hour:02d}:30:00Z")
            profile = create_test_profile()
            self.assertFalse(check_night_owl(event, profile), f"Failed for hour {hour}")

    def test_already_earned_no_duplicate(self):
        """Already having night_owl prevents duplicate award."""
        event = create_test_event(started_at="2026-02-14T02:00:00Z")
        profile = create_test_profile(achievements=["night_owl"])
        self.assertFalse(check_night_owl(event, profile))

    def test_invalid_timestamp_no_achievement(self):
        """Invalid timestamp does not earn night_owl."""
        event = create_test_event(started_at="invalid-timestamp")
        profile = create_test_profile()
        self.assertFalse(check_night_owl(event, profile))


class TestStreak10(unittest.TestCase):
    """Tests for streak_10 achievement."""

    def test_exactly_10_streak(self):
        """Exactly 10 consecutive successes earns streak_10."""
        profile = create_test_profile(current_streak=10)
        self.assertTrue(check_streak_10(profile))

    def test_more_than_10_streak(self):
        """More than 10 consecutive successes earns streak_10."""
        profile = create_test_profile(current_streak=15)
        self.assertTrue(check_streak_10(profile))

    def test_9_streak_not_enough(self):
        """9 consecutive successes does not earn streak_10."""
        profile = create_test_profile(current_streak=9)
        self.assertFalse(check_streak_10(profile))

    def test_already_earned_no_duplicate(self):
        """Already having streak_10 prevents duplicate award."""
        profile = create_test_profile(
            current_streak=10,
            achievements=["streak_10"]
        )
        self.assertFalse(check_streak_10(profile))


class TestStreak25(unittest.TestCase):
    """Tests for streak_25 achievement."""

    def test_exactly_25_streak(self):
        """Exactly 25 consecutive successes earns streak_25."""
        profile = create_test_profile(current_streak=25)
        self.assertTrue(check_streak_25(profile))

    def test_more_than_25_streak(self):
        """More than 25 consecutive successes earns streak_25."""
        profile = create_test_profile(current_streak=30)
        self.assertTrue(check_streak_25(profile))

    def test_24_streak_not_enough(self):
        """24 consecutive successes does not earn streak_25."""
        profile = create_test_profile(current_streak=24)
        self.assertFalse(check_streak_25(profile))

    def test_already_earned_no_duplicate(self):
        """Already having streak_25 prevents duplicate award."""
        profile = create_test_profile(
            current_streak=25,
            achievements=["streak_25"]
        )
        self.assertFalse(check_streak_25(profile))


class TestCheckAllAchievements(unittest.TestCase):
    """Tests for check_all_achievements integration function."""

    def test_first_invocation_earns_first_blood(self):
        """First successful invocation earns first_blood."""
        profile = create_test_profile(
            agent_name="coding",
            successful_invocations=1,
            total_invocations=1,
            current_streak=1
        )
        event = create_test_event()

        earned = check_all_achievements(profile, event, [event], [event])
        self.assertIn("first_blood", earned)

    def test_multiple_achievements_at_once(self):
        """Can earn multiple achievements in one call."""
        profile = create_test_profile(
            agent_name="coding",
            successful_invocations=100,
            total_invocations=100,
            current_streak=10
        )
        event = create_test_event(cost_usd=0.005)
        events = [create_test_event(cost_usd=0.005) for _ in range(100)]

        earned = check_all_achievements(profile, event, events, events)

        # Should earn first_blood, century_club, marathon, streak_10
        self.assertIn("first_blood", earned)
        self.assertIn("century_club", earned)
        self.assertIn("marathon", earned)
        self.assertIn("streak_10", earned)

    def test_no_achievements_earned(self):
        """Returns empty list when no achievements are earned."""
        profile = create_test_profile(
            agent_name="coding",
            successful_invocations=0,
            total_invocations=1,
            current_streak=0
        )
        event = create_test_event(status="error")

        earned = check_all_achievements(profile, event, [event], [event])
        self.assertEqual(earned, [])

    def test_does_not_return_already_earned(self):
        """Does not return achievements that are already earned."""
        profile = create_test_profile(
            agent_name="coding",
            successful_invocations=1,
            total_invocations=1,
            current_streak=1,
            achievements=["first_blood"]
        )
        event = create_test_event()

        earned = check_all_achievements(profile, event, [event], [event])
        self.assertNotIn("first_blood", earned)


class TestAchievementMetadata(unittest.TestCase):
    """Tests for achievement metadata functions."""

    def test_get_all_achievement_ids(self):
        """get_all_achievement_ids returns all 12 achievements."""
        ids = get_all_achievement_ids()
        self.assertEqual(len(ids), 12)

        expected_ids = [
            "first_blood", "century_club", "perfect_day", "speed_demon",
            "comeback_kid", "big_spender", "penny_pincher", "marathon",
            "polyglot", "night_owl", "streak_10", "streak_25"
        ]
        for expected_id in expected_ids:
            self.assertIn(expected_id, ids)

    def test_get_achievement_name_valid_ids(self):
        """get_achievement_name returns correct names for all achievements."""
        test_cases = [
            ("first_blood", "First Blood"),
            ("century_club", "Century Club"),
            ("perfect_day", "Perfect Day"),
            ("speed_demon", "Speed Demon"),
            ("comeback_kid", "Comeback Kid"),
            ("big_spender", "Big Spender"),
            ("penny_pincher", "Penny Pincher"),
            ("marathon", "Marathon Runner"),
            ("polyglot", "Polyglot"),
            ("night_owl", "Night Owl"),
            ("streak_10", "On Fire"),
            ("streak_25", "Unstoppable"),
        ]

        for achievement_id, expected_name in test_cases:
            self.assertEqual(get_achievement_name(achievement_id), expected_name)

    def test_get_achievement_name_invalid_id(self):
        """get_achievement_name raises ValueError for unknown ID."""
        with self.assertRaises(ValueError) as context:
            get_achievement_name("unknown_achievement")
        self.assertIn("Unknown achievement ID", str(context.exception))

    def test_get_achievement_description_valid_ids(self):
        """get_achievement_description returns correct descriptions."""
        test_cases = [
            ("first_blood", "First successful invocation"),
            ("century_club", "100 successful invocations"),
            ("perfect_day", "10+ invocations in one session, 0 errors"),
            ("speed_demon", "5 consecutive completions under 30s"),
            ("comeback_kid", "Success immediately after 3+ consecutive errors"),
            ("big_spender", "Single invocation over $1.00"),
            ("penny_pincher", "50+ successes at < $0.01 each"),
            ("marathon", "100+ invocations in a single project"),
            ("polyglot", "Agent used across 5+ different ticket types"),
            ("night_owl", "Invocation between 00:00-05:00 local time"),
            ("streak_10", "10 consecutive successes"),
            ("streak_25", "25 consecutive successes"),
        ]

        for achievement_id, expected_desc in test_cases:
            self.assertEqual(get_achievement_description(achievement_id), expected_desc)

    def test_get_achievement_description_invalid_id(self):
        """get_achievement_description raises ValueError for unknown ID."""
        with self.assertRaises(ValueError) as context:
            get_achievement_description("unknown_achievement")
        self.assertIn("Unknown achievement ID", str(context.exception))


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_empty_events_list(self):
        """Handle empty events list gracefully."""
        profile = create_test_profile()

        # These should not crash with empty lists
        self.assertFalse(check_speed_demon([], profile))
        self.assertFalse(check_comeback_kid([], profile))
        self.assertFalse(check_penny_pincher([], profile))
        self.assertFalse(check_polyglot([], profile))

    def test_single_event_in_list(self):
        """Handle single event in list."""
        events = [create_test_event()]
        profile = create_test_profile()

        # Most achievements requiring multiple events should be False
        self.assertFalse(check_speed_demon(events, profile))
        self.assertFalse(check_comeback_kid(events, profile))

    def test_boundary_values_duration(self):
        """Test boundary values for duration-based achievements."""
        # Exactly 30 seconds should not earn speed_demon
        events = [create_test_event(duration_seconds=30.0) for _ in range(5)]
        profile = create_test_profile()
        self.assertFalse(check_speed_demon(events, profile))

        # 29.99 seconds should earn speed_demon
        events = [create_test_event(duration_seconds=29.99) for _ in range(5)]
        self.assertTrue(check_speed_demon(events, profile))

    def test_boundary_values_cost(self):
        """Test boundary values for cost-based achievements."""
        # Exactly $1.00 should not earn big_spender
        event = create_test_event(cost_usd=1.00)
        profile = create_test_profile()
        self.assertFalse(check_big_spender(event, profile))

        # $1.01 should earn big_spender
        event = create_test_event(cost_usd=1.01)
        self.assertTrue(check_big_spender(event, profile))

        # Exactly $0.01 should not count for penny_pincher
        events = [create_test_event(cost_usd=0.01) for _ in range(50)]
        profile = create_test_profile()
        self.assertFalse(check_penny_pincher(events, profile))


if __name__ == "__main__":
    unittest.main()
