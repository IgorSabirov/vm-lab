"""Event-addressed coupling, not an implementation/certification of Random123."""
import hashlib
import json


def uniform(seed, *address):
    raw = json.dumps(["now-v1", int(seed), *address], separators=(",", ":"))
    n = int.from_bytes(hashlib.sha256(raw.encode()).digest()[:8], "big")
    return ((n >> 12) + 0.5) / 2**52  # representable midpoint, strictly between 0 and 1


def input_bits(seed, forced=None, preparation="correlated"):
    if forced is not None:
        if len(forced) != 2 or any(x not in (0, 1) for x in forced):
            raise ValueError("content must be two bits")
        return list(forced)
    if preparation == "independent":
        return [int(uniform(seed, "prepare", "independent", side) < .5) for side in ("A", "B")]
    common = int(uniform(seed, "prepare", "common") < 0.5)
    return [common ^ int(uniform(seed, "prepare", side) < 0.25)
            for side in ("A", "B")]


def exact_histories():
    """R124 preparation: exact weights; do not confuse with finite seed counts."""
    from fractions import Fraction
    from itertools import product
    for common, a, b in product((0, 1), repeat=3):
        weight = Fraction(1, 2) * Fraction(1 if a else 3, 4) * Fraction(1 if b else 3, 4)
        yield (common, a, b), [common ^ a, common ^ b], weight
