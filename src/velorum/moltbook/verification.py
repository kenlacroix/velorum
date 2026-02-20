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

# Per-word operation lookup (maps word → operation name)
_OP_LOOKUP: dict[str, str] = {}
for _w in ("adds", "add", "added", "plus", "gains", "gained",
           "increases", "increased", "grows", "grew", "speeds", "sped"):
    _OP_LOOKUP[_w] = "add"
for _w in ("subtracts", "subtract", "subtracted", "minus",
           "loses", "lost", "decreases", "decreased",
           "slows", "slowed", "drops", "dropped"):
    _OP_LOOKUP[_w] = "subtract"
for _w in ("multiplies", "multiplied", "multiply", "times", "product"):
    _OP_LOOKUP[_w] = "multiply"
for _w in ("divides", "divided", "divide", "splits", "split"):
    _OP_LOOKUP[_w] = "divide"

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


def _merge_fragments(text: str) -> str:
    """Rejoin word fragments split by obfuscation.

    Obfuscation can split a word like "twenty" into "twen ty" by inserting
    a space (after stripping special chars). Try merging adjacent tokens
    to reconstruct known number and operation words.
    """
    all_known = set(WORD_NUMBERS) | set(_OP_LOOKUP) | set(_IMPLICIT_OPS)
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

        # Operation word
        if word in _OP_LOOKUP:
            pending_op = _OP_LOOKUP[word]
            i += 1
            continue

        # Digit number
        digit_match = re.match(r"\d+(?:\.\d+)?$", word)
        if digit_match:
            value = float(digit_match.group())
            if numbers and pending_op:
                operations.append(pending_op)
            elif numbers:
                operations.append("add")  # fallback
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
                operations.append("add")  # fallback
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
