"""Scoring and points formula."""

from psalms import count_words

MODE_MULTIPLIERS = {
    "blank": 1.0,
    "letters": 1.5,
    "recitation": 2.0,
    "study": 0.0,
}

CHUNK_MASTERY_BONUS = 50
FIRST_IN_CLASS_BONUS = 100
STREAK_PER_DAY = 10
STREAK_CAP = 70


def calculate_points(
    psalm_id: int,
    chunk_number: int,
    mode: str,
    passed: bool,
    is_chunk_mastery: bool = False,
    is_psalm_mastery: bool = False,
    streak: int = 0,
    is_first_in_class: bool = False,
    psalm_word_count: int = 0,
    chunk_word_count: int = 0,
) -> int:
    if not passed or mode == "study":
        return 0

    base = chunk_word_count
    multiplier = MODE_MULTIPLIERS.get(mode, 1.0)
    points = int(base * multiplier)

    if is_chunk_mastery:
        points += CHUNK_MASTERY_BONUS

    if is_psalm_mastery:
        points += psalm_word_count * 2  # full psalm word count × 2

    streak_bonus = min(streak * STREAK_PER_DAY, STREAK_CAP)
    points += streak_bonus

    if is_first_in_class:
        points += FIRST_IN_CLASS_BONUS

    return points
