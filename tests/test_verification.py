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


def test_insufficient_numbers_returns_zero():
    result = solve_challenge("no numbers here at all")
    assert result == "0.00"
