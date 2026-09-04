"""Host-side tests for the detector arithmetic (PROJECT_PLAN section 11)."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ids_model as m  # noqa: E402


def test_k_table_matches_polynomial_and_paper_points():
    tab = m.k_table()
    assert len(tab) == m.K_TABLE_MAX + 1
    for x, v in enumerate(tab):
        assert v == max(0, round(m.k_polynomial(x) * 1000))
    # Shape from Fig. 5 of the paper: k grows with the neighbour count over the
    # range the paper studied and stays in a plausible sigma-multiple range.
    assert tab[0] == 0            # clamped, polynomial is negative at 0
    assert all(tab[x] < tab[x + 1] for x in range(1, 20))
    assert 0.5 < m.k_polynomial(2) < 1.0 and 2.5 < m.k_polynomial(20) < 3.5
    assert max(tab) < 6000        # never more than 6 sigma


def test_generated_header_matches_model():
    hdr = (ROOT / "include" / "ids-k-table.h").read_text()
    body = re.sub(r"/\*.*?\*/", "", hdr.split("= {")[1].split("};")[0], flags=re.S)
    vals = [int(v) for v in re.findall(r"\d+", body)]
    assert vals == m.k_table()


def test_zero_neighbours():
    assert m.profile([]) == (0, 0, 0, m.k_x1000(0), 0)
    assert m.dio_alerts([]) == []


def test_one_neighbour_never_flagged():
    for c in (0, 1, 50, 1000):
        n, mean, sigma, k, thr = m.profile([c])
        assert sigma == 0 and thr == mean == c * 1000
        assert m.dio_alerts([c]) == []


def test_equal_counts_never_flagged():
    for c in (0, 3, 7):
        assert m.dio_alerts([c] * 6) == []


def test_single_high_outlier_among_ten_flagged():
    counts = [2, 3, 2, 3, 2, 3, 2, 3, 2, 40]
    assert m.dio_alerts(counts) == [9]
    n, mean, sigma, k, thr = m.profile(counts)
    assert mean == 6200 and k == m.k_x1000(10)
    assert 40 * 1000 > thr > 3 * 1000


def test_single_outlier_among_six_is_not_flagged():
    # Samuelson's inequality: with the population standard deviation the
    # largest possible z-score in a sample of n is sqrt(n-1). For n = 6 that
    # is 2.236, below the paper's k(6) = 2.276, so a lone outlier can never
    # exceed mean + k*sigma no matter how large it is.
    for outlier in (40, 400, 4000):
        assert m.dio_alerts([2, 3, 2, 3, 2, outlier]) == []


def test_single_outlier_detectability_bound():
    # The extreme case (all other neighbours identical) reaches z = sqrt(n-1)
    # exactly, so the detector flags a lone attacker iff sqrt(n-1) > k(n).
    # This documents which neighbourhood sizes can detect a single attacker.
    import math
    expected_detectable = {n for n in range(2, 41) if math.sqrt(n - 1) > m.k_x1000(n) / 1000}
    got = {n for n in range(2, 41) if m.dio_alerts([3] * (n - 1) + [3000]) == [n - 1]}
    assert got == expected_detectable
    # Blind spots: k(n) exceeds sqrt(n-1) at 5-7 neighbours and again at
    # 28-32 where the quartic peaks (k(32) = 5.66 > sqrt(31) = 5.57).
    assert {5, 6, 7, 28, 29, 30, 31, 32} & got == set()
    assert {2, 3, 4, 8, 10, 15, 20, 25, 35, 40} <= got


def test_small_spread_edge():
    counts = [1, 1, 1, 2]
    n, mean, sigma, k, thr = m.profile(counts)
    assert mean == 1250
    assert m.dio_alerts(counts) == ([3] if 2000 > thr else [])


def test_dis_threshold_boundaries():
    assert m.dis_alerts([3, 3, 0], 3) == []          # exactly at threshold: normal
    assert m.dis_alerts([4, 3, 0], 3) == [0]         # one above: attacker
    assert m.dis_alerts([2, 2], 2) == []
    assert m.dis_alerts([3, 2], 2) == [0]


def test_arithmetic_stays_in_32_bits_for_attack_rates():
    # Aggressive attacker: 1 DIO/s for a 5-minute window, 40 neighbours.
    counts = [300] + [4] * 39
    n, mean, sigma, k, thr = m.profile(counts)
    assert n * sum(c * c for c in counts) < 2**32
    assert (sum(counts) * 1000) < 2**32
    assert m.dio_alerts(counts) == [0]


def test_isqrt_exact():
    for v in (0, 1, 2, 3, 4, 99, 100, 10**12, 2**40 + 7):
        r = m.isqrt(v)
        assert r * r <= v < (r + 1) * (r + 1)
