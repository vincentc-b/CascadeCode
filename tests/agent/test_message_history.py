from cascade.agent.graph_turn import run_error_message
from cascade.agent.message_history import MAX_CONTENT_CHARS, MAX_MESSAGES, MAX_ERROR_CHARS, append_recent_messages
from cascade.agent.types import RoleResult


def test_message_history_bounds_count_and_content():
    old = [{"role": "event", "content": "old"}] * MAX_MESSAGES
    recent = append_recent_messages(old, [{"role": "feature_lead", "content": "x" * (MAX_CONTENT_CHARS * 2)}])
    assert len(recent) == MAX_MESSAGES
    assert len(recent[-1]["content"]) < MAX_CONTENT_CHARS + 32
    assert len(old) == MAX_MESSAGES


def test_provider_error_does_not_echo_unbounded_prompt():
    result = RoleResult(status="error", text="x" * 100_000 + "\nMCP handshake timed out")
    message = run_error_message("feature_lead", result)
    assert len(message) < 4_100
    assert message.endswith("MCP handshake timed out")


def test_old_provider_echo_is_compacted_before_next_prompt():
    message = {"role": "feature_lead", "content": "feature_lead: turn failed — " + "x" * 30_000}
    recent = append_recent_messages([], [message])
    assert len(recent[0]["content"]) < MAX_ERROR_CHARS + 100
    assert len(message["content"]) > 30_000
