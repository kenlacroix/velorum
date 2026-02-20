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

# Operation keywords
ADD_WORDS = {"adds", "add", "plus", "gains", "increases", "grows", "speeds"}
SUB_WORDS = {"subtracts", "subtract", "minus", "loses", "decreases", "slows", "drops"}
MUL_WORDS = {"multiplies", "multiply", "times", "doubles", "triples", "product"}
DIV_WORDS = {"divides", "divide", "halves", "splits"}


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
    to reconstruct known number words.
    """
    words = text.split()
    merged: list[str] = []
    i = 0
    while i < len(words):
        # Try merging 3, then 2 adjacent tokens
        found = False
        for span in (3, 2):
            if i + span <= len(words):
                candidate = "".join(words[i : i + span])
                if candidate in WORD_NUMBERS:
                    merged.append(candidate)
                    i += span
                    found = True
                    break
        if not found:
            merged.append(words[i])
            i += 1
    return " ".join(merged)


def _extract_numbers(text: str) -> list[float]:
    """Extract all numbers (word or digit form) from cleaned text.

    Handles compound numbers like "twenty three" (23), "one hundred" (100),
    "three hundred fifty" (350), etc.
    """
    numbers: list[float] = []
    # Digit numbers (including decimals)
    for match in re.finditer(r"\b\d+(?:\.\d+)?\b", text):
        numbers.append(float(match.group()))

    # Word numbers — handle compound forms (e.g., "twenty three" = 23)
    words = text.lower().split()
    i = 0
    while i < len(words):
        word = words[i].strip(".,!?;:")
        if word in WORD_NUMBERS:
            value = WORD_NUMBERS[word]
            # Look ahead to build compound numbers
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
            numbers.append(value)
            i = j
        else:
            i += 1
    return numbers


def _detect_operation(text: str) -> str:
    """Detect the math operation from the challenge text."""
    lower = text.lower()
    words = set(lower.split())
    if words & SUB_WORDS or "slows" in lower or "minus" in lower or "drops" in lower:
        return "subtract"
    if words & MUL_WORDS or "times" in lower or "multiplied" in lower:
        return "multiply"
    if words & DIV_WORDS or "divided" in lower or "halves" in lower:
        return "divide"
    if words & ADD_WORDS or "adds" in lower or "plus" in lower:
        return "add"
    return "add"  # default fallback


def solve_challenge(challenge: str) -> str | None:
    """Solve an obfuscated math challenge and return the answer as a 2-decimal string.

    Steps:
    1. Deobfuscate the challenge text (strip junk chars, normalize)
    2. Extract numbers (word form or digit form)
    3. Detect the math operation
    4. Compute and format to 2 decimal places

    Returns the answer formatted to 2 decimal places (e.g., "15.00"),
    or None if the challenge could not be parsed. Callers MUST check
    for None and skip submission — submitting a wrong answer counts
    toward the 10-strike ban.
    """
    logger.info("Raw challenge: %r", challenge)

    cleaned = deobfuscate(challenge)
    cleaned = _merge_fragments(cleaned)
    logger.info("Deobfuscated: %r", cleaned)

    numbers = _extract_numbers(cleaned)
    if len(numbers) < 2:
        logger.error(
            "CANNOT SOLVE — not enough numbers in challenge: %r (cleaned: %r)",
            challenge,
            cleaned,
        )
        return None

    a, b = numbers[0], numbers[1]
    op = _detect_operation(cleaned)

    if op == "divide" and b == 0:
        logger.error("CANNOT SOLVE — division by zero in challenge: %r", challenge)
        return None

    if op == "add":
        result = a + b
    elif op == "subtract":
        result = a - b
    elif op == "multiply":
        result = a * b
    elif op == "divide":
        result = a / b
    else:
        result = a + b

    answer = f"{result:.2f}"
    logger.info("Solved: %s %s %s = %s", a, op, b, answer)
    return answer
