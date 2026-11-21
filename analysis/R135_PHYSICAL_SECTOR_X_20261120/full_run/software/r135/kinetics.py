"""Homogeneous nonthermal particle kinetics on fixed comoving momentum cells.

f_i is a cell-constant occupation at q=a*p. The Liouville redshift term is
therefore exact: df_i/dt=C_i. Number and energy source moments use precisely
the same cells as the state. Supplied collision kernels are physical inputs;
the solver does not infer an X portal or full SM neutrino transport from a
thermal relaxation coefficient. See NUMERICS_KINETICS_NEUTRINOS.md.
"""
from __future__ import annotations

import math

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import solve_ivp
from scipy.special import expit

from .common import InputError, OpenInput, finite


def _vector(value, size, name, *, nonnegative=False):
    arr = np.asarray(value, dtype=float)
    if arr.shape != (size,) or not np.isfinite(arr).all() or (nonnegative and np.any(arr < 0)):
        raise InputError(f"{name}: expected {size} finite" + (" nonnegative" if nonnegative else "") + " values")
    return arr


class MomentumGrid:
    """Finite q cells in MeV; scale factor is dimensionless and explicitly fixed.

    g counts the states described by ONE occupation. Use g=1 for a single
    massless neutrino helicity. A particle and antiparticle have separate
    grids/states unless their equality is a supplied physical assumption.
    """
    def __init__(self, q_edges_MeV, mass_MeV=0., degeneracy=1., *, moment_order=24,
                 statistics="fermion"):
        self.q_edges = np.asarray(q_edges_MeV, dtype=float)
        self.mass = finite(mass_MeV, "kinetic particle mass", nonnegative=True)
        self.degeneracy = finite(degeneracy, "kinetic degeneracy", positive=True)
        names = {"fermion": "fermion", "boson": "boson", "classical": "classical",
                 "FD": "fermion", "BE": "boson", "MB": "classical"}
        if statistics not in names:
            raise InputError("statistics must be fermion, boson or classical")
        self.statistics = names[statistics]
        self.statistical_sign = {"fermion": -1, "boson": 1, "classical": 0}[self.statistics]
        if (self.q_edges.ndim != 1 or len(self.q_edges) < 2 or not np.isfinite(self.q_edges).all()
                or self.q_edges[0] != 0 or np.any(np.diff(self.q_edges) <= 0)):
            raise InputError("comoving momentum cell edges must start at zero and strictly increase")
        if type(moment_order) is not int or moment_order < 4:
            raise InputError("moment quadrature order must be an integer >=4")
        self.size = len(self.q_edges)-1
        left, right = self.q_edges[:-1], self.q_edges[1:]
        self.number_weights = self.degeneracy/(6*np.pi**2)*(right**3-left**3)
        self.q_centres = .75*(right**4-left**4)/(right**3-left**3)
        x, w = leggauss(moment_order)
        self._q = left[:, None]+(x[None, :]+1)*(right-left)[:, None]/2
        self._wq2 = self.degeneracy/(2*np.pi**2)*w[None, :]*(right-left)[:, None]/2*self._q**2
        self.moment_order = moment_order

    def energy_pressure_weights(self, a):
        """Comoving density weights, before dividing by a**3."""
        a = finite(a, "scale factor", positive=True)
        if self.mass == 0:
            w = self.degeneracy/(8*np.pi**2*a)*(self.q_edges[1:]**4-self.q_edges[:-1]**4)
            return w, w/3
        p = self._q/a
        energy = np.sqrt(p*p+self.mass*self.mass)
        return np.sum(self._wq2*energy, axis=1), np.sum(self._wq2*p*p/(3*energy), axis=1)

    def representative_energies(self, a):
        return self.energy_pressure_weights(a)[0]/self.number_weights

    def occupation(self, f, *, check_pauli=True):
        values = _vector(f, self.size, "occupation")
        if check_pauli and (np.any(values < 0) or (self.statistics == "fermion" and np.any(values > 1))):
            raise InputError("occupation outside its statistical domain: nonnegative, and <=1 for fermions")
        return values

    def moments(self, f, a):
        # Internal implicit-solver stages can lie just outside the domain;
        # no clipping is performed. Initial and accepted states are checked
        # by integrate_kinetic_bath, while outer solvers own their own check.
        f = self.occupation(f, check_pauli=False)
        ew, pw = self.energy_pressure_weights(a)
        volume = float(a)**3
        return {"number_MeV3": float(self.number_weights @ f/volume),
                "rho_MeV4": float(ew @ f/volume), "pressure_MeV4": float(pw @ f/volume)}

    def source_moments(self, df_dt, a):
        df_dt = _vector(df_dt, self.size, "collision/source derivative")
        ew, _ = self.energy_pressure_weights(a)
        return {"number_MeV3_s": float(self.number_weights @ df_dt/float(a)**3),
                "energy_MeV4_s": float(ew @ df_dt/float(a)**3)}

    def equilibrium(self, a, T_MeV, mu_MeV=0.):
        """FD/BE/MB equilibrium at cell mean energies, not exact cell averages.

        No separate Bose condensate at q=0 is represented by these cells.
        A chemical potential above the rest mass is consequently invalid.
        """
        temperature = finite(T_MeV, "bath temperature", positive=True)
        mu = finite(mu_MeV, "chemical potential")
        argument = (self.representative_energies(a)-mu)/temperature
        if self.statistics == "fermion":
            return expit(-argument)
        if self.statistics == "boson":
            if mu > self.mass:
                raise InputError("boson chemical potential exceeds the rest mass; condensate dynamics is not implemented")
            with np.errstate(over="ignore"):
                return 1/np.expm1(argument)
        with np.errstate(over="ignore"):
            result = np.exp(-argument)
        if not np.isfinite(result).all():
            raise InputError("classical equilibrium exceeds floating-point range")
        return result

    def fermi_dirac(self, a, T_MeV, mu_MeV=0.):
        if self.statistics != "fermion":
            raise InputError("fermi_dirac requires fermionic statistics")
        return self.equilibrium(a, T_MeV, mu_MeV)

    def massless_spectrum(self, f, a):
        """Lossless connection to the weak integrator for a massless species."""
        from .neutrino_rates import BinnedSpectrum
        if self.mass != 0 or self.statistics != "fermion":
            raise OpenInput("weak neutrino quadrature assumes a massless fermionic spectrum")
        return BinnedSpectrum(self.q_edges/finite(a, "scale factor", positive=True), self.occupation(f))


def _source(source):
    if not isinstance(source, str) or not source.strip():
        raise OpenInput("a collision kernel requires its explicit physical or diagnostic source")
    return source


class EmissionAbsorption:
    """C_i = j_i (1+eta*f_i) - kappa_i*f_i, retaining inverse absorption.

    Rates are arrays or callables ``rate(time_s, a, bath_T_MeV) -> array``.
    Both rates must be supplied, nonnegative, and in s^-1. The operator is
    eta=-1,+1,0 for FD, BE, MB. The operator is inward pointing on f=0
    (also f=1 for fermions). Bose growth is not artificially clipped.
    This class does not certify that an input
    kernel was derived from a particular microscopic amplitude.
    """
    def __init__(self, grid, emission_s_inv, absorption_s_inv, *, source):
        self.grid = grid
        self.emission = emission_s_inv
        self.absorption = absorption_s_inv
        self.source = _source(source)

    def coefficients(self, time_s, a, bath_T_MeV):
        out = []
        for name, item in (("emission", self.emission), ("absorption", self.absorption)):
            value = item(time_s, a, bath_T_MeV) if callable(item) else item
            out.append(_vector(value, self.grid.size, name+" rate", nonnegative=True))
        return tuple(out)

    def rhs(self, time_s, f, a, bath_T_MeV):
        f = self.grid.occupation(f, check_pauli=False)
        j, kappa = self.coefficients(time_s, a, bath_T_MeV)
        return j*(1+self.grid.statistical_sign*f)-kappa*f


class ConservativeScattering:
    """Statistical inter-cell redistribution, exactly conserving number.

    W[i,j] is the transition rate from source cell j to destination cell i
    before the target blocking factor. It has units s^-1. W must either be
    a nonnegative matrix or callable ``W(time_s,a,T_bath)``. Every pair is
    accumulated once with opposite signs in the cell particle numbers.
    Energy gained/lost by the distribution belongs to the coupled bath.
    """
    def __init__(self, grid, transition_s_inv, *, source):
        self.grid = grid
        self.transition = transition_s_inv
        self.source = _source(source)

    def coefficients(self, time_s, a, bath_T_MeV):
        value = self.transition(time_s, a, bath_T_MeV) if callable(self.transition) else self.transition
        matrix = np.asarray(value, dtype=float)
        if (matrix.shape != (self.grid.size, self.grid.size) or not np.isfinite(matrix).all()
                or np.any(matrix < 0)):
            raise InputError("transition rates must form a finite nonnegative square matrix")
        return matrix

    def rhs(self, time_s, f, a, bath_T_MeV):
        f = self.grid.occupation(f, check_pauli=False)
        matrix = self.coefficients(time_s, a, bath_T_MeV)
        n = self.grid.number_weights*f
        transfers = matrix*n[None, :]*(1+self.grid.statistical_sign*f[:, None])
        # Summing the antisymmetric matrix makes each pair number-conserving
        # independently, including inverse scattering and statistical factors.
        return np.sum(transfers-transfers.T, axis=1)/self.grid.number_weights


def detailed_balance_transition(grid, a, T_MeV, conductance_MeV3_s):
    """Construct W from a supplied symmetric conductance, for verification.

    W_ij*w_j = G_ij exp[(E_j-E_i)/(2T)]. Hence the discrete FD distribution
    (or BE/MB) is an exact fixed point for every admissible chemical potential. G is an INPUT,
    not a computed weak or portal cross section; its source must accompany
    the enclosing ConservativeScattering object.
    """
    temperature = finite(T_MeV, "bath temperature", positive=True)
    conductance = np.asarray(conductance_MeV3_s, float)
    if (conductance.shape != (grid.size, grid.size) or not np.isfinite(conductance).all()
            or np.any(conductance < 0) or not np.array_equal(conductance, conductance.T)):
        raise InputError("detailed-balance conductance must be nonnegative and exactly symmetric")
    energy = grid.representative_energies(a)
    exponent = (energy[None, :]-energy[:, None])/(2*temperature)
    active = conductance > 0
    if np.any(np.abs(exponent[active]) > 600):
        raise InputError("transition exponent is numerically unresolved; rescale the supplied kernel")
    result = np.zeros_like(conductance)
    result[active] = conductance[active]*np.exp(exponent[active])
    return result/grid.number_weights[None, :]


def kinetic_rhs(grid, operators, time_s, f, a, bath_T_MeV):
    """Composable P7 RHS plus source moments, ready for joint state integration."""
    derivative = np.zeros(grid.size)
    for operator in operators:
        if operator.grid is not grid:
            raise InputError("collision operator and state must share the same momentum grid")
        derivative += operator.rhs(time_s, f, a, bath_T_MeV)
    return derivative, grid.source_moments(derivative, a)


def integrate_kinetic_bath(grid, initial_f, operators, time_s, *, bath_coefficient,
                           bath_T_MeV, H_s_inv=0., initial_a=1., rtol=1e-8,
                           atol=1e-11, max_step_s=math.inf, method="Radau"):
    """Joint f(q,t), scale factor and finite radiation-bath evolution.

    rho_b=c*T_b**4, P_b=rho_b/3; c is explicitly supplied. H is a constant
    or callable ``H(time_s,a,rho_total_MeV4)``. The same collision Q that
    heats the particles is subtracted from the bath at every RHS evaluation:
    drho_b/dt=-4*H*rho_b-Q. Thus the bath temperature feeds back into its own
    supplied kernels. For a general EOS, P7 should reuse kinetic_rhs and
    moments rather than treating this radiation bath as the SM EOS.
    """
    f0 = grid.occupation(initial_f)
    operators = tuple(operators)
    time = np.asarray(time_s, float)
    if (time.ndim != 1 or len(time) < 2 or not np.isfinite(time).all()
            or time[0] < 0 or np.any(np.diff(time) <= 0)):
        raise InputError("kinetic integration needs an increasing nonnegative time grid")
    coefficient = finite(bath_coefficient, "radiation bath coefficient", positive=True)
    temperature = finite(bath_T_MeV, "initial bath temperature", positive=True)
    a0 = finite(initial_a, "initial scale factor", positive=True)
    relative = finite(rtol, "kinetic relative tolerance", positive=True)
    absolute = finite(atol, "kinetic absolute tolerance", positive=True)
    if max_step_s != math.inf:
        finite(max_step_s, "kinetic maximum time step", positive=True)
    if not callable(H_s_inv):
        finite(H_s_inv, "Hubble rate", nonnegative=True)
    rho0 = coefficient*temperature**4
    initial_energy = a0**3*(rho0+grid.moments(f0, a0)["rho_MeV4"])
    # y=(a,rho_b,f..., cumulative expansion work, cumulative transfer).
    y0 = np.concatenate(([a0, rho0], f0, [0., 0.]))

    def rhs(t, y):
        a, rho = y[:2]
        if a <= 0 or rho <= 0:
            raise InputError("kinetic integration exhausted or invalidated the positive bath")
        f = y[2:2+grid.size]
        bath_t = (rho/coefficient)**.25
        moments = grid.moments(f, a)
        total_rho = rho+moments["rho_MeV4"]
        hubble = H_s_inv(t, a, total_rho) if callable(H_s_inv) else H_s_inv
        hubble = finite(hubble, "Hubble rate", nonnegative=True)
        derivative, sources = kinetic_rhs(grid, operators, t, f, a, bath_t)
        q = sources["energy_MeV4_s"]
        work = 3*hubble*a**3*(rho/3+moments["pressure_MeV4"])
        return np.concatenate(([hubble*a, -4*hubble*rho-q], derivative, [work, q]))

    sol = solve_ivp(rhs, (time[0], time[-1]), y0, method=method,
                    t_eval=time, rtol=relative, atol=absolute, max_step=max_step_s)
    if not sol.success or sol.y.shape[1] != len(time) or not np.isfinite(sol.y).all():
        raise InputError("kinetic integration failed: "+str(sol.message))
    f_values = sol.y[2:2+grid.size].T
    # Never silently clip Pauli violations: even a small one is part of the
    # explicit returned diagnostic; material violations fail the calculation.
    violation = float(max(0., -np.min(f_values),
                          np.max(f_values)-1 if grid.statistics == "fermion" else 0.))
    if violation > max(20*absolute, 1e-10):
        raise InputError("kinetic integration violates occupation bounds; refine or change the solver")
    moments = [grid.moments(f, a) for f, a in zip(f_values, sol.y[0])]
    bath_temperatures = (sol.y[1]/coefficient)**.25
    sources = [kinetic_rhs(grid, operators, t, f, a, temp)[1]
               for t, f, a, temp in zip(time, f_values, sol.y[0], bath_temperatures)]
    balance = sol.y[0]**3*(sol.y[1]+np.array([x["rho_MeV4"] for x in moments]))+sol.y[-2]
    return {"time_s": time.tolist(), "scale_factor": sol.y[0].tolist(),
            "q_edges_MeV": grid.q_edges.tolist(), "occupation": f_values.tolist(),
            "bath_T_MeV": bath_temperatures.tolist(), "bath_rho_MeV4": sol.y[1].tolist(),
            "number_MeV3": [x["number_MeV3"] for x in moments],
            "rho_MeV4": [x["rho_MeV4"] for x in moments],
            "pressure_MeV4": [x["pressure_MeV4"] for x in moments],
            "Q_to_kinetic_MeV4_s": [x["energy_MeV4_s"] for x in sources],
            "cumulative_transfer_MeV4": sol.y[-1].tolist(),
            "comoving_expansion_work_MeV4": sol.y[-2].tolist(),
            "relative_energy_balance": ((balance-initial_energy)/initial_energy).tolist(),
            "max_occupation_bound_violation": violation,
            "operator_sources": [operator.source for operator in operators], "statistics": grid.statistics,
            "method": method, "rtol": relative, "atol": absolute,
            "nfev": int(sol.nfev), "moment_order": grid.moment_order,
            "tail": "zero outside supplied comoving cells; convergence in support is required",
            "scope": "homogeneous occupations with supplied kernels and finite radiation bath; no condensate mode"}
