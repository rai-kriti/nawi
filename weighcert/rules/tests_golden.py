"""
Golden tests for the rules engine.
Section 12.1 of NAWI_Implementation_Spec.md.
Run with:  py -3 -m pytest rules/tests_golden.py -v
"""
import sys
import os

# Allow running without Django installed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from decimal import Decimal
from rules.engine import (
    mpe_lookup, error_calc, check_compliance, repeatability_eval,
    eccentricity_required_load, validate_instrument, zero_check,
    RangeSpec, MpeLookupResult,
)

D = Decimal  # shorthand


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def r(max_g, e_g, order=1, d_g=None):
    return RangeSpec(order=order, max_g=D(str(max_g)), e_g=D(str(e_g)),
                     d_g=D(str(d_g)) if d_g else D(str(e_g)))


def single(max_g, e_g, d_g=None):
    return [r(max_g, e_g, order=1, d_g=d_g)]


# ---------------------------------------------------------------------------
# mpe table — initial / subsequent verification (multiplier 1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls,e_g,load_g,m,expected_mpe", [
    ("III", "1",    "0",       "0",    "0.5"),
    ("III", "1",    "500",     "500",  "0.5"),
    ("III", "1",    "501",     "501",  "1.0"),
    ("III", "1",    "2000",    "2000", "1.0"),
    ("III", "1",    "2001",    "2001", "1.5"),
    ("III", "1",    "10000",   "10000","1.5"),
    # class II
    ("II",  "0.1",  "500.0",   "5000", "0.05"),
    ("II",  "0.1",  "500.1",   "5001", "0.10"),
    ("II",  "0.1",  "2000.0",  "20000","0.10"),
    ("II",  "0.1",  "2000.1",  "20001","0.15"),
    # class IIII
    ("IIII","10",   "500",     "50",   "5"),
    ("IIII","10",   "510",     "51",   "10"),
    ("IIII","10",   "2010",    "201",  "15"),
    # class I
    ("I",   "0.001","50",      "50000","0.0005"),
    ("I",   "0.001","50.001",  "50001","0.001"),
    ("I",   "0.001","200.001", "200001","0.0015"),
])
def test_mpe_table(cls, e_g, load_g, m, expected_mpe):
    ranges = single(D(load_g) * 10 if D(load_g) > 0 else D("1000"), e_g)
    # Set max high enough so the load is not "above max"
    # For class I, use a large max
    if cls == "I":
        ranges = single("300", e_g)
    elif cls == "II":
        ranges = single("10000", e_g)
    elif cls == "IIII":
        ranges = single("100000", e_g)
    else:
        ranges = single("100000", "1")
    result = mpe_lookup(cls, ranges, D(load_g), multiplier=1)
    assert not result.outside_class, f"Outside class: {result.error_msg}"
    assert result.mpe == D(expected_mpe), (
        f"class={cls} e={e_g} load={load_g}: got {result.mpe}, expected {expected_mpe}"
    )


def test_mpe_outside_class_III():
    """Load 10001g on class III, e=1g must be flagged as outside class."""
    ranges = single("10001", "1")
    result = mpe_lookup("III", ranges, D("10001"), multiplier=1)
    assert result.outside_class


# ---------------------------------------------------------------------------
# Service inspection: multiplier 2
# ---------------------------------------------------------------------------

def test_service_inspection_500g():
    ranges = single("100000", "1")
    result = mpe_lookup("III", ranges, D("500"), multiplier=2)
    assert result.mpe == D("1.0")

def test_service_inspection_2001g():
    ranges = single("100000", "1")
    result = mpe_lookup("III", ranges, D("2001"), multiplier=2)
    assert result.mpe == D("3.0")


# ---------------------------------------------------------------------------
# Multi-interval: class III, 2/5/15 kg, e=1/2/10 g
# ---------------------------------------------------------------------------

def multi_interval_ranges():
    return [
        RangeSpec(order=1, max_g=D("2000"), e_g=D("1"), d_g=D("1")),
        RangeSpec(order=2, max_g=D("5000"), e_g=D("2"), d_g=D("2")),
        RangeSpec(order=3, max_g=D("15000"), e_g=D("10"), d_g=D("10")),
    ]

@pytest.mark.parametrize("load_g,expected_mpe", [
    ("500",   "0.5"),   # range 1, 0 ≤ m ≤ 500
    ("1500",  "1"),     # range 1, 500 < m ≤ 2000
    ("3000",  "2"),     # range 2, m=1500, 0 < m ≤ 2500 → actually m=3000/2=1500 ≤ 5000/2=2500 → 0.5e? No.
    ("4500",  "3"),     # range 2, m=2250 > 2500 → 1.5×2 = 3  ✓
    ("10000", "10"),    # range 3, m=1000 → ≤2000 → 1.0×10 = 10
    # Exact boundary: 2000g belongs to range 1  [spec §4.7]
    ("2000",  "1"),     # range 1, m=2000 → 1.0×1 = 1.0
    # Exact boundary: 5000g belongs to range 2
    ("5000",  "3"),     # range 2, m=2500 → 1.5×2 = 3.0
])
def test_multi_interval(load_g, expected_mpe):
    ranges = multi_interval_ranges()
    result = mpe_lookup("III", ranges, D(load_g), multiplier=1)
    assert not result.outside_class, f"Outside class at {load_g}g: {result.error_msg}"
    assert result.mpe == D(expected_mpe), (
        f"load={load_g}: got mpe={result.mpe}, expected {expected_mpe}"
    )

def test_multi_3000g_range2():
    """3000g should be in range 2 (max_2=5000), m=3000/2=1500 ≤ 2500 → 0.5×2=1g?
    Wait — Table 6 for class III: 0≤m≤500 → 0.5e, 500<m≤2000 → 1.0e, 2000<m≤10000 → 1.5e
    m=1500 ≤ 2000 → 1.0 × e2 = 1.0 × 2 = 2g. The spec example says 3000g → ±2g."""
    ranges = multi_interval_ranges()
    result = mpe_lookup("III", ranges, D("3000"), multiplier=1)
    assert result.mpe == D("2")
    assert result.range_order == 2


# ---------------------------------------------------------------------------
# Changeover error — official worked example  [4.8]
# ---------------------------------------------------------------------------

def test_changeover_official_example():
    """e=d=5g, L=1000g, I=1000g, ΔL=1.5g, E0=0.5g → Ec=+0.5g → PASS (mpe=2.5g at m=200)"""
    e = D("5")
    d = D("5")
    L = D("1000")
    I = D("1000")
    delta_L = D("1.5")
    E0 = D("0.5")

    err = error_calc(I=I, L=L, e_i=e, d=d, E0=E0, delta_L=delta_L)
    assert err.P == D("1001"), f"P={err.P}"
    assert err.E == D("1"), f"E={err.E}"
    assert err.Ec == D("0.5"), f"Ec={err.Ec}"
    assert not err.missing_delta_L

    ranges = single("100000", "5", d_g="5")
    mpe_r = mpe_lookup("III", ranges, L, multiplier=1)
    assert mpe_r.mpe == D("2.5")  # m=200, factor=0.5, e=5 → 2.5g

    comp = check_compliance(err, mpe_r)
    assert comp.passed


def test_changeover_boundary_pass():
    """Ec = +2.5g, mpe = 2.5g → exactly at limit → PASS (inclusive)"""
    e = D("5"); d = D("5"); L = D("1000"); E0 = D("0")
    # We need Ec=2.5: I + e/2 - deltaL - L - E0 = 2.5
    # 1000 + 2.5 - deltaL - 1000 - 0 = 2.5 → deltaL=0
    err = error_calc(I=D("1000"), L=D("1000"), e_i=e, d=d, E0=D("0"), delta_L=D("0"))
    assert err.Ec == D("2.5")
    ranges = single("100000", "5", d_g="5")
    mpe_r = mpe_lookup("III", ranges, L, multiplier=1)
    comp = check_compliance(err, mpe_r)
    assert comp.passed


def test_changeover_boundary_fail():
    """Ec = +2.6g, mpe = 2.5g → FAIL"""
    e = D("5"); d = D("5"); L = D("1000"); E0 = D("0")
    # Ec = I + e/2 - deltaL - L - E0 = 1000 + 2.5 - (-0.1) - 1000 = 2.6 → deltaL=-0.1
    # Actually: Ec = P - L - E0 = (I + e/2 - deltaL) - L - E0
    # To get Ec=2.6: deltaL = -0.1 (add -0.1g... that doesn't make physical sense)
    # Simpler: use large I
    # Ec = I + e/2 - deltaL - L - E0 = (I - L) + e/2 - deltaL - E0
    # I-L = 0, e/2 = 2.5, deltaL=0, E0=0 → Ec=2.5 (boundary pass)
    # To get 2.6, let I-L = 0.1 (indication=1000.1 is not on the interval though)
    # Use simple method: set d <= 0.2e (d=1g, e=5g, 1 <= 1 so d/e=0.2 → not strictly > 0.2e)
    # Let's just test with d > 0.2e and manually set:
    err = error_calc(I=D("1000"), L=D("1000"), e_i=e, d=D("5"), E0=D("-0.1"), delta_L=D("0"))
    # Ec = P - L - E0 = (1000 + 2.5 - 0) - 1000 - (-0.1) = 2.5 + 0.1 = 2.6
    assert err.Ec == D("2.6")
    ranges = single("100000", "5", d_g="5")
    mpe_r = mpe_lookup("III", ranges, L, multiplier=1)
    comp = check_compliance(err, mpe_r)
    assert not comp.passed


def test_changeover_boundary_negative_pass():
    """Ec = -2.5g → PASS (inclusive, symmetrical)"""
    e = D("5"); d = D("5")
    # Ec = P - L - E0, need Ec = -2.5
    # P = I + e/2 - deltaL = 1000 + 2.5 - 0 = 1002.5; L=1005; E0=0
    err = error_calc(I=D("1000"), L=D("1005"), e_i=e, d=d, E0=D("0"), delta_L=D("0"))
    # E = P - L = 1002.5 - 1005 = -2.5; Ec = -2.5 - 0 = -2.5
    assert err.Ec == D("-2.5")
    ranges = single("100000", "5", d_g="5")
    mpe_r = mpe_lookup("III", ranges, D("1005"), multiplier=1)
    comp = check_compliance(err, mpe_r)
    assert comp.passed


# ---------------------------------------------------------------------------
# Classification checks (Table 3)
# ---------------------------------------------------------------------------

def test_classification_valid_1():
    """class III, e=1g, Max=10kg → n=10000 → valid."""
    findings = validate_instrument("III", D("10000"), D("20"), D("1"), D("1"))
    n_findings = [f for f in findings if f.code in ("N_LOW", "N_HIGH")]
    assert not n_findings, f"Unexpected n findings: {n_findings}"

def test_classification_n_high():
    """class III, e=1g, Max=10001g → n=10001 → warning."""
    findings = validate_instrument("III", D("10001"), D("20"), D("1"), D("1"))
    assert any(f.code == "N_HIGH" for f in findings)

def test_classification_n_low():
    """class III, e=5g, Max=2000g → n=400 < 500 → warning."""
    findings = validate_instrument("III", D("2000"), D("20"), D("5"), D("5"))
    assert any(f.code == "N_LOW" for f in findings)

def test_classification_iiii_valid():
    """class IIII, e=10g, Max=10000g → n=1000 → valid."""
    findings = validate_instrument("IIII", D("10000"), D("100"), D("10"), D("10"))
    n_findings = [f for f in findings if f.code in ("N_LOW", "N_HIGH")]
    assert not n_findings


# ---------------------------------------------------------------------------
# Repeatability  [3.6.1, A.4.10]
# ---------------------------------------------------------------------------

def test_repeatability_pass():
    """errors [+0.5, 0.0, +1.0] at mpe=1.0 → spread=1.0 → PASS."""
    errors = [D("0.5"), D("0.0"), D("1.0")]
    mpe = D("1.0")
    result = repeatability_eval(errors, mpe)
    assert result.passed
    assert result.spread == D("1.0")

def test_repeatability_fail():
    """errors [+0.5, -0.5, +1.0] at mpe=1.0 → spread=1.5 → FAIL."""
    errors = [D("0.5"), D("-0.5"), D("1.0")]
    mpe = D("1.0")
    result = repeatability_eval(errors, mpe)
    assert not result.passed
    assert result.spread == D("1.5")


# ---------------------------------------------------------------------------
# Eccentricity required load  [3.6.2, A.4.7]
# ---------------------------------------------------------------------------

def test_eccentric_4_support():
    """Max=10kg, T+=0 → 1/3 × 10 = 3.333…kg"""
    load = eccentricity_required_load("up_to_4_supports", D("10000"), D("0"), 4)
    expected = D("10000") / 3
    assert load == expected

def test_eccentric_6_support():
    """6-support → 1/(6-1) × Max = 1/5 × Max"""
    load = eccentricity_required_load("more_than_4_supports", D("10000"), D("0"), 6)
    expected = D("10000") / 5
    assert load == expected

def test_eccentric_tank():
    """tank/hopper → 1/10 × Max"""
    load = eccentricity_required_load("tank_hopper", D("10000"), D("0"), 4)
    assert load == D("1000")

def test_eccentric_rolling():
    """rolling → 0.8 × Max"""
    load = eccentricity_required_load("rolling_load", D("10000"), D("0"), 4)
    assert load == D("8000")


# ---------------------------------------------------------------------------
# Utility: missing delta_L when required
# ---------------------------------------------------------------------------

def test_missing_delta_L():
    """d > 0.2e, no delta_L, simplified=False → missing_delta_L=True."""
    err = error_calc(
        I=D("100"), L=D("100"), e_i=D("5"), d=D("5"), E0=D("0"),
        delta_L=None, allow_simplified=False
    )
    assert err.missing_delta_L

def test_simplified_no_delta_L():
    """allow_simplified=True → simple method, no missing flag."""
    err = error_calc(
        I=D("100"), L=D("100"), e_i=D("5"), d=D("5"), E0=D("0"),
        delta_L=None, allow_simplified=True
    )
    assert not err.missing_delta_L
    assert err.method == "simple"

