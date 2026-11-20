# SU(3) latent-heat mass scale and relaxation gate C

Date: 20 November 2026.

## Choice of lattice input

Use the newer and more precise of the two project references:

\[
\mathcal L/T_c^4=1.175(10)
\]

[Giusti et al., arXiv:2501.10284](https://arxiv.org/abs/2501.10284).

The alternative \(1.025(21)(27)\) from [Borsanyi et al., arXiv:2202.05234](https://arxiv.org/abs/2202.05234) is retained as a cross-check, not averaged with the first result: the central values are from separate lattice determinations and should not be combined without a common systematic-error model.

## Temperature ratio from the BBN energy budget

The late-transfer BBN/CLASS benchmark is

\[
\Delta\rho/T_\gamma^4=0.044518075411783944.
\]

Under the optimistic assumptions that the transition occurs at \(T_X=T_c\), all of the latent heat is available (\(\epsilon=1\)), and it supplies this transfer, the energy bound gives

\[
\xi\equiv T_X/T_\gamma
=\left[\frac{0.0445180754118}{1.175}\right]^{1/4}
=0.4411889520.
\]

Propagating only the quoted \(0.010\) uncertainty gives \(\xi=0.44119\pm0.00094\). This is an energy-budget threshold, not an independent measurement of the hidden temperature.

## Conditional mass-gap and relaxation estimate

Test the proposed mass-gap identification

\[
m_X=T_c=\xi T_\gamma,
\qquad \tau_X=1/m_X
\]

in natural units. In seconds, \(\tau_X=\hbar/(m_Xc^2)\).

The physical radiation-era Friedmann rate is

\[
H=1.66\sqrt{g_*}\frac{T_\gamma^2}{M_{\rm Pl}},
\qquad M_{\rm Pl}=1.2209\times10^{22}\ {\rm MeV}.
\]

It is **not** \(H=T_\gamma\). The shorthand \(H^{-1}\sim1/T_\gamma\) omits the Planck suppression and is not the cosmological Hubble time in the same MeV units.

The paired PRIMAT/LINX integration spans \(T_\gamma=8.617\) to \(0.00517\) MeV. The endpoint estimates below use \(g_*=10.75\) before electron-positron annihilation and \(g_*=3.36\) after it.

| Epoch | \(T_\gamma\) (MeV) | \(T_c=m_X\) (MeV) | \(\tau_X\) (s) | \(H^{-1}\) (s) | \(\tau_X/H^{-1}\) |
|---|---:|---:|---:|---:|---:|
| BBN start | 8.617 | 3.80173 | \(1.73\times10^{-22}\) | \(1.99\times10^{-2}\) | \(8.71\times10^{-21}\) |
| Early window low | 2.0 | 0.88238 | \(7.46\times10^{-22}\) | 0.369 | \(2.02\times10^{-21}\) |
| Late window high | 0.2 | 0.08824 | \(7.46\times10^{-21}\) | 36.9 | \(2.02\times10^{-22}\) |
| Late window low | 0.02 | 0.008824 | \(7.46\times10^{-20}\) | \(6.60\times10^3\) | \(1.13\times10^{-23}\) |
| BBN end | 0.00517 | 0.002281 | \(2.89\times10^{-19}\) | \(9.88\times10^4\) | \(2.92\times10^{-24}\) |

Thus, **conditional on \(m_X=T_c\) and absence of critical slowing down**, microscopic equilibration is faster than expansion by at least \(1.15\times10^{20}\) across the listed BBN interval.

For comparison, incorrectly setting \(H=T_\gamma\) would give \(\tau_X/H^{-1}=T_\gamma/T_c=1/\xi\simeq2.27\), a false failure. The Planck scale in the Friedmann equation is essential.

## Gate C verdict

**PASS — conditional mass-gap timescale test.** Under \(m_X=T_c\), \(\tau_X\ll H^{-1}\), so the microscopic X degrees of freedom can in principle equilibrate rapidly enough to follow the phase boundary during BBN cooling.

This does **not** yet prove that the phase transition completes or that it transfers energy to the visible plasma. Three independent timescales must not be conflated:

1. microscopic relaxation \(1/m_X\);
2. critical relaxation / nucleation / bubble-growth time;
3. portal or decay time that transfers latent heat into photons and free-streaming radiation.

Near a critical point, critical slowing down can invalidate \(\tau_X=1/m_X\). A damping coefficient, dynamic critical exponent, nucleation rate and portal collision terms are not supplied by the latent-heat ratio. The assumption \(m_X=T_c\) is also a hypothesis: \(\mathcal L/T_c^4\) alone does not derive the mass gap.

Therefore Gate C is passed for the stated microscopic timescale estimate, not for the complete cosmological phase-conversion and energy-transfer history. The next calculation must derive the X spectral gap and damping from its microscopic Hamiltonian, then calculate nucleation/relaxation and portal rates.

## Reproduction

From repository root:

\`\`\`sh
python analysis/BH1_SU3_RELAXATION_GATE_20261120/verify.py
\`\`\`

Machine results are in [CHECKS.json](CHECKS.json).
