"""Bound the conversational state copied into every planning checkpoint.

The queue and chat stores retain the durable history. Graph messages are only
the recent context passed to the next model turn.
"""

MAX_MESSAGES = 64
MAX_CONTENT_CHARS = 32_000
MAX_ERROR_CHARS = 4_000


def append_recent_messages(current: list[dict], update: list[dict]) -> list[dict]:
    recent = (current + update)[-MAX_MESSAGES:]
    result = []
    for message in recent:
        content = message.get("content")
        if isinstance(content, str):
            if ": turn failed — " in content[:80] and len(content) > MAX_ERROR_CHARS:
                content = content[:100] + "\n[older provider output omitted]\n" + content[-(MAX_ERROR_CHARS - 140):]
            elif len(content) > MAX_CONTENT_CHARS:
                content = content[:MAX_CONTENT_CHARS] + "\n[truncated]"
            if content != message.get("content"):
                message = {**message, "content": content}
        result.append(message)
    return result
