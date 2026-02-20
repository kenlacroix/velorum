"""Tests for the Moltbook math challenge solver."""

from velorum.moltbook.verification import solve_challenge


def test_subtraction_word_problem():
    result = solve_challenge("lobster swims at twenty, slows by five")
    assert result == "15.00"


def test_addition_word_problem():
    result = solve_challenge("crab starts at ten, adds three more")
    assert result == "13.00"


def test_multiplication_word_problem():
    result = solve_challenge("fish has four, times two")
    assert result == "8.00"


def test_division_word_problem():
    result = solve_challenge("whale has sixty, divides by three")
    assert result == "20.00"


def test_numeric_digits():
    result = solve_challenge("start at 25, subtract 10")
    assert result == "15.00"


def test_insufficient_numbers_returns_none():
    result = solve_challenge("no numbers here at all")
    assert result is None


def test_obfuscated_subtraction():
    result = solve_challenge("A] lO^bSt-Er S[wImS aT/ tW,eNtY, sL|oWs b!Y fI;vE")
    assert result == "15.00"


def test_obfuscated_addition():
    result = solve_challenge("cR^aB c-rA|wLs aT tEn, sP!eEdS bY fIfTeEn")
    assert result == "25.00"


def test_division_by_zero_returns_none():
    result = solve_challenge("fish has ten, divides by zero")
    assert result is None


# --- Multi-step challenges ---


def test_three_step_add_subtract():
    result = solve_challenge("lobster starts at twenty, adds five, loses three")
    assert result == "22.00"


def test_three_step_mixed_ops():
    result = solve_challenge("crab has ten, adds five, times two")
    assert result == "30.00"


def test_four_numbers():
    result = solve_challenge("fish starts at thirty, subtract ten, add five, subtract three")
    assert result == "22.00"


# --- Implicit multipliers ---


def test_doubles():
    result = solve_challenge("fish starts at fifteen, doubles")
    assert result == "30.00"


def test_halves():
    result = solve_challenge("whale has forty, halves")
    assert result == "20.00"


def test_triples():
    result = solve_challenge("crab has ten, triples")
    assert result == "30.00"


def test_doubles_then_subtract():
    result = solve_challenge("fish starts at ten, doubles, loses five")
    assert result == "15.00"


# --- Obfuscated multi-step ---


def test_obfuscated_multi_step():
    result = solve_challenge("cR^aB s|tA,rTs aT tEn, a!dDs fI;vE, sL|oWs b!Y tH;rEe")
    assert result == "12.00"
