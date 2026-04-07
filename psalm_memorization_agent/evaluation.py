"""
Typing evaluation logic.
- Ignore punctuation
- Ignore capitalization
- Allow minor typos (1-2 char edits per word)
"""

import re
import unicodedata


def normalize_word(word: str) -> str:
    """Strip punctuation and lowercase a word."""
    word = word.lower()
    word = re.sub(r"[^\w\s]", "", word, flags=re.UNICODE)
    return word.strip()


def tokenize(text: str) -> list[str]:
    """Split text into words, normalizing each."""
    words = text.split()
    return [normalize_word(w) for w in words if normalize_word(w)]


def levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            insertions = prev[j] + 1
            deletions = curr[j - 1] + 1
            substitutions = prev[j - 1] + (ca != cb)
            curr.append(min(insertions, deletions, substitutions))
        prev = curr
    return prev[len(b)]


def words_match(typed_word: str, correct_word: str) -> bool:
    """A typed word matches if edit distance <= 2 (for words longer than 3 chars)."""
    if not typed_word or not correct_word:
        return False
    if typed_word == correct_word:
        return True
    max_allowed = 0
    if len(correct_word) >= 6:
        max_allowed = 2
    elif len(correct_word) >= 4:
        max_allowed = 1
    return levenshtein(typed_word, correct_word) <= max_allowed


def evaluate(typed: str, correct: str) -> dict:
    """
    Compare typed text against correct text.
    Returns:
        score: 0.0–1.0
        matched: int (words matched)
        total: int (total correct words)
        details: list of (correct_word, typed_word_or_None, matched_bool)
    """
    correct_words = tokenize(correct)
    typed_words = tokenize(typed)
    total = len(correct_words)

    if total == 0:
        return {"score": 1.0, "matched": 0, "total": 0, "details": []}

    matched = 0
    details = []
    typed_idx = 0

    for correct_word in correct_words:
        if typed_idx < len(typed_words) and words_match(typed_words[typed_idx], correct_word):
            details.append((correct_word, typed_words[typed_idx], True))
            matched += 1
            typed_idx += 1
        else:
            # Try to find the word nearby (allow for one inserted/skipped word)
            found = False
            for lookahead in range(typed_idx, min(typed_idx + 2, len(typed_words))):
                if words_match(typed_words[lookahead], correct_word):
                    details.append((correct_word, typed_words[lookahead], True))
                    matched += 1
                    typed_idx = lookahead + 1
                    found = True
                    break
            if not found:
                typed_word = typed_words[typed_idx] if typed_idx < len(typed_words) else None
                details.append((correct_word, typed_word, False))
                if typed_idx < len(typed_words):
                    typed_idx += 1

    score = matched / total
    return {"score": score, "matched": matched, "total": total, "details": details}


# ---------------------------------------------------------------------------
# Fill-in-the-blank helpers
# ---------------------------------------------------------------------------

KEY_WORD_RATIO = 0.3  # ~30% of words are blanked


def make_blank_version(text: str) -> tuple[str, list[int]]:
    """
    Return (blanked_text, blank_indices) where blanked_text has underscores
    replacing every ~3rd word, and blank_indices is the list of 0-based word
    positions that were blanked.
    """
    words = text.split()
    blank_indices = []
    # Blank every Nth word (skip very short words and first/last word)
    step = max(2, round(1 / KEY_WORD_RATIO))
    for i in range(1, len(words) - 1, step):
        if len(words[i]) > 3:
            blank_indices.append(i)

    result = list(words)
    for idx in blank_indices:
        result[idx] = "_" * len(words[idx])
    return " ".join(result), blank_indices


def evaluate_blanks(typed_answers: list[str], correct_words: list[str]) -> dict:
    """Evaluate fill-in-the-blank answers."""
    total = len(correct_words)
    if total == 0:
        return {"score": 1.0, "matched": 0, "total": 0}
    matched = sum(
        1 for t, c in zip(typed_answers, correct_words)
        if words_match(normalize_word(t), normalize_word(c))
    )
    return {"score": matched / total, "matched": matched, "total": total}


# ---------------------------------------------------------------------------
# First-letter hint helpers
# ---------------------------------------------------------------------------

def make_first_letter_version(text: str) -> str:
    """Replace each word with just its first letter (preserving spaces)."""
    words = text.split()
    result = []
    for word in words:
        clean = re.sub(r"[^\w]", "", word)
        if clean:
            result.append(clean[0] + "_" * (len(clean) - 1))
        else:
            result.append(word)
    return " ".join(result)
