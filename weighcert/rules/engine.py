"""
Rules engine for WeighCert — OIML R 76-1:2006
==============================================
Pure Python, no Django imports, no database access.
All masses in Decimal grams.  All results are plain Python
objects (dataclasses / dicts).

This module is the SINGLE source of truth for every calculation.
The browser may show a preview; the server always recomputes here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Optional

# Use 28-digit precision for all calculations
getcontext().prec = 28

RULESET_VERSION = "R76-1:2006"

# ---------------------------------------------------------------------------
# Reference tables (also seeded to DB as ClassLimit / MpeBand / MultiIntervalCondition)
# ---------------------------------------------------------------------------

# Table 3 — Classification limits  [3.2, Table 3]
# Each entry: (class, e_min_g, e_max_g, n_min, n_max, min_factor, e_condition_label)
# e_min/e_max are Decimal grams; None means no bound.
# min_factor: Min >= min_factor * d  (5 for grading instruments, else as below)
CLASS_LIMITS = [
    # class I
    ("I",   Decimal("0.000001"), None,            50000, None,    100),
    # class II  — two e-bands
    ("II",  Decimal("0.000001"), Decimal("0.00005"), 100,  100000, 20),
    ("II",  Decimal("0.0001"),   None,              5000, 100000, 50),
    # class III — two e-bands
    ("III", Decimal("0.0001"),   Decimal("0.002"),  100,  10000,  20),
    ("III", Decimal("0.005"),    None,              500,  10000,  20),
    # class IIII
    ("IIII",Decimal("0.005"),    None,              100,  1000,   10),
]

# Table 6 — MPE bands  [3.5.1, Table 6]
# (class, m_upper_inclusive, factor)   m_upper=None → open-ended upper
# Boundaries are UPPER-INCLUSIVE (m=500 → 0.5e for class III)
MPE_BANDS: dict[str, list[tuple[Optional[Decimal], Decimal]]] = {
    "I":    [
        (Decimal("50000"),  Decimal("0.5")),
        (Decimal("200000"), Decimal("1.0")),
        (None,              Decimal("1.5")),
    ],
    "II":   [
        (Decimal("5000"),   Decimal("0.5")),
        (Decimal("20000"),  Decimal("1.0")),
        (Decimal("100000"), Decimal("1.5")),
    ],
    "III":  [
        (Decimal("500"),    Decimal("0.5")),
        (Decimal("2000"),   Decimal("1.0")),
        (Decimal("10000"),  Decimal("1.5")),
    ],
    "IIII": [
        (Decimal("50"),     Decimal("0.5")),
        (Decimal("200"),    Decimal("1.0")),
        (Decimal("1000"),   Decimal("1.5")),
    ],
}

# Table 4 — Multi-interval condition  [Table 4]
# Min value of Max_i / e_{i+1}
MULTI_INTERVAL_MIN: dict[str, int] = {
    "I":    50000,
    "II":   5000,
    "III":  500,
    "IIII": 50,
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RangeSpec:
    """One partial weighing range (or the only range for single-range instruments)."""
    order: int            # 1-based index
    max_g: Decimal        # Max_i in grams
    e_g:   Decimal        # e_i in grams
    d_g:   Optional[Decimal] = None   # d_i — defaults to e_i when None


@dataclass
class MpeLookupResult:
    mpe: Decimal           # absolute mpe in grams
    m: Decimal             # load in verification intervals
    e_used: Decimal        # e_i used
    factor: Decimal        # 0.5 / 1.0 / 1.5
    range_order: int       # which partial range was used
    multiplier: int        # 1 or 2
    outside_class: bool = False
    error_msg: str = ""


@dataclass
class ErrorResult:
    P: Optional[Decimal]        # indication prior to rounding (changeover)
    E: Decimal                  # error before E0 correction
    Ec: Decimal                 # corrected error
    E0_used: Decimal
    method: str                 # "changeover" or "simple"
    missing_delta_L: bool = False


@dataclass
class ComplianceResult:
    passed: bool
    Ec: Decimal
    mpe: Decimal
    abs_Ec: Decimal
    mpe_lookup: MpeLookupResult


@dataclass
class InstrumentFinding:
    code: str
    severity: str   # "error" | "warning"
    message: str
    clause: str


@dataclass
class RepeatabilityResult:
    passed: bool
    spread: Decimal
    spread_limit: Decimal
    errors: list[Decimal]
    per_reading_pass: list[bool]


@dataclass
class EccentricityLoad:
    """Required eccentricity test load for a given mode."""
    required_load_g: Decimal
    mode: str


# ---------------------------------------------------------------------------
# 7.2 mpe lookup
# ---------------------------------------------------------------------------

def mpe_lookup(
    cls: str,
    ranges: list[RangeSpec],
    load_g: Decimal,
    multiplier: int = 1,
) -> MpeLookupResult:
    """
    Return the mpe for a given load.

    For multi-interval instruments the range is chosen so that:
      - A load exactly equal to Max_i belongs to range i.
      - A load above all Max_i is flagged as out-of-range.
    """
    # Choose partial range  [3.3, 4.7]
    chosen: Optional[RangeSpec] = None
    # Sort by order just in case
    sorted_ranges = sorted(ranges, key=lambda r: r.order)

    if load_g <= Decimal("0"):
        # Zero or negative load → use range 1
        chosen = sorted_ranges[0]
    else:
        for r in sorted_ranges:
            if load_g <= r.max_g:
                chosen = r
                break
        if chosen is None:
            # Above all ranges
            last = sorted_ranges[-1]
            return MpeLookupResult(
                mpe=Decimal("0"),
                m=Decimal("0"),
                e_used=last.e_g,
                factor=Decimal("0"),
                range_order=last.order,
                multiplier=multiplier,
                outside_class=True,
                error_msg=f"Load {load_g} g exceeds Max {last.max_g} g",
            )

    e_i = chosen.e_g
    m = load_g / e_i

    bands = MPE_BANDS.get(cls)
    if bands is None:
        raise ValueError(f"Unknown accuracy class: {cls!r}")

    factor: Optional[Decimal] = None
    for upper, f in bands:
        if upper is None or m <= upper:
            factor = f
            break

    if factor is None:
        # m is above the last defined band → outside class limits
        last_upper = bands[-1][0]
        return MpeLookupResult(
            mpe=Decimal("0"),
            m=m,
            e_used=e_i,
            factor=Decimal("0"),
            range_order=chosen.order,
            multiplier=multiplier,
            outside_class=True,
            error_msg=(
                f"Load {load_g} g gives m={m} which exceeds the highest "
                f"band ({last_upper}) for class {cls}"
            ),
        )

    mpe = factor * e_i * multiplier

    return MpeLookupResult(
        mpe=mpe,
        m=m,
        e_used=e_i,
        factor=factor,
        range_order=chosen.order,
        multiplier=multiplier,
    )


# ---------------------------------------------------------------------------
# 7.3 Error calculation  [3.5.3.2, A.4.4.3]
# ---------------------------------------------------------------------------

def error_calc(
    I: Decimal,           # indication
    L: Decimal,           # applied (net) load in grams
    e_i: Decimal,         # verification scale interval for the load's range
    d: Decimal,           # actual scale interval
    E0: Decimal,          # zero error (Decimal 0 if not determined)
    delta_L: Optional[Decimal] = None,   # extra weights added (changeover)
    allow_simplified: bool = False,
    *,
    # For multi-interval: e at the range where (I + e) falls
    e_for_half_e_term: Optional[Decimal] = None,
) -> ErrorResult:
    """
    Return P, E, Ec.

    Uses changeover method when d > 0.2 * e_i.
    Falls back to simple method (E = I - L) when:
      - d <= 0.2 * e_i, OR
      - allow_simplified is True (admin setting), OR
      - delta_L is None and allow_simplified is True
    """
    threshold = Decimal("0.2") * e_i
    need_changeover = d > threshold

    if e_for_half_e_term is None:
        e_for_half_e_term = e_i

    if need_changeover and not allow_simplified:
        if delta_L is None:
            # Mark as missing but do not crash — caller handles
            # (server blocks save; browser shows required indicator)
            return ErrorResult(
                P=None,
                E=Decimal("0"),
                Ec=Decimal("0"),
                E0_used=E0,
                method="changeover",
                missing_delta_L=True,
            )
        half_e = e_for_half_e_term / 2
        P = I + half_e - delta_L
        E = P - L
        Ec = E - E0
        return ErrorResult(P=P, E=E, Ec=Ec, E0_used=E0, method="changeover")
    else:
        # Simple method: E = I - L  [3.5.3.2 when d <= 0.2e, or simplified]
        E = I - L
        Ec = E - E0
        return ErrorResult(P=None, E=E, Ec=Ec, E0_used=E0, method="simple")


def check_compliance(error_result: ErrorResult, mpe_result: MpeLookupResult) -> ComplianceResult:
    """Pass if |Ec| <= mpe (inclusive)."""
    abs_Ec = abs(error_result.Ec)
    passed = abs_Ec <= mpe_result.mpe
    return ComplianceResult(
        passed=passed,
        Ec=error_result.Ec,
        mpe=mpe_result.mpe,
        abs_Ec=abs_Ec,
        mpe_lookup=mpe_result,
    )


# ---------------------------------------------------------------------------
# 7.4 Zero check  [4.5.2, A.4.2.3]
# ---------------------------------------------------------------------------

def zero_check(
    E0: Decimal,
    e1: Decimal,           # e of range 1 (or the only range)
) -> dict:
    """Pass if |E0| <= 0.25 * e1."""
    limit = Decimal("0.25") * e1
    return {
        "passed": abs(E0) <= limit,
        "E0": E0,
        "limit": limit,
    }


def zero_range_check(
    measured_tracking_range_g: Optional[Decimal],
    measured_initial_range_g: Optional[Decimal],
    max_g: Decimal,
) -> dict:
    """
    Optional check: tracking/zero-setting range <= 4% of Max;
    initial zero-setting range <= 20% of Max.
    """
    result = {}
    if measured_tracking_range_g is not None:
        limit_4pct = Decimal("0.04") * max_g
        result["tracking_range_passed"] = measured_tracking_range_g <= limit_4pct
        result["tracking_range_limit"] = limit_4pct
    if measured_initial_range_g is not None:
        limit_20pct = Decimal("0.20") * max_g
        result["initial_range_passed"] = measured_initial_range_g <= limit_20pct
        result["initial_range_limit"] = limit_20pct
    return result


# ---------------------------------------------------------------------------
# 7.4 Repeatability  [3.6.1, A.4.10]
# ---------------------------------------------------------------------------

def repeatability_eval(
    errors: list[Decimal],
    mpe: Decimal,
) -> RepeatabilityResult:
    """
    spread = max(errors) - min(errors)
    Pass if spread <= mpe and every |error| <= mpe.
    """
    if not errors:
        return RepeatabilityResult(
            passed=False, spread=Decimal("0"),
            spread_limit=mpe, errors=[], per_reading_pass=[]
        )
    spread = max(errors) - min(errors)
    per_reading = [abs(e) <= mpe for e in errors]
    passed = spread <= mpe and all(per_reading)
    return RepeatabilityResult(
        passed=passed,
        spread=spread,
        spread_limit=mpe,
        errors=errors,
        per_reading_pass=per_reading,
    )


def required_repeatability_count(cls: str) -> int:
    """3 for III/IIII, 6 for I/II  [A.4.10]."""
    return 3 if cls in ("III", "IIII") else 6


# ---------------------------------------------------------------------------
# 7.4 Eccentricity required load  [3.6.2, A.4.7]
# ---------------------------------------------------------------------------

def eccentricity_required_load(
    mode: str,              # "up_to_4_supports" | "more_than_4_supports" | "tank_hopper" | "rolling_load"
    max_g: Decimal,
    tare_plus_g: Decimal,   # maximum additive tare effect T+
    n_supports: int = 4,    # number of support points (for more_than_4 mode)
) -> Decimal:
    """Return required eccentricity test load in grams."""
    base = max_g + tare_plus_g
    if mode == "up_to_4_supports":
        return base / 3
    elif mode == "more_than_4_supports":
        return base / (n_supports - 1)
    elif mode == "tank_hopper":
        return base / 10
    elif mode == "rolling_load":
        return Decimal("0.8") * base
    else:
        raise ValueError(f"Unknown eccentricity mode: {mode!r}")


# ---------------------------------------------------------------------------
# 7.4 Tare  [4.6.3, A.4.6.2]
# ---------------------------------------------------------------------------

def tare_setting_limit(
    e1: Decimal,
    d: Decimal,
    is_mechanical_digital: bool = False,
) -> Decimal:
    """
    0.25 e (electronic or analog)
    0.5 d  (mechanical with digital indication)
    """
    if is_mechanical_digital:
        return Decimal("0.5") * d
    return Decimal("0.25") * e1


# ---------------------------------------------------------------------------
# 7.1 Instrument validation  [3.2, 3.4, Table 3]
# ---------------------------------------------------------------------------

def validate_instrument(
    cls: str,
    max_g: Decimal,
    min_g: Decimal,
    e_g: Decimal,
    d_g: Decimal,
    ranges: Optional[list[RangeSpec]] = None,
    is_grading: bool = False,
) -> list[InstrumentFinding]:
    """
    Return list of InstrumentFinding objects (warnings only — no hard blocks).
    """
    findings: list[InstrumentFinding] = []

    # --- n check ---
    n = max_g / e_g
    cls_rows = [r for r in CLASS_LIMITS if r[0] == cls]
    # Find the row matching the e range
    matching = None
    for row in cls_rows:
        _, e_min, e_max, n_min, n_max, min_factor = row
        if e_g >= e_min and (e_max is None or e_g <= e_max):
            matching = row
            break

    if matching is None:
        findings.append(InstrumentFinding(
            code="E_RANGE",
            severity="warning",
            message=f"e={e_g} g is not in a recognised range for class {cls}.",
            clause="Table 3",
        ))
    else:
        _, e_min, e_max, n_min, n_max, min_factor = matching
        if n < n_min:
            findings.append(InstrumentFinding(
                code="N_LOW",
                severity="warning",
                message=f"n = {n} is below the minimum {n_min} for class {cls}. [Table 3]",
                clause="Table 3 / 3.2",
            ))
        if n_max is not None and n > n_max:
            findings.append(InstrumentFinding(
                code="N_HIGH",
                severity="warning",
                message=f"n = {n} exceeds the maximum {n_max} for class {cls}. [Table 3]",
                clause="Table 3 / 3.2",
            ))
        # Min check  [3.4.3]
        min_factor_eff = 5 if is_grading else min_factor
        min_limit = Decimal(str(min_factor_eff)) * d_g
        if min_g < min_limit:
            findings.append(InstrumentFinding(
                code="MIN_LOW",
                severity="warning",
                message=(
                    f"Min={min_g} g is below {min_factor_eff} × d = {min_limit} g. [3.4.3]"
                ),
                clause="3.4.3",
            ))

    # --- d / e relationship  [3.4.2] ---
    if d_g >= e_g:
        findings.append(InstrumentFinding(
            code="D_GE_E",
            severity="warning",
            message=f"d={d_g} g must be less than e={e_g} g. [3.4.2]",
            clause="3.4.2",
        ))
    if e_g > 10 * d_g:
        findings.append(InstrumentFinding(
            code="E_GT_10D",
            severity="warning",
            message=f"e={e_g} g exceeds 10 × d={d_g} g. [3.4.2]",
            clause="3.4.2",
        ))

    # --- e series check  [3.4.2 / DECISION: warning only] ---
    if not _is_valid_e_series(e_g):
        findings.append(InstrumentFinding(
            code="E_SERIES",
            severity="warning",
            message=f"e={e_g} g is not of the form 1×10^k, 2×10^k or 5×10^k. [3.4.2]",
            clause="3.4.2",
        ))

    # --- Multi-interval checks  [3.3, Table 4] ---
    if ranges and len(ranges) > 1:
        sorted_ranges = sorted(ranges, key=lambda r: r.order)
        min_cond = MULTI_INTERVAL_MIN.get(cls, 500)
        for i, r in enumerate(sorted_ranges):
            ni = r.max_g / r.e_g
            # Check n_i in Table 3 (using same logic as above)
            mi_cls_rows = [row for row in CLASS_LIMITS if row[0] == cls]
            mi_match = None
            for row in mi_cls_rows:
                _, e_min, e_max, n_min, n_max, _ = row
                if r.e_g >= e_min and (e_max is None or r.e_g <= e_max):
                    mi_match = row
                    break
            if mi_match:
                _, _, _, n_min, n_max, _ = mi_match
                if ni < n_min or (n_max and ni > n_max):
                    findings.append(InstrumentFinding(
                        code=f"RANGE{r.order}_N",
                        severity="warning",
                        message=(
                            f"Range {r.order}: n={ni} outside [{n_min},{n_max}]. [Table 3]"
                        ),
                        clause="Table 3",
                    ))
            # Table 4 condition for all but last range
            if i < len(sorted_ranges) - 1:
                e_next = sorted_ranges[i + 1].e_g
                ratio = r.max_g / e_next
                if ratio < min_cond:
                    findings.append(InstrumentFinding(
                        code=f"RANGE{r.order}_COND",
                        severity="warning",
                        message=(
                            f"Range {r.order}: Max_{r.order}/e_{r.order+1} = {ratio} "
                            f"< {min_cond}. [Table 4]"
                        ),
                        clause="Table 4",
                    ))
            # Consecutive e values must be increasing
            if i > 0 and r.e_g <= sorted_ranges[i - 1].e_g:
                findings.append(InstrumentFinding(
                    code=f"RANGE{r.order}_E_ORDER",
                    severity="warning",
                    message=f"e_{r.order} must be greater than e_{r.order-1}. [3.3]",
                    clause="3.3",
                ))

    return findings


def _is_valid_e_series(e: Decimal) -> bool:
    """Check if e is of the form 1, 2 or 5 × 10^k."""
    if e <= 0:
        return False
    # Normalise: find the magnitude
    # Divide by 10^k until 1 <= mantissa < 10
    mantissa = e
    while mantissa >= 10:
        mantissa /= 10
    while mantissa < 1:
        mantissa *= 10
    # Round to avoid floating-point weirdness in Decimal
    mantissa = mantissa.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return mantissa in (Decimal("1"), Decimal("2"), Decimal("5"))


# ---------------------------------------------------------------------------
# 7.5 Suggested loads generator  [A.4.4, 8.3.3]
# ---------------------------------------------------------------------------

def suggested_loads(
    cls: str,
    ranges: list[RangeSpec],
    min_g: Decimal,
    min_count: int = 5,
    include_min: bool = True,
) -> list[Decimal]:
    """
    Return suggested accuracy loads (grams), increasing order.
    Always includes 0 conceptually (zero covered by zero check),
    Max, and loads at / just above each mpe band boundary.
    """
    sorted_ranges = sorted(ranges, key=lambda r: r.order)
    max_g = sorted_ranges[-1].max_g
    loads: set[Decimal] = set()

    # Always include Max
    loads.add(max_g)

    # Include Min if >= 100 mg  [8.3.3]
    if include_min and min_g >= Decimal("0.1"):
        loads.add(min_g)

    # Band boundaries per range
    for r in sorted_ranges:
        e_i = r.e_g
        bands = MPE_BANDS.get(cls, [])
        for upper, _ in bands:
            if upper is None:
                continue
            boundary_load = upper * e_i  # m_upper × e
            if Decimal("0") < boundary_load <= r.max_g:
                loads.add(boundary_load)
            # Also just above: boundary + e (the first load in the next band)
            just_above = boundary_load + e_i
            if Decimal("0") < just_above <= r.max_g:
                loads.add(just_above)

    # Fill to min_count with evenly spaced values
    if max_g > 0:
        step = max_g / Decimal(str(max(min_count - 1, 1)))
        cur = step
        for _ in range(min_count * 3):
            if cur >= max_g:
                break
            loads.add(cur.quantize(sorted_ranges[0].e_g, rounding=ROUND_HALF_UP))
            cur += step

    result = sorted(loads)
    return result


# ---------------------------------------------------------------------------
# 7.6 Weight error check  [3.7.1]
# ---------------------------------------------------------------------------

def weight_error_check(
    weight_errors_g: list[Decimal],   # combined certified corrections or class tolerances
    mpe_at_load: Decimal,
) -> dict:
    """
    Total weight error must not exceed 1/3 of instrument mpe. [DECISION: warning]
    """
    total = sum(abs(e) for e in weight_errors_g)
    limit = mpe_at_load / 3
    return {
        "total_weight_error": total,
        "limit": limit,
        "passed": total <= limit,
    }


# ---------------------------------------------------------------------------
# 4.8 Changeover method: half-e term for multi-interval  [A.4.4.3 note]
# ---------------------------------------------------------------------------

def half_e_for_changeover(
    I: Decimal,
    e_i: Decimal,
    ranges: list[RangeSpec],
) -> Decimal:
    """
    For a multi-interval instrument: the ½e term uses the e of the range
    in which (I + e_i) falls.  [A.4.4.3 note]
    """
    indication_next = I + e_i
    for r in sorted(ranges, key=lambda r: r.order):
        if indication_next <= r.max_g:
            return r.e_g / 2
    # Above all ranges: use last e
    return sorted(ranges, key=lambda r: r.order)[-1].e_g / 2


# ---------------------------------------------------------------------------
# Inspection type → limit multiplier
# ---------------------------------------------------------------------------

INSPECTION_MULTIPLIERS = {
    "initial_verification":     1,
    "subsequent_verification":  1,
    "service_inspection":       2,
}


def multiplier_for_inspection(inspection_type: str) -> int:
    m = INSPECTION_MULTIPLIERS.get(inspection_type)
    if m is None:
        raise ValueError(f"Unknown inspection type: {inspection_type!r}")
    return m


# ---------------------------------------------------------------------------
# Overall session result
# ---------------------------------------------------------------------------

def overall_result(
    zero_ok: Optional[bool],
    accuracy_ok: Optional[bool],
    repeatability_ok: Optional[bool],
    eccentricity_ok: Optional[bool],
    tare_ok: Optional[bool],           # None if not applicable
    discrimination_ok: Optional[bool], # None if not applicable
    sensitivity_ok: Optional[bool],    # None if not applicable
    tilt_ok: Optional[bool],           # None if not applicable
    mandatory_complete: bool,
) -> str:
    """Return 'pass', 'fail', or 'incomplete'."""
    if not mandatory_complete:
        return "incomplete"
    mandatory = [zero_ok, accuracy_ok, repeatability_ok, eccentricity_ok]
    optional = [x for x in [tare_ok, discrimination_ok, sensitivity_ok, tilt_ok] if x is not None]
    all_checks = mandatory + optional
    if any(v is None for v in mandatory):
        return "incomplete"
    if all(v is True for v in all_checks):
        return "pass"
    return "fail"

