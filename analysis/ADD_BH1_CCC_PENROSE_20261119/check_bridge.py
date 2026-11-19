"""Controls for the proposed ADD / BH1 / Gupta bridge and the CMB comparison."""
import json
import sys
from fractions import Fraction
from math import asin, comb, degrees, exp, fsum, log, sin, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"ADD_C1_AUTHOR_REPRO_20261116"))
import graph_engine
import ring_engine


def add_checks():
    densities = []
    for rho in (Fraction(1, 10), Fraction(1, 2)):
        def entropy(length):
            p = 2*length*rho
            assert p.denominator == 1
            return log(comb(2*length, int(p)))
        for length in (50, 500, 5000):
            d = 5  # integer lengths with the exact same density on both sides
            xi = length*(entropy(length+d)-entropy(length-d))/(2*d)
            densities.append(dict(L=length, rho=str(rho), Xi_over_S=xi/entropy(length)))
        assert abs(densities[-1]["Xi_over_S"]-1) < .002

    outputs = []
    for word in [(1, 2, 0), (1, 0, 2), (3, 0, 0)]:
        a = ring_engine.forward(ring_engine.make(word))
        b = graph_engine.forward(graph_engine.make(word))
        assert ring_engine.snapshot(a) == graph_engine.snapshot(b)
        assert sum(bool(v & 1) for v in word) == sum(bool(v & 2) for v in word) == 1
        outputs.append(dict(states=word, next_length=len(a)))
    assert [v["next_length"] for v in outputs] == [2, 3, 4]
    return dict(fixed_density=densities, C1_same_charges=outputs)


def canonical(beta, energies, counts):
    weights = [n*exp(-beta*e) for e, n in zip(energies, counts)]
    z = fsum(weights)
    probabilities = [w/z for w in weights]
    entropy = fsum(p*log(n/p) for p, n in zip(probabilities, counts))
    assert abs(entropy-log(z)-beta*fsum(p*e for p,e in zip(probabilities, energies))) < 1e-13
    return z, entropy


def scaling_control():
    baseline = canonical(1, [0,1,2],[1,3,2])
    rescaled = canonical(1/3, [0,3,6],[1,3,2])
    changed = canonical(1/3, [0,3,7],[1,3,2])
    assert all(abs(v-w)<1e-14 for v,w in zip(baseline,rescaled))
    assert abs(changed[1]-baseline[1]) > .01
    return dict(S0=baseline[1], uniform_S=rescaled[1], changed_level_S=changed[1])


def annulus_slope(pixels, r1, width):
    selected = [(r,t) for r,t,masked in pixels if not masked and r1 <= r < r1+width]
    if len(selected) < 2:
        raise ValueError("Fewer than two selected pixels")
    rbar = fsum(r for r,t in selected)/len(selected)
    tbar = fsum(t for r,t in selected)/len(selected)
    variance = fsum((r-rbar)**2 for r,t in selected)
    if variance == 0:
        raise ValueError("No radial variation")
    return fsum((r-rbar)*(t-tbar) for r,t in selected)/variance


def sky_checks():
    # First five Planck rows in the left column of Table II, and every
    # epsilon=0.02 row of Table V. Galactic polar angle and longitude in radians.
    planck = [(2.219,.012),(.204,2.405),(.703,2.777),(2.988,4.908),(2.545,.051)]
    wmap = [(.204,2.405),(.582,5.323),(2.219,.012),(.703,2.778),(2.118,1.853),
            (2.988,4.909),(.595,3.159),(2.962,.056)]
    def angle(a,b):
        h = sin((a[0]-b[0])/2)**2+sin(a[0])*sin(b[0])*sin((a[1]-b[1])/2)**2
        return degrees(2*asin(sqrt(min(1,max(0,h)))))
    nearest = [min(angle(p,w) for w in wmap) for p in planck]
    assert sum(d < .1 for d in nearest) == 4
    diameters = [degrees(2*r) for r in (.03,.04)]
    assert diameters[-1] < 6
    # Eq. (1), masked/outside outliers and centered regression.
    for slope in (0,-3,5):
        pixels = [(r, 2+slope*r,False) for r in (.013,.018,.023,.028)]
        pixels.extend([(.019,10000,True),(.004,-10000,False)])
        assert abs(annulus_slope(pixels,.01,.02)-slope) < 1e-12
    return dict(paper_diameter_degrees=diameters, edonzo_gaussian_fwhm_degrees=[6,8],
                nearest_wmap_degrees=nearest, matched_at_0p1_deg=4,
                planck_rows_tested=5, wmap_rows_same_width=8, slope_controls=3)


if __name__ == "__main__":
    print(json.dumps(dict(ADD=add_checks(), canonical=scaling_control(), CMB=sky_checks()), indent=2))
