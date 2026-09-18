#!/usr/bin/env python3
"""Bit-exact Python twin of the detector arithmetic in firmware/ids.c."""
import math

K_TABLE_MAX = 40          # table index is min(neighbours, K_TABLE_MAX)
SCALE = 1000              # fixed-point scale used on the mote


def k_polynomial(x):
    """Paper eq. (2): k as a function of the number of neighbours x."""
    return -5e-5 * x**4 + 0.0037 * x**3 - 0.0899 * x**2 + 0.9281 * x - 0.7903


def k_table():
    """k * 1000, rounded, clamped at 0 (the polynomial is negative at x=0 and
    beyond x~44; a negative k would flag anything above the mean)."""
    return [max(0, round(k_polynomial(x) * SCALE)) for x in range(K_TABLE_MAX + 1)]


def k_x1000(n_neighbours, table=None):
    table = table or k_table()
    return table[min(n_neighbours, K_TABLE_MAX)]


def isqrt(n):
    return math.isqrt(n)


def profile(dio_counts):
    """Return (n, mean_x1000, sigma_x1000, k_x1000, threshold_x1000) exactly as
    ids.c computes them at the end of a window."""
    n = len(dio_counts)
    if n == 0:
        return 0, 0, 0, k_x1000(0), 0
    s = sum(dio_counts)
    sq = sum(c * c for c in dio_counts)
    mean = (s * SCALE) // n
    num = n * sq - s * s                      # n^2 * variance, non-negative
    sigma = isqrt(num * SCALE * SCALE) // n   # sqrt(var) * 1000
    k = k_x1000(n)
    thr = mean + (k * sigma) // SCALE
    return n, mean, sigma, k, thr


def dio_alerts(dio_counts):
    """Indices of neighbours whose DIO count exceeds the dynamic threshold."""
    _, _, _, _, thr = profile(dio_counts)
    return [i for i, c in enumerate(dio_counts) if c * SCALE > thr]


def dis_alerts(dis_counts, dis_threshold=3):
    return [i for i, c in enumerate(dis_counts) if c > dis_threshold]
