"""Free thermal SU(3) on S^3. Finite-rank group integral, normalized Haar measure."""
import json
from math import pi

import numpy as np
from scipy.optimize import brentq


class FreeSU3:
    def __init__(self, grid, windings, offset=0):
        angles = 2*pi*np.arange(grid)/grid
        first, second = np.meshgrid(angles+2*pi*offset/grid, angles-2*pi*offset/(2*grid), indexing="ij")
        third = -first-second
        pairs = (first-second, first-third, second-third)
        haar = np.prod([4*np.sin(delta/2)**2 for delta in pairs], axis=0)/6
        assert abs(haar.mean()-1) < 1e-13
        self.haar = haar.ravel()/grid**2
        self.n = np.arange(1, windings+1)
        self.adjoint = np.stack([(2+2*sum(np.cos(n*delta) for delta in pairs)).ravel()
                                 for n in self.n])
        self.loop = abs(np.exp(1j*first)+np.exp(1j*second)+np.exp(1j*third)).ravel()/3

        assert abs(self.haar @ (3*self.loop)**2-1) < 1e-12

    def thermal(self, u):
        b = 1/u
        x = np.exp(-b*self.n)
        z = (6*x**2-2*x**3)/(1-x)**3
        exponent = (z/self.n) @ self.adjoint
        er = (12*x**2/(1-x)**4) @ self.adjoint  # minus partial_b exponent
        shift = exponent.max()
        weights = self.haar*np.exp(exponent-shift)
        norm = weights.sum()
        weights /= norm
        log_z = np.log(norm)+shift
        er_mean = weights @ er
        deviation = self.loop-(weights @ self.loop)
        chi = 9*(weights @ (deviation**2))
        # d/du E[O]=cov(O,ER)/u^2 for O independent of u.
        chi_prime = 9*(weights @ (deviation**2*(er-er_mean)))/u**2
        return dict(chi=float(chi), chi_prime=float(chi_prime),
                    log_Z=float(log_z), S=float(log_z+b*er_mean), ER=float(er_mean))


def peak(grid, windings, offset=0):
    model = FreeSU3(grid, windings, offset)
    values = np.linspace(0.4, 1.2, 41)
    derivative = [model.thermal(u)["chi_prime"] for u in values]
    changes = [(a, b) for a, b, left, right in zip(values, values[1:], derivative, derivative[1:])
               if left*right < 0]
    assert len(changes) == 1 and derivative[0] > 0 > derivative[-1]
    lo, hi = changes[0]
    root = brentq(lambda u: model.thermal(u)["chi_prime"], lo, hi, xtol=2e-13)
    result = model.thermal(root)
    # A separate finite-difference check of E R = -partial_b ln Z.
    h = 1e-5
    b = 1/root
    derivative_b = (model.thermal(1/(b+h))["log_Z"]-model.thermal(1/(b-h))["log_Z"])/(2*h)
    assert abs(derivative_b+result["ER"]) < 1e-6
    return dict(grid=grid, windings=windings, grid_offset=offset, peak_TR=root, **result)


if __name__ == "__main__":
    runs = [peak(g, n) for g, n in [(90, 12), (180, 12), (180, 20), (360, 20)]]
    assert abs(runs[-1]["peak_TR"]-runs[-2]["peak_TR"]) < 2e-5
    assert abs(runs[-1]["S"]-runs[-2]["S"]) < 3e-3
    shifted = peak(360, 20, 0.37)
    assert abs(shifted["peak_TR"]-runs[-1]["peak_TR"]) < 2e-6
    runs.append(shifted)
    print(json.dumps(runs, indent=2))
