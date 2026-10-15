#!/usr/bin/env python3
"""
PHM-Lite: Deterministic physics plausibility checker (offline subset).

Three-time-calibrated rules from common physical law:
  - Dimensional / unit consistency
  - Universal speed limit (c)
  - Absolute temperature floor (0 K)
  - Non-negativity of mass / length / energy
  - Probability range [0, 1]
  - Kinematic relations (free-fall family, tolerance-checked)
  - Conservation checks (energy / momentum, tolerance-checked)

Design guarantees:
  - Deterministic: same input -> same output, always reproducible.
  - Zero dependencies (pure standard library), Python >= 3.8.
  - Verdicts: PASS / WARN / FAIL with structured violation records.

NOTE: This is the OFFLINE SUBSET of the PHM physical-judgment engine.
It intentionally excludes proprietary core methods; deployment-specific
deep checks are exposed via a configurable remote engine endpoint.
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple

__version__ = "1.0.0"
ENGINE_ID = "PHM-Lite"
DETERMINISTIC = True

# --- Physical constants (SI) ---
C_LIGHT = 299_792_458.0          # m/s, exact
ABSOLUTE_ZERO_C = -273.15        # degC
G_EARTH = 9.80665                # m/s^2, standard gravity

# Sanity thresholds for WARN (orders of magnitude, engineering judgment)
WARN_ACC_G = 100.0               # sustained >100 g is suspicious outside impact events
WARN_SPEED_FRAC = 0.5            # >0.5 c is suspicious for macroscopic objects


class Violation:
    __slots__ = ("rule", "severity", "detail", "location")

    def __init__(self, rule: str, severity: str, detail: str, location: str = ""):
        self.rule = rule
        self.severity = severity  # "FAIL" | "WARN"
        self.detail = detail
        self.location = location

    def to_dict(self) -> Dict[str, str]:
        return {"rule": self.rule, "severity": self.severity,
                "detail": self.detail, "location": self.location}


def _verdict(violations: List[Violation]) -> str:
    if any(v.severity == "FAIL" for v in violations):
        return "FAIL"
    if any(v.severity == "WARN" for v in violations):
        return "WARN"
    return "PASS"


# ---------------------------------------------------------------- units ---

# unit -> (dimension, to_si_factor, si_offset_for_temperature)
_UNIT_TABLE = {
    # length
    "m": ("L", 1.0, 0.0), "km": ("L", 1000.0, 0.0), "cm": ("L", 0.01, 0.0),
    "mm": ("L", 0.001, 0.0), "mile": ("L", 1609.344, 0.0),
    "ft": ("L", 0.3048, 0.0), "au": ("L", 1.495978707e11, 0.0),
    "ly": ("L", 9.4607e15, 0.0),
    # time
    "s": ("T", 1.0, 0.0), "ms": ("T", 0.001, 0.0), "min": ("T", 60.0, 0.0),
    "h": ("T", 3600.0, 0.0), "hour": ("T", 3600.0, 0.0),
    "day": ("T", 86400.0, 0.0), "yr": ("T", 3.15576e7, 0.0),
    # mass
    "kg": ("M", 1.0, 0.0), "g": ("M", 0.001, 0.0), "mg": ("M", 1e-6, 0.0),
    "t": ("M", 1000.0, 0.0), "ton": ("M", 1000.0, 0.0),
    "lb": ("M", 0.45359237, 0.0),
    # speed
    "m/s": ("L/T", 1.0, 0.0), "km/h": ("L/T", 1.0 / 3.6, 0.0),
    "km/s": ("L/T", 1000.0, 0.0), "mph": ("L/T", 0.44704, 0.0),
    "knot": ("L/T", 0.514444, 0.0), "kn": ("L/T", 0.514444, 0.0),
    "c": ("L/T", C_LIGHT, 0.0),
    # acceleration
    "m/s2": ("L/T2", 1.0, 0.0), "m/s^2": ("L/T2", 1.0, 0.0),
    "g0": ("L/T2", G_EARTH, 0.0), "gal": ("L/T2", 0.01, 0.0),
    # force / energy / power
    "N": ("M*L/T2", 1.0, 0.0), "kN": ("M*L/T2", 1000.0, 0.0),
    "J": ("M*L2/T2", 1.0, 0.0), "kJ": ("M*L2/T2", 1000.0, 0.0),
    "MJ": ("M*L2/T2", 1e6, 0.0), "Wh": ("M*L2/T2", 3600.0, 0.0),
    "kWh": ("M*L2/T2", 3.6e6, 0.0), "eV": ("M*L2/T2", 1.602176634e-19, 0.0),
    "MeV": ("M*L2/T2", 1.602176634e-13, 0.0),
    "GeV": ("M*L2/T2", 1.602176634e-10, 0.0),
    "W": ("M*L2/T3", 1.0, 0.0), "kW": ("M*L2/T3", 1000.0, 0.0),
    "MW": ("M*L2/T3", 1e6, 0.0), "GW": ("M*L2/T3", 1e9, 0.0),
    "hp": ("M*L2/T3", 745.69987158227, 0.0),
    # temperature (special: offset conversions)
    "K": ("THETA", 1.0, 0.0), "degC": ("THETA", 1.0, 273.15),
    "°C": ("THETA", 1.0, 273.15),
    # pressure
    "Pa": ("M/(L*T2)", 1.0, 0.0), "kPa": ("M/(L*T2)", 1000.0, 0.0),
    "MPa": ("M/(L*T2)", 1e6, 0.0), "bar": ("M/(L*T2)", 1e5, 0.0),
    "atm": ("M/(L*T2)", 101325.0, 0.0),
    # angle
    "deg": ("A", 1.0, 0.0), "rad": ("A", 1.0, 0.0),
}

_NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?"
_QTY_RE = re.compile(
    r"(?P<num>" + _NUM + r")\s?(?P<unit>" +
    "|".join(re.escape(u) for u in sorted(_UNIT_TABLE, key=len, reverse=True)) +
    r")(?![A-Za-z0-9/^])"
)


def to_si(value: float, unit: str) -> Tuple[Optional[float], Optional[str]]:
    """Convert a value in a known unit to SI base. Returns (si_value, dim) or (None, None)."""
    u = _UNIT_TABLE.get(unit)
    if u is None:
        return None, None
    dim, factor, offset = u
    v = value * factor + (offset if dim == "THETA" else 0.0)
    return v, dim


def check_quantity(value: float, unit: str, location: str = "") -> List[Violation]:
    """Universal per-quantity checks. Applicable to ANY domain."""
    out: List[Violation] = []
    si, dim = to_si(value, unit)
    if si is None:
        return out
    disp = f"{value} {unit}"

    if dim == "L/T":  # speed
        if si < 0:
            out.append(Violation("speed_negative", "FAIL",
                                 f"Negative speed {disp}", location))
        elif si > C_LIGHT:
            out.append(Violation("speed_exceeds_light", "FAIL",
                                 f"Speed {disp} exceeds c = 299792458 m/s", location))
        elif si > WARN_SPEED_FRAC * C_LIGHT:
            out.append(Violation("speed_relativistic_warn", "WARN",
                                 f"Speed {disp} > 0.5c, implausible for macroscopic bodies", location))
    elif dim == "THETA":
        if si < 0:
            out.append(Violation("below_absolute_zero", "FAIL",
                                 f"Temperature {disp} below absolute zero", location))
    elif dim == "M":
        if si < 0:
            out.append(Violation("negative_mass", "FAIL",
                                 f"Negative mass {disp}", location))
    elif dim == "L":
        if si < 0:
            out.append(Violation("negative_length", "FAIL",
                                 f"Negative length {disp}", location))
    elif dim == "L/T2":
        if si < 0:
            out.append(Violation("negative_acceleration_mag", "FAIL",
                                 f"Negative acceleration magnitude {disp}", location))
        elif si > WARN_ACC_G * G_EARTH:
            out.append(Violation("acceleration_extreme", "WARN",
                                 f"Acceleration {disp} > {WARN_ACC_G:.0f} g", location))
    elif dim == "M*L/T2":
        if si < 0:
            out.append(Violation("negative_force", "WARN",
                                 f"Negative force {disp} (check sign convention)", location))
    return out


def check_probability(value: float, location: str = "") -> Optional[Violation]:
    if 0.0 <= value <= 1.0:
        return None
    return Violation("probability_out_of_range", "FAIL",
                     f"Probability {value} outside [0, 1]", location)


def check_kinematics(data: Dict[str, float], location: str = "") -> List[Violation]:
    """Cross-check kinematic descriptions for internal consistency.

    Accepts any subset of keys (SI units): v0, v, a, t, s (displacement), h (height).
    Verifies v = v0 + a t and s = v0 t + 0.5 a t^2 within tolerance when present.
    """
    out: List[Violation] = []
    v0, v, a, t = data.get("v0"), data.get("v"), data.get("a"), data.get("t")
    s, h = data.get("s"), data.get("h")
    tol = 0.02  # 2%

    if None not in (v0, v, a, t) and t != 0:
        pred = v0 + a * t
        if abs(v - pred) > tol * max(abs(v), abs(pred), 1e-12):
            out.append(Violation("kinematics_v_equation", "FAIL",
                                 f"v = v0 + a t violated: given v={v} m/s, "
                                 f"predicted {pred:.6g} m/s", location))
    if None not in (v0, a, t, s) and t != 0:
        pred = v0 * t + 0.5 * a * t * t
        if abs(s - pred) > tol * max(abs(s), abs(pred), 1e-12):
            out.append(Violation("kinematics_s_equation", "FAIL",
                                 f"s = v0 t + a t^2/2 violated: given s={s} m, "
                                 f"predicted {pred:.6g} m", location))
    if h is not None and t is not None and a is None and t != 0:
        # free-fall consistency: h = 0.5 g t^2 (if user supplied drop height + time)
        pred = 0.5 * G_EARTH * t * t
        if abs(h - pred) > max(tol * max(abs(h), abs(pred), 1e-12), 0.05):
            out.append(Violation("kinematics_freefall", "WARN",
                                 f"Free-fall check: h={h} m with t={t} s implies "
                                 f"{pred:.4g} m at standard gravity", location))
    return out


def check_conservation(before: Dict[str, float], after: Dict[str, float],
                       location: str = "") -> List[Violation]:
    """Energy (M*L2/T2) and momentum (M*L/T) conservation with 2% tolerance."""
    out: List[Violation] = []
    tol = 0.02
    for key in ("energy", "momentum"):
        b, a = before.get(key), after.get(key)
        if b is None or a is None:
            continue
        if abs(a - b) > tol * max(abs(b), abs(a), 1e-12):
            out.append(Violation(f"conservation_{key}", "FAIL",
                                 f"{key.capitalize()} not conserved: {b} -> {a} "
                                 f"(delta {(a - b) / max(abs(b), 1e-12) * 100:.1f}%)",
                                 location))
    return out


def check_text(text: str) -> Dict[str, Any]:
    """Main gate for LLM outputs: extract quantities with known units and check each.

    Deterministic regex extraction; unknown units are ignored (no false FAILs).
    """
    violations: List[Violation] = []
    scanned = 0
    for m in _QTY_RE.finditer(text):
        raw_num = m.group("num").replace(",", "")
        unit = m.group("unit")
        try:
            val = float(raw_num)
        except ValueError:
            continue
        # bare 'g' is ambiguous (gram vs gravity); require explicit unit-like usage
        if unit == "g" and not re.search(r"\d\s?g(?:\s|$|[,.;)])", text):
            continue
        loc = text[max(0, m.start() - 24):m.end() + 8].replace("\n", " ")
        violations.extend(check_quantity(val, unit, location=loc))
        scanned += 1
    # probabilities written as "probability/likelihood/confidence 0.xx"
    for m in re.finditer(r"(probability|likelihood|confidence)[^0-9\-+]{0,12}(" + _NUM + r")",
                         text, re.I):
        try:
            val = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        v = check_probability(val, location=m.group(0)[:40])
        if v:
            violations.append(v)
            scanned += 1

    return {
        "verdict": _verdict(violations),
        "n_quantities_checked": scanned,
        "violations": [v.to_dict() for v in violations],
        "engine": ENGINE_ID,
        "version": __version__,
        "deterministic": DETERMINISTIC,
    }


def full_check(text: str, kinematics: Optional[Dict[str, float]] = None,
               conservation: Optional[Tuple[Dict[str, float], Dict[str, float]]] = None
               ) -> Dict[str, Any]:
    """Combined check: text scan + optional kinematic + optional conservation."""
    result = check_text(text)
    extra: List[Violation] = []
    if kinematics:
        extra.extend(check_kinematics(kinematics))
    if conservation:
        b, a = conservation
        extra.extend(check_conservation(b, a))
    if extra:
        result["violations"] = result["violations"] + [v.to_dict() for v in extra]
        result["verdict"] = _verdict(
            [Violation(v["rule"], v["severity"], v["detail"], v["location"])
             for v in result["violations"]])
    return result


if __name__ == "__main__":
    import json
    demo = ("The drone descends at 450 km/h and lands after 12 s. "
            "The battery stores 5 kWh. Confidence: 1.8 probability of success.")
    print(json.dumps(full_check(demo, kinematics={"v0": 0.0, "a": 9.8, "t": 3.0, "v": 50.0}),
                     indent=2, ensure_ascii=False))
