"""Conditional common-clock control on pinned PRIMAT; no microphysical claim."""
import numpy as np


class Clock:
    def __init__(self, f0=3.66, alpha=0.0):
        if f0 <= 0:
            raise ValueError('f0 must be positive')
        self.f0, self.alpha = float(f0), float(alpha)

    def to_standard(self, tc):
        tc = np.asarray(tc)
        if self.alpha == 0:
            return tc / self.f0
        return -np.expm1(-self.alpha * tc) / (self.alpha * self.f0)

    def to_scaled(self, u):
        u = np.asarray(u)
        if self.alpha == 0:
            return self.f0 * u
        if np.any(1 - self.alpha * self.f0 * u <= 0):
            raise ValueError('clock inverse outside domain')
        return -np.log1p(-self.alpha * self.f0 * u) / self.alpha

    def factor(self, tc):
        return self.f0 * np.exp(self.alpha * np.asarray(tc))


class ScaledBackground:
    """Retain the standard thermal/neutrino history at corresponding T.

    NuclearNetwork is duck-typed. No new weak cache is generated: original
    weak rates are loaded for the identical Tnu(Tgamma) and scaled only in RAM.
    """
    def __init__(self, base, clock, scale_rates=True):
        self.base, self.clock, self.scale_rates = base, clock, scale_rates
        self.cfg, self.plasma = base.cfg, base.plasma

    def __getattr__(self, name):
        return getattr(self.base, name)

    def t_of_T(self, T):
        return self.clock.to_scaled(self.base.t_of_T(T))

    def T_of_t(self, tc):
        return self.base.T_of_t(self.clock.to_standard(tc))

    def rhoB_BBN(self, tc):
        return self.base.rhoB_BBN(self.clock.to_standard(tc))

    def a_of_t(self, tc):
        return self.base.a_of_t(self.clock.to_standard(tc))

    def t_of_a(self, a):
        return self.clock.to_scaled(self.base.t_of_a(a))

    def Tnu_of_t(self, tc):
        return self.base.Tnu_of_t(self.clock.to_standard(tc))

    def factor_at_kelvin(self, T_K):
        return self.clock.factor(self.t_of_T(np.asarray(T_K) / self.cfg.MeV_to_Kelvin))

    def weak_nTOp(self, T_K):
        rate = self.base.weak_nTOp(T_K)
        return rate / self.factor_at_kelvin(T_K) if self.scale_rates else rate

    def weak_pTOn(self, T_K):
        rate = self.base.weak_pTOn(T_K)
        return rate / self.factor_at_kelvin(T_K) if self.scale_rates else rate

    def Hubble(self, Tg, *args):
        return self.base.Hubble(Tg, *args) / self.clock.factor(self.t_of_T(Tg))


def attach(run, clock, scale_rates=True):
    if run.cfg.decay_era:
        raise ValueError('Optional post-BBN DT era is outside this control')
    base = run.background
    bg = ScaledBackground(base, clock, scale_rates)
    run.background = run.nuclear.background = bg
    if scale_rates:
        for name in ('rhsMT', 'JacobianMT', 'rhsLT', 'JacobianLT'):
            original = getattr(run.nucl, name)

            def scaled(Y, T_K, rho, ignored_forward, ignored_reverse, original=original):
                # Original weak callbacks: never apply the common factor twice.
                return original(Y, T_K, rho, base.weak_nTOp, base.weak_pTOn) / bg.factor_at_kelvin(T_K)

            setattr(run.nucl, name, scaled)
    temperatures = np.geomspace(10., .001, 17)
    u = np.asarray(base.t_of_T(temperatures))
    tc = clock.to_scaled(u)
    residuals = {}
    def check(name, actual, expected):
        actual, expected = np.asarray(actual), np.asarray(expected)
        residuals[name] = float(np.max(np.abs(actual-expected)/np.maximum(np.abs(expected), 1e-200)))
        if not np.allclose(actual, expected, rtol=2e-12, atol=1e-200):
            raise RuntimeError('Clock/background identity failed: '+name)
    check('clock_roundtrip', clock.to_standard(tc), u)
    check('T_gamma', bg.T_of_t(tc), base.T_of_t(u))
    check('rho_b', bg.rhoB_BBN(tc), base.rhoB_BBN(u))
    check('scale_factor', bg.a_of_t(tc), base.a_of_t(u))
    for flavour, expected in base.Tnu_of_t(u).items():
        check('Tnu_'+flavour, bg.Tnu_of_t(tc)[flavour], expected)
    if scale_rates:
        for direction in ('weak_nTOp','weak_pTOn'):
            kelvin=temperatures*run.cfg.MeV_to_Kelvin
            check(direction,getattr(bg,direction)(kelvin)*clock.factor(tc),getattr(base,direction)(kelvin))
    # Exact-map conditioning beyond the almost-constant physical alpha.
    # These are pointwise algebra tests, not extra cosmological runs.
    for alpha in (0., -1e-7):
        test_clock=Clock(3.66,alpha)
        check('clock_diagnostic_'+str(alpha),test_clock.to_standard(test_clock.to_scaled(u)),u)
    bg.audit={'relative_residuals':residuals,'sample_count':17,'physical_clock_identification':False}
    return bg
