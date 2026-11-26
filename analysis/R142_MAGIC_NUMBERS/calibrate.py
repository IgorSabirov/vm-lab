"""Independent shell-filling and metrological controls. Standard library only."""
import json
from fractions import Fraction
from itertools import accumulate, product
from math import comb


def filled_shells(dimension, maximum):
    # Each nonnegative occupation tuple is one orbital with two spin states.
    states = list(product(range(maximum + 1), repeat=dimension))
    sizes = [2 * sum(sum(state) == k for state in states) for k in range(maximum + 1)]
    assert sizes == [2 * comb(k + dimension - 1, dimension - 1) for k in range(maximum + 1)]
    return list(accumulate(sizes))


def main():
    value = Fraction("137.035999177")
    uncertainty = Fraction("0.000000021")
    print(json.dumps(dict(dot_2d=filled_shells(2, 3), oscillator_3d=filled_shells(3, 5),
                          inverse_alpha=str(float(value)), uncertainty=str(uncertainty),
                          residual_of_exact_137=str(value-137),
                          residual_in_uncertainties=float((value-137)/uncertainty)), indent=2))


if __name__ == "__main__":
    main()
