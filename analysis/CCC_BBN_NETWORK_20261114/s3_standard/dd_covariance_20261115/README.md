> **Действующее решение 16 ноября 2026:** [площадку выбирает владелец; временного потолка нет](../../../../COMPUTE_AUTHORITY.md). Гейт времени — калибровка, прогноз и план/факт. Прежние временные ограничения и маршрутизация в тексте ниже отменены; факты прошлых запусков сохраняются.

# S3 D+D: local covariance-response package

**ID:** S3_DD_RESPONSE_20261115_r1  
**Status:** preregistered package; no integrations in this repository revision.  
**Scientific acceptance:** false.

## Question

At a standard BBN background and fixed non-D+D reaction rates, how do the two LINX D+D rate-uncertainty directions change the four late-time abundance observables? The package measures the local response and derives a first-order covariance ratio as a function of the unknown inter-channel correlation rho.

## Inputs and semantics

The package pins LINX bfba07c77a5fcba1cc772d42f2d9e9be8a542df8, key_PRIMAT_2023, the existing dd_adapter.py and its rate_tables_override patch. For each channel the upstream table's third column is f_i(T)=expsigma_i(T). LINX's actual parameter is one scalar q_i shared over the entire table:

r_i(T,q_i) = mu_i(T) * exp(q_i * ln(f_i(T))).

The implementation must use this temperature-dependent table on the existing nodes. It must not apply an additional nuclear_rates_q multiplier after table replacement. The reverse rate remains the upstream detailed-balance transform of the same forward table.

## Integration matrix

There are nine BBN integrations:

1. One native baseline with q=0 for every active reaction. It creates the shared standard background.
2. For ddHe3n: q=-1,+1,-0.5,+0.5.
3. For ddtp: q=-1,+1,-0.5,+0.5.

All eight perturbation runs reuse the same background, reaction network, weak sector, initial conditions, solver, tolerances and upstream inputs. The non-varied D+D channel and all other reactions remain at q=0. Integrations execute sequentially, each with a 600 s hard wall cap. After Run 0, the worker records its measured wall time and an eight-run forecast before starting the remaining tasks. No automatic retry or unbudgeted smaller-step rerun is allowed.

## Observables

- D/H = Y_d/Y_p.
- Yp = 4 Y_He4.
- Late 3He/H = (Y_He3+Y_t)/Y_p, accounting for tritium beta decay.
- Late 7Li/H = (Y_Li7+Y_Be7)/Y_p, accounting for Be7 electron capture.

The ratios are evaluated from the final LINX abundance vector. The hydrogen denominator is the free-proton abundance used by this network output.

## Local propagation

For observable O, the response is a_i(O;h)=[ln O(+h)-ln O(-h)]/(2h). We report both h=1 and h=0.5 estimates, their per-direction step discrepancy, and

kappa = 2*a1*a2/(a1^2+a2^2),

sigma_corr/sigma_indep ~= sqrt(1+kappa*rho).

R(rho)=[[1,rho],[rho,1]], rho in [-1,1], is only a parameterized correlation family with unit Gaussian marginals. The pinned input audit did not provide joint D+D posterior samples or a measured correlation. rho=0 is a comparison case, not a physical independence claim. This is a delta-method result for ln O; it is not an exact nonlinear BBN covariance or a posterior for rho.

## Directional hypotheses

The signs for D/H, late 3He/H and late 7Li/H are preregistered as directional expectations only. A sign mismatch is a diagnostic of net network flow, not an automatic software failure. No sign is preregistered for Yp. For Yp, report the absolute D+D contribution a1^2+a2^2; kappa alone is scale-invariant and cannot represent the size of the effect.

## Reuse of the previous adapter identity pair

The prior r3 strict native/override arms are not used as the new science baseline: their other-reaction q values were nonzero deterministic controls. They can only document that the table override mechanism reproduced the native rate tables and final output at that prior control point. The new Run 0 is an all-reaction q=0 native BBN baseline.

## Out of scope

No GP posterior, correlated Monte Carlo, experimental determination of rho, full 427-channel covariance, CMB/BBN/FIRAS likelihood, BH1, S2 microphysics drift or scientific acceptance. A later nonlinear correlated Monte Carlo can test the local approximation after a physically sourced rho distribution exists.