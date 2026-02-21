"""Math challenge solver for Moltbook content verification.

Moltbook uses obfuscated word-problem math challenges as anti-spam.
The challenge text has random punctuation, mixed case, and special
characters injected between letters.

Example raw:   "A] lO^bSt-Er S[wImS aT/ tW,eNtY, sL|oWs b!Y fI;vE"
Deobfuscated:  "a lobster swims at twenty slows by five"
Answer:        15.00
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Word-to-number mapping
WORD_NUMBERS: dict[str, float] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}

# Fraction words — "a third" = 1/3, "a quarter" = 1/4, etc.
_FRACTIONS: dict[str, float] = {
    "half": 0.5,
    "third": 1.0 / 3.0,
    "quarter": 0.25,
    "fourth": 0.25,
    "fifth": 0.2,
    "sixth": 1.0 / 6.0,
    "seventh": 1.0 / 7.0,
    "eighth": 0.125,
    "ninth": 1.0 / 9.0,
    "tenth": 0.1,
}

# Per-word operation lookup (maps word → operation name)
_OP_LOOKUP: dict[str, str] = {}
for _w in ("adds", "add", "added", "plus", "gains", "gained",
           "increases", "increased", "grows", "grew", "speeds", "sped",
           "earns", "earned", "receives", "received", "collects", "collected",
           "finds", "found", "gets", "got", "rises", "rose",
           "climbs", "climbed", "jumps", "jumped", "accelerates", "accelerated"):
    _OP_LOOKUP[_w] = "add"
for _w in ("subtracts", "subtract", "subtracted", "minus",
           "loses", "lost", "decreases", "decreased",
           "slows", "slowed", "drops", "dropped",
           "spends", "spent", "removes", "removed",
           "uses", "used", "consumes", "consumed",
           "gives", "gave", "falls", "fell",
           "shrinks", "shrunk", "reduces", "reduced",
           "decelerates", "decelerated", "surrenders", "surrendered",
           "donates", "donated", "discards", "discarded",
           "eats", "ate", "burns", "burned", "burnt"):
    _OP_LOOKUP[_w] = "subtract"
for _w in ("multiplies", "multiplied", "multiply", "times", "product"):
    _OP_LOOKUP[_w] = "multiply"
for _w in ("divides", "divided", "divide", "splits", "split"):
    _OP_LOOKUP[_w] = "divide"

# Two-word operation phrases (checked before single-word ops)
_TWO_WORD_OPS: dict[str, str] = {
    "takes away": "subtract",
    "took away": "subtract",
    "gives away": "subtract",
    "gave away": "subtract",
    "goes up": "add",
    "went up": "add",
    "goes down": "subtract",
    "went down": "subtract",
    "picks up": "add",
    "picked up": "add",
    "puts down": "subtract",
    "put down": "subtract",
    "cut by": "subtract",
    "less than": "subtract",
}

# Single-word context hints that imply an operation between two numbers
# when no explicit operation word is present. Applied to the question
# at the end of the challenge to override the "add" fallback.
_CONTEXT_OPS: dict[str, str] = {
    "difference": "subtract",
    "total": "add",
    "combined": "add",
    "sum": "add",
    "together": "add",
    "remaining": "subtract",
}

# Implicit operation + operand (no separate number follows)
_IMPLICIT_OPS: dict[str, tuple[str, float]] = {
    "doubles": ("multiply", 2),
    "doubled": ("multiply", 2),
    "triples": ("multiply", 3),
    "tripled": ("multiply", 3),
    "quadruples": ("multiply", 4),
    "quadrupled": ("multiply", 4),
    "halves": ("divide", 2),
    "halved": ("divide", 2),
}

# Words to skip during parsing (prepositions, articles, connectors)
_SKIP_WORDS = frozenset({
    "a", "an", "the", "at", "by", "to", "of", "and", "then", "with",
    "its", "it", "is", "was", "has", "had", "more", "from", "for",
})


def _collapse_runs(s: str) -> str:
    """Collapse consecutive duplicate characters to one: 'thhhree' → 'thre'."""
    return re.sub(r"(.)\1+", r"\1", s)


# Build a reverse lookup: collapsed form → original known word.
# Used to recover words garbled by letter-doubling obfuscation.
_COLLAPSED_LOOKUP: dict[str, str] = {}
for _word in (
    list(WORD_NUMBERS)
    + list(_OP_LOOKUP)
    + list(_IMPLICIT_OPS)
    + list(_FRACTIONS)
    + list(_CONTEXT_OPS)
):
    _key = _collapse_runs(_word)
    # First registered word wins (avoids overwriting by synonyms)
    if _key not in _COLLAPSED_LOOKUP:
        _COLLAPSED_LOOKUP[_key] = _word


def deobfuscate(text: str) -> str:
    """Strip obfuscation characters from Moltbook challenge text.

    The obfuscation inserts random non-letter chars between and around
    letters, and mixes case. We strip everything except letters, digits,
    spaces, and periods, then normalize whitespace and lowercase.
    """
    # Keep only letters, digits, whitespace, and decimal points
    cleaned = re.sub(r"[^a-zA-Z0-9\s.]", "", text)
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.lower()


def _deduplicate_words(text: str) -> str:
    """Recover words garbled by letter-doubling obfuscation.

    Moltbook sometimes doubles or triples each letter in a word:
    "lOoBbSsTtEeR" → "loobbsstteer" → should be "lobster".

    For each token, collapse consecutive duplicate characters and check
    if the collapsed form matches a known word (number, operation, etc.).
    If so, replace with the canonical word.
    """
    words = text.split()
    result: list[str] = []
    for word in words:
        collapsed = _collapse_runs(word)
        canonical = _COLLAPSED_LOOKUP.get(collapsed)
        if canonical:
            result.append(canonical)
        else:
            result.append(word)
    return " ".join(result)


def _merge_fragments(text: str) -> str:
    """Rejoin word fragments split by obfuscation.

    Obfuscation can split a word like "twenty" into "twen ty" by inserting
    a space (after stripping special chars). Try merging adjacent tokens
    to reconstruct known number and operation words.
    """
    all_known = (
        set(WORD_NUMBERS)
        | set(_OP_LOOKUP)
        | set(_IMPLICIT_OPS)
        | set(_FRACTIONS)
    )
    words = text.split()
    merged: list[str] = []
    i = 0
    while i < len(words):
        # Try merging 3, then 2 adjacent tokens
        found = False
        for span in (3, 2):
            if i + span <= len(words):
                candidate = "".join(words[i : i + span])
                if candidate in all_known:
                    merged.append(candidate)
                    i += span
                    found = True
                    break
        if not found:
            merged.append(words[i])
            i += 1
    return " ".join(merged)


def _detect_context_op(text: str) -> str | None:
    """Scan the full text for context words that hint at the operation.

    Returns an operation name if a context word is found, else None.
    Used as a smarter fallback than always defaulting to "add".
    """
    for word, op in _CONTEXT_OPS.items():
        if word in text:
            return op
    return None


def _parse_expression(text: str) -> tuple[list[float], list[str]]:
    """Parse cleaned text into a sequence of numbers and operations.

    Walks through words left-to-right, extracting numbers (digit or word
    form, including compounds like "twenty three") and operations in the
    order they appear.

    Returns (numbers, operations) where len(operations) == len(numbers) - 1.
    """
    words = text.split()
    numbers: list[float] = []
    operations: list[str] = []
    pending_op: str | None = None
    context_op = _detect_context_op(text)
    fallback_op = context_op or "add"
    i = 0

    while i < len(words):
        word = words[i].strip(".,!?;:")

        # Implicit operation with built-in operand (doubles, halves, etc.)
        if word in _IMPLICIT_OPS:
            op, implicit_val = _IMPLICIT_OPS[word]
            if numbers:
                operations.append(op)
                numbers.append(implicit_val)
            i += 1
            pending_op = None
            continue

        # Two-word operation phrases ("takes away", "gives away", etc.)
        if i + 1 < len(words):
            two_word = f"{word} {words[i + 1].strip('.,!?;:')}"
            if two_word in _TWO_WORD_OPS:
                pending_op = _TWO_WORD_OPS[two_word]
                i += 2
                continue

        # Single-word operation
        if word in _OP_LOOKUP:
            pending_op = _OP_LOOKUP[word]
            i += 1
            continue

        # Fraction word: "a third", "a quarter", etc.
        # When preceded by a pending subtract/divide op, apply as fraction
        if word in _FRACTIONS:
            frac_val = _FRACTIONS[word]
            if numbers and pending_op:
                # "loses a third" = multiply by fraction
                # "slows by a third" = subtract (current * fraction)
                # The intent is: result = current - current * fraction
                # But we model it as: multiply by (1 - fraction) for subtract,
                # or multiply by fraction for other ops
                if pending_op == "subtract":
                    # "loses a third" means lose 1/3 of current value
                    operations.append("multiply")
                    numbers.append(1.0 - frac_val)
                elif pending_op == "divide":
                    operations.append("multiply")
                    numbers.append(frac_val)
                elif pending_op == "add":
                    # "gains a third" means gain 1/3 of current value
                    operations.append("multiply")
                    numbers.append(1.0 + frac_val)
                else:
                    operations.append(pending_op)
                    numbers.append(frac_val)
            elif numbers:
                # No pending op — use context fallback
                if fallback_op == "subtract":
                    operations.append("multiply")
                    numbers.append(1.0 - frac_val)
                else:
                    operations.append("multiply")
                    numbers.append(1.0 + frac_val)
            pending_op = None
            i += 1
            continue

        # Digit number
        digit_match = re.match(r"\d+(?:\.\d+)?$", word)
        if digit_match:
            value = float(digit_match.group())
            if numbers and pending_op:
                operations.append(pending_op)
            elif numbers:
                operations.append(fallback_op)
            numbers.append(value)
            pending_op = None
            i += 1
            continue

        # Word number (with compound look-ahead)
        if word in WORD_NUMBERS:
            value = WORD_NUMBERS[word]
            j = i + 1
            while j < len(words):
                next_word = words[j].strip(".,!?;:")
                if next_word in WORD_NUMBERS:
                    next_val = WORD_NUMBERS[next_word]
                    if next_val == 100 or next_val == 1000:
                        # "three hundred" = 300
                        value *= next_val
                    elif next_val < value and value >= 20:
                        # "twenty three" = 23
                        value += next_val
                    else:
                        break
                    j += 1
                else:
                    break
            if numbers and pending_op:
                operations.append(pending_op)
            elif numbers:
                operations.append(fallback_op)
            numbers.append(value)
            pending_op = None
            i = j
            continue

        # Skip noise words, move on
        i += 1

    return numbers, operations


def solve_challenge(challenge: str) -> str | None:
    """Solve an obfuscated math challenge and return the answer as a 2-decimal string.

    Steps:
    1. Deobfuscate the challenge text (strip junk chars, normalize)
    2. Parse numbers and operations sequentially
    3. Evaluate left-to-right
    4. Format to 2 decimal places

    Returns the answer formatted to 2 decimal places (e.g., "15.00"),
    or None if the challenge could not be parsed. Callers MUST check
    for None and skip submission — submitting a wrong answer counts
    toward the 10-strike ban.
    """
    logger.info("Raw challenge: %r", challenge)

    cleaned = deobfuscate(challenge)
    cleaned = _deduplicate_words(cleaned)
    cleaned = _merge_fragments(cleaned)
    logger.info("Deobfuscated: %r", cleaned)

    numbers, operations = _parse_expression(cleaned)
    logger.debug("Parsed: numbers=%s, operations=%s", numbers, operations)

    if len(numbers) < 2:
        logger.error(
            "CANNOT SOLVE — not enough numbers in challenge: %r (cleaned: %r, found: %s)",
            challenge,
            cleaned,
            numbers,
        )
        return None

    if len(operations) != len(numbers) - 1:
        logger.error(
            "CANNOT SOLVE — mismatched operations: %d numbers, %d ops (cleaned: %r)",
            len(numbers),
            len(operations),
            cleaned,
        )
        return None

    # Evaluate left-to-right
    result = numbers[0]
    for j, op in enumerate(operations):
        n = numbers[j + 1]
        if op == "add":
            result += n
        elif op == "subtract":
            result -= n
        elif op == "multiply":
            result *= n
        elif op == "divide":
            if n == 0:
                logger.error("CANNOT SOLVE — division by zero in challenge: %r", challenge)
                return None
            result /= n
        else:
            result += n  # fallback

    answer = f"{result:.2f}"
    logger.info(
        "Solved: %s = %s (steps: %s)",
        " → ".join(
            f"{numbers[0]}"
            if k == 0
            else f"{operations[k-1]} {numbers[k]}"
            for k in range(len(numbers))
        ),
        answer,
        len(operations),
    )
    return answer
