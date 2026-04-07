"""
Claude API integration for per-attempt feedback on failed attempts.
Uses claude-haiku-4-5-20251001 for cost efficiency.
"""

import os
import anthropic

_client = None
_cached_system_prompt = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


SYSTEM_PROMPT = """You are a warm, encouraging Sunday School teacher helping 7th graders memorize Psalms from the Bible (NKJV). Your feedback is:
- Short: 1–3 sentences only
- Age-appropriate for 12–13 year olds
- Specific and actionable (point out exactly where they struggled)
- Encouraging and faith-aware (briefly reference the meaning or beauty of the text when relevant)
- Never harsh or discouraging

You help students understand what they got wrong and give a practical tip for the next try."""


def get_feedback(
    correct_text: str,
    typed_text: str,
    mode: str,
    recent_attempts: list[dict],
    psalm_title: str,
) -> str:
    """
    Call Claude to generate feedback for a failed attempt.
    Returns a single short message (1–3 sentences).
    Falls back to a generic message on any error.
    """
    client = _get_client()

    recent_summary = ""
    if recent_attempts:
        lines = []
        for a in recent_attempts[-3:]:
            lines.append(f"- Score: {a['score']:.0%}, passed: {a['passed']}")
        recent_summary = "\nRecent attempts:\n" + "\n".join(lines)

    mode_label = {
        "blank": "fill in the blank",
        "letters": "first letter hints",
        "recitation": "full recitation",
    }.get(mode, mode)

    user_message = (
        f"Psalm: {psalm_title}\n"
        f"Mode: {mode_label}\n\n"
        f"Correct text:\n{correct_text}\n\n"
        f"Student typed:\n{typed_text}\n"
        f"{recent_summary}\n\n"
        "Give the student 1–3 sentences of specific, encouraging feedback."
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception:
        return "Keep going — you're making progress! Read through the passage one more time and try again."
