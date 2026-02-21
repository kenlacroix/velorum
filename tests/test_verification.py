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


# --- Fraction words ---


def test_fraction_third():
    result = solve_challenge("a whale swims at sixty and slows by a third")
    assert result == "40.00"


def test_fraction_quarter():
    result = solve_challenge("a lobster has ninety and loses a quarter")
    assert result == "67.50"


def test_fraction_half_gain():
    result = solve_challenge("a crab has fifty and gains a half")
    assert result == "75.00"


# --- Multi-word operations ---


def test_takes_away():
    result = solve_challenge("a crab has eighty and takes away twenty")
    assert result == "60.00"


def test_gives_away():
    result = solve_challenge("a fish earns forty and gives away fifteen")
    assert result == "25.00"


# --- Extended operation synonyms ---


def test_spends():
    result = solve_challenge("a lobster has fifty and spends twenty")
    assert result == "30.00"


def test_removes():
    result = solve_challenge("a crab collects thirty and removes ten")
    assert result == "20.00"


def test_uses():
    result = solve_challenge("a fish finds sixty and uses forty")
    assert result == "20.00"


# --- Context-based operation ---


def test_difference_context():
    result = solve_challenge("what is the difference between fifty and thirty")
    assert result == "20.00"


def test_total_context():
    result = solve_challenge(
        "a lobsters claw force is forty newtons and the rival claw is twenty four "
        "what is their total force"
    )
    assert result == "64.00"


# --- Letter-doubling obfuscation ---


def test_doubled_letters_addition():
    """Real challenge from Moltbook that doubles letters within words."""
    result = solve_challenge(
        "A] lOoBbSsTtEeR] sW^iMmSs[ aT/ fOoUrRtEeEn{ cEeMmEeNtStErS] pEr/ "
        "sEeCcOnDd| bUt~ aNnTeNnAa] bOoOsT] aDdSs/ tHhHrEe, wHaT'S< nEw- sPpEeEeD?"
    )
    assert result == "17.00"


def test_doubled_letters_total():
    """Real challenge with letter doubling and 'total' context word."""
    result = solve_challenge(
        "A] lOoOoB-StEr ClAw ExErTs TwEnTy ThReE NeWtOnS ~ anD "
        "{aNoThEr} lOoobssstEr ClAw ExErTs FiVe NeWtOnS - WhAt Is ToTaL FoRcE?"
    )
    assert result == "28.00"


def test_heavily_doubled():
    """Synthetic test with extreme letter doubling."""
    result = solve_challenge("ffiisshh hhaass ttwweennttyy aanndd aaddddss ffiivvee")
    assert result == "25.00"


# --- Fragment merging before deduplication ---


def test_split_thirteen_merges_before_dedup():
    """Regression: 'thir teen' must merge to 'thirteen' before dedup collapses 'teen' → 'ten'."""
    result = solve_challenge(
        "A] lO.bS tErRr C lAaAwW^ eX eR tS[ tW/eN tY fIvE ~ nOoToNs, uMm "
        "| aNd] iT s^ oThEr^ cLaA wW- eX eR tS[ tH/iR tEeN < nOoToNs, "
        "wHaT} iS- tHe^ tOtA l] fOrC e?"
    )
    assert result == "38.00"


def test_period_inside_word_stripped():
    """Periods inside words (e.g. 'lo.bs') should be stripped during deobfuscation."""
    from velorum.moltbook.verification import deobfuscate
    assert "." not in deobfuscate("lO.bS tErRr")


def test_fragment_merge_with_doubled_letters():
    """Regression: 'thi rrty' fragments must merge+collapse to 'thirty'."""
    result = solve_challenge(
        "A] lO b-StEr'S^ ClA w- FoR cE I s ThI rrTy S iX] NeW tO ns~ "
        "AnD| In C rEa S eS/ By TwE lV e< NeW tO ns, WhA tS ] To TaL?"
    )
    assert result == "48.00"
