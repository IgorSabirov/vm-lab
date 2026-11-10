"""Exact probability and total-variation estimators for finite distributions."""
from __future__ import annotations
from fractions import Fraction
from math import isfinite
from typing import Hashable, Mapping

Mass = int | Fraction


def _as_fraction(value: object) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        raise TypeError("probability masses must be int or Fraction; float/bool are forbidden")
    out = Fraction(value)
    if out < 0:
        raise ValueError("probability masses must be nonnegative")
    return out


def validate_distribution(distribution: Mapping[Hashable, Mass]) -> dict[Hashable, Fraction]:
    if not distribution:
        raise ValueError("probability distribution cannot be empty")
    converted = {k: _as_fraction(v) for k, v in distribution.items()}
    if sum(converted.values(), Fraction(0, 1)) != 1:
        raise ValueError("probability distribution must sum exactly to one")
    return converted


def total_variation(p: Mapping[Hashable, Mass], q: Mapping[Hashable, Mass]) -> Fraction:
    pp = validate_distribution(p)
    qq = validate_distribution(q)
    support = set(pp) | set(qq)
    tv = sum((abs(pp.get(k, Fraction(0)) - qq.get(k, Fraction(0))) for k in support), Fraction(0)) / 2
    if not (Fraction(0) <= tv <= Fraction(1)):
        raise ArithmeticError("TV outside [0,1]; probability validation failed")
    return tv


def point_mass(value: Hashable) -> dict[Hashable, Fraction]:
    return {value: Fraction(1, 1)}


def direct_total_variation(p: Mapping[Hashable, Mass], q: Mapping[Hashable, Mass]) -> Fraction:
    """Independent direct-sum implementation used only by validation controls."""
    p2, q2 = validate_distribution(p), validate_distribution(q)
    keys = sorted(set(p2) | set(q2), key=repr)
    accum = Fraction(0, 1)
    for key in keys:
        a = p2[key] if key in p2 else Fraction(0)
        b = q2[key] if key in q2 else Fraction(0)
        accum += abs(a - b)
    return accum / 2


def mixed_difference_l1(p11: Mapping[Hashable, Mass], p10: Mapping[Hashable, Mass],
                        p01: Mapping[Hashable, Mass], p00: Mapping[Hashable, Mass]) -> Fraction:
    """L1 norm of the signed factorial mixed difference; not itself a TV."""
    d11, d10, d01, d00 = map(validate_distribution, (p11, p10, p01, p00))
    keys = set(d11) | set(d10) | set(d01) | set(d00)
    signed = {k: d11.get(k, 0) - d10.get(k, 0) - d01.get(k, 0) + d00.get(k, 0) for k in keys}
    return sum((abs(Fraction(v)) for v in signed.values()), Fraction(0, 1))
