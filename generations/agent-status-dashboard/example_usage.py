"""Example usage of AgentMetricsCollector.

This demonstrates how to use the collector to track agent delegations
in a typical workflow.
"""

from pathlib import Path
from agent_metrics_collector import AgentMetricsCollector

# Initialize collector
collector = AgentMetricsCollector(
    project_name="my-project",
    metrics_dir=Path(".")
)

# Start a session
session_id = collector.start_session(session_type="initializer")

# Track a coding agent delegation
print("Tracking coding agent...")
with collector.track_agent(
    agent_name="coding",
    ticket_key="AI-46",
    model_used="claude-sonnet-4-5",
    session_id=session_id
) as tracker:
    # Simulate work...
    # Agent writes some code

    # Record tokens used
    tracker.add_tokens(input_tokens=2000, output_tokens=3000)

    # Record artifacts created
    tracker.add_artifact("file:created:agent_metrics_collector.py")
    tracker.add_artifact("file:created:test_agent_metrics_collector.py")

print("Coding agent completed successfully!")

# Track a github agent delegation
print("\nTracking github agent...")
with collector.track_agent(
    agent_name="github",
    ticket_key="AI-46",
    model_used="claude-haiku-4-5",
    session_id=session_id
) as tracker:
    # Agent creates a commit and PR
    tracker.add_tokens(input_tokens=500, output_tokens=500)
    tracker.add_artifact("commit:abc123")
    tracker.add_artifact("pr:created:#46")

print("Github agent completed successfully!")

# Track an agent that fails
print("\nTracking agent with error...")
try:
    with collector.track_agent(
        agent_name="linear",
        ticket_key="AI-46",
        model_used="claude-sonnet-4-5",
        session_id=session_id
    ) as tracker:
        tracker.add_tokens(input_tokens=100, output_tokens=50)
        raise ValueError("Simulated error")
except ValueError:
    print("Linear agent failed (error recorded)")

# End the session
collector.end_session(session_id, status="complete")

# Get the current state
state = collector.get_state()

print("\n" + "=" * 60)
print("FINAL STATE")
print("=" * 60)
print(f"Total sessions: {state['total_sessions']}")
print(f"Total events: {len(state['events'])}")
print(f"Total tokens: {state['total_tokens']}")
print(f"Total cost: ${state['total_cost_usd']:.4f}")

print("\nAgent Profiles:")
for agent_name, profile in state['agents'].items():
    print(f"  {agent_name}:")
    print(f"    - Invocations: {profile['total_invocations']}")
    print(f"    - Success rate: {profile['success_rate']:.1%}")
    print(f"    - Total tokens: {profile['total_tokens']}")
    print(f"    - Total cost: ${profile['total_cost_usd']:.4f}")

print("\nSession Summary:")
session = state['sessions'][0]
print(f"  Session ID: {session['session_id'][:8]}...")
print(f"  Agents invoked: {', '.join(session['agents_invoked'])}")
print(f"  Total tokens: {session['total_tokens']}")
print(f"  Total cost: ${session['total_cost_usd']:.4f}")
print(f"  Status: {session['status']}")
