"""One-level, two-channel 3He(d,p)4He rate at the marginal medians of de Souza et al."""
import ctypes as ct
from ctypes.util import find_library
from math import pi, sqrt

import numpy as np
from scipy import constants
from scipy.special import roots_legendre


class GslResult(ct.Structure):
    _fields_ = [("value", ct.c_double), ("error", ct.c_double)]


def coulomb_functions():
    library = find_library("gsl")
    if not library:
        raise RuntimeError("Install GNU Scientific Library (libgsl) for the Coulomb waves.")
    gsl = ct.CDLL(library)
    gsl.gsl_set_error_handler_off()
    waves = gsl.gsl_sf_coulomb_wave_FG_e
    waves.argtypes = [ct.c_double] * 3 + [ct.c_int] + [ct.POINTER(GslResult)] * 4 + [ct.POINTER(ct.c_double)] * 2
    waves.restype = ct.c_int
    return waves


def he3d_rates(t9, order=192, lower=0.001, upper=2.0):
    # Energies and masses in MeV, radii in fm. Source Eqs. 1–6 and Table 2.
    waves = coulomb_functions()
    masses = [constants.physical_constants[name + " mass energy equivalent in MeV"][0]
              for name in ("deuteron", "helion", "proton", "alpha particle")]
    md, mh, mp, ma = masses
    mu_in = md * mh / (md + mh)
    mu_out = mp * ma / (mp + ma)
    q_value = md + mh - mp - ma
    hbar_c = constants.hbar * constants.c / constants.electron_volt * 1e9  # MeV fm

    def channel(energy, mass, radius, ell):
        wave_number = sqrt(2 * mass * energy) / hbar_c
        rho = radius * wave_number
        eta = 2 * constants.alpha * sqrt(mass / (2 * energy))
        fg = [GslResult() for _ in range(4)]
        exponents = [ct.c_double(), ct.c_double()]
        status = waves(eta, rho, ell, 0, *(ct.byref(x) for x in fg + exponents))
        if status or any(x.value for x in exponents):
            raise ArithmeticError(f"Coulomb wave failure at {energy} MeV (GSL {status})")
        f, fp, g, gp = (x.value for x in fg)
        assert abs(fp * g - f * gp - 1) < 2e-8
        norm = f*f + g*g
        return rho/norm, rho*(f*fp + g*gp)/norm

    eigenenergy, boundary_energy = 0.202, 0.516
    width_d, width_p = 0.362, 0.0350
    bd = channel(boundary_energy, mu_in, 3.25, 0)[1]
    bp = channel(boundary_energy + q_value, mu_out, 5.77, 2)[1]
    nodes, weights = roots_legendre(order)
    energy = (upper-lower)*nodes/2 + (upper+lower)/2
    sigma_barns = []
    for e in energy:
        pd, sd = channel(e, mu_in, 3.25, 0)
        pp, sp = channel(e + q_value, mu_out, 5.77, 2)
        gd, gp = 2*width_d*pd, 2*width_p*pp
        shift = -width_d*(sd-bd) - width_p*(sp-bp)
        probability = gd*gp / ((eigenenergy + shift - e)**2 + ((gd+gp)/2)**2)
        assert 0 <= probability <= 1
        sigma_barns.append(pi * hbar_c**2 / (2*mu_in*e) * (2/3) * probability / 100)
    kt = constants.Boltzmann / constants.electron_volt * 1000 * np.asarray(t9)
    integral = (upper-lower)/2 * (np.exp(-energy/kt[:, None]) @ (weights*energy*sigma_barns))
    return constants.Avogadro * 1e-22 * constants.c * sqrt(8/(pi*mu_in)) * integral / kt**1.5
