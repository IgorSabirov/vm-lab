# R149–R150: winding harmonics, дальние перескоки и полнота голономического следа (27.11.2026)

**Важный результат / существенное ограничение.** MODEL_PASS_WITH_SCOPE; LAB физический оператор и межзонная полнота OPEN; X OPEN; scientific_acceptance=false. PR #222, baseline e77f53af4f220053521e8a29b2cd4bdc23ca4b3a. Основание: представленные владельцем 27.11 блоки кода, выводы и соседская рецензия (архив «Вставленный текст(20261127-061042).txt»), предыдущий [MODEL-LOCK](../MODEL_LOCK.md). Малый независимый численный replay повторён 27.11 на локальном CPU для проверки публикации (не новый физический эксперимент). [replay.py](replay.py), [RESULTS.json](RESULTS.json). Исходное число 3.41e−6 не таргет. Единицы: k_B=1, E_R и J1 — энергии; общий нуль энергии дна первой зоны и изолированного порта при обеих фазах.

## 1. Реальная оптическая дисперсия и нормировка (R130/R132/R150)

V=V0 sin²(k_L x), s=V0/E_R; H_nn/E_R=(2n+κ)²+s/2, H_n,n±1/E_R=−s/4. Signed Fourier convention H=E_offset I−Σ_{r≥1}J_r(S_φ^r+S_φ^{†r}), J_r=−mean E(κ)cos(rπκ). S spatial shift; это не утверждение о физических часах F. В разности от дна ε=2Σ J_r(1−cos rq), q=πκ. При полном Fourier ряде J_width=(E(1)−E(0))/4=Σ_{r odd}J_r (равенство J_width=J1 только при нулевой сумме остальных нечётных гармоник; чистый косинус — достаточное условие).

| Условие | s | J1/E_R | J_width/E_R |
|---|---:|---:|---:|
| J_width=1/π² | 3.40181871215 | .10001247 | .101321184 |
| J1=1/π² | 3.35203828064 | .101321184 | около .10269 |

Deep lattice formula при s_width ≈.14133 E_R (39.5% выше target), descending root ≈4.4633 — не точная калибровка. При s_width J2/J1=−8.806%, J3/J1=1.264%; при s_Fourier: J1…J12/J1 = 1, −.0895673535, .0130843932, −.00232033450, .000456704308, −.0000959440614, .0000210746646, −.00000478168562, .00000111198492, −.000000263645691, .0000000634919924, −.0000000154880181. Кривизна относительно NN: Σr²J_r/J1≈.73112418. J1 из ширины и Fourier различаются ~1.29% при s_width. Согласование одного масштаба не определяет оператор. В обычной синусоидальной решётке J_r зависимы от одного s; независимое управление дальними перескоками требует собственной реализации (синтетические связи/другая форма потенциала). Не смешивать winding на накрытии и короткую хорду.

## 2. ВАЖНО: обобщение первого различающего момента R149

N=6, φ=0,π; ε_m(φ)=2Σ_{r=1}^R J_r[1−cos(r(2πm+φ)/N)]. Δ_p=Tr H_π^p−Tr H_0^p. На универсальном накрытии каждый множитель даёт сдвиг ±r или 0. В следе остаётся суммарное смещение wN; смена фазы даёт (−1)^w, поэтому вклад различается только при нечётном w. Если pR<N, такого пути нет. **p*≥ceil(N/R)** (при отсутствии различия p*=∞); равенство для полного набора допустимых r и ненулевого суммарного коэффициента минимального winding, не для произвольных J_r (возможны отсутствующие шаги и компенсации). Здесь проверены:

| R | p* | Δ_p*/J1^p* | sign leading C |
|---|---:|---:|---:|
| 1 | 6 | −24 | + |
| 2 | 3 | −.01724489159 | − |
| 3 | 2 | −.00410883231 | + |
| 4 | 2 | −.01408449091 | + |
| 5 | 2 | −.03600629768 | + |
| 6 | 1 | −.00230265747 | − |

Дальность здесь — на накрытии; r=N — полный обход, возвращающийся в тот же узел; r=4,5 на N6 не обычные кратчайшие соседи. Фазовое сворачивание S^N=e^{iφ}I: для полного Fourier ряда **Δ1=4NΣ_{l≥0}J_{(2l+1)N}** (абсолютная сходимость, общий нуль, действительные J_r). След суммы cos исчезает кроме r, кратных N, чётные winding сокращаются. Для N6 J6/J1≈−9.5944e−5, Δ1/J1≈−.0023026575; r=18,30,… дают малые поправки, не тождественно ноль.

Ξφ=1+Tr exp(−Hφ/T), iso C=1−Ξπ/Ξ0. При фиксированном конечном числе состояний C~(−1)^(p*+1)Δ_p*/[(N+1)p*!T^p*]; free N вместо N+1. Порт имеет одинаковую энергию и кратность; 1 — опорное состояние, не автоматически вакуум/газ. **T^-1 не уникальный маркер Rel:** NR long range даёт тот же порядок; исходный NN NR T^-6 vs NN f(K) T^-1 верен в своём классе. Порядок момента управляется winding и дальностью, не только дисперсией. Полный континуум бесконечномерный: конечномерное разложение следа степеней неприменимо автоматически. Для свободного круга после Пуассона winding w имеет вес exp(−π²w²/(β E_L)); при β→0 фазовое различие экспоненциально мало. Не переносить на все потенциалы/динамические носители без доказательства.

## 3. Четыре модели и спектральный holdout

N=6, M/J1=15.85/3.08622708259639589, f(x)=sqrt(M²+2Mx)−M в J1 units. NN NR, NN f(K), Optical NR projected lowest band, Optical f(K) projected lowest band. Последняя — функциональное исчисление, НЕ автоматически физический релятивистский гамильтониан с внешним потенциалом.

| Model | R_a | R_p |
|---|---:|---:|
| NN NR | 1 | .5 |
| NN f(K) | .822264366 | .431547255 |
| Optical NR | 1.356214004 | .681765755 |
| Optical f(K) | 1.108302631 | .577641650 |

| T/J1 | NN NR iso | NN f(K) iso | Opt NR iso | Opt f(K) iso |
|---:|---:|---:|---:|---:|
| .1 | .431427813 | .426746105 | .363540832 | .358553000 |
| .15 | .333272499 | .326302987 | .238863114 | .233952934 |
| .2 | .243142296 | .236800437 | .147500662 | .145324311 |
| .3 | .120771142 | .119673658 | .052161950 | .055270393 |
| .5 | .029833042 | .034172957 | .006483017 | .010211725 |
| .7 | .008632905 | .012439840 | .000911824 | .002772430 |
| 1 | .001821331 | .003931659 | .000058181 | .000666976 |
| 1.5 | .000244060 | .001062355 | 7.126e−7 | .000142200 |
| 2 | 5.23248e−5 | .000443065 | −4.133e−7 | 5.03393e−5 |

At t=.2, |C_NN_NR−C_Opt_NR|/|C_NN_NR−C_NN_f|≈15.08. Opt f ratio closer to NN NR than NN f for R_a; not proof that four models cannot be discriminated. Need multi-phase absolute mode IDs and joint covariance. For independent 1% errors in each AP level referenced to common known band minimum, gradient (R,−1−R,1)/(E3−E1), NN NR σ_R=.03162278 and conditional separation .1777356/σ≈5.62 (not 6.6); common middle level induces correlated gaps. Not universal error budget. Port-off calibrate J1…Jr/uncertainties, held-out phases and contact/temperature; simultaneous model predictions before data.

## 4. ВАЖНО: проекция может менять знак голономического контраста

First band zeros (bracket 1.5…10): t_NR≈1.70835, t_f≈3.82412. Отрицательный однозонный контраст подтверждён при t=1.8,2 (NR); t=5,10,… (f); не утверждать единственность нулей на всех T без доказательства. Higher bands: lowest second band energy above common minimum =20.41685538 J1, first band maximum=4.05425341 J1.

| T/J1 | first band NR | multiple bands NR |
|---|---:|---:|
| 1.5 | +7.126e−7 | +7.485e−7 |
| 1.8 | −1.369e−7 | +5.718e−8 |
| 2 | −4.133e−7 | +1.030e−8 |

At t=2 omitted Boltzmann scale exp(−20.4169/2)≈3.7e−5; projection error ≈41× full contrast even though omitted occupation small. For full scalar Schrödinger H with real periodic potential and minimal magnetic coupling, common E0, same isolated reference, diamagnetic heat-kernel inequality implies Tr exp(−βHπ)≤Tr exp(−βH0), hence C_full≥0. Applies to full scalar operator, not band projections, signed hopping or spinor/contact Hamiltonians generally. This is a mathematical sign control, not resolved value at double precision. Numerical negative first-band result is not negative full physical contrast. Reference from supplied review: Erdős, Loss, Vougalter (diamagnetic heat-kernel inequality); no new literature claim or physical donor acceptance made here.

Exact discarded-sector error if retained sums Zφ^(B) and omitted Dφ≥0 include common reference consistently: C_full−C_B=[(1−C_B)D0−Dπ]/(Z0^(B)+D0). Require absolute bound on this difference, not only small Dφ/Zφ. Cutoff study in RESULTS; increasing number of plane waves ≠ number of physical bands retained. Both controls required. Define epsilon_C before unblinding as small fraction of smallest relevant model separation; sign claim also require error below |C| with margin; compare tail, numerical precision, calibration and systematic uncertainty. At t≥3 numerical cancellation in NR full can reach precision floor; do not report sign/magnitude from noise. For arbitrary H2 domain M²I+2MH≥0; f(H_NR with V) differs physically from f(kinetic)+V. No automatic relativistic physics. This extends R132/R133's observable-specific limits and R135's physical projection contract.

## 5. Historical point / X (R135/R142/R150)

t=80/3.08622708259639589=25.9216181632, same dimensionless M/J as legacy. NN NR +1.55027e−11; NN f +3.40920e−6; Optical NR one band −9.12684e−6; Optical f one band −4.24251e−6. Since t exceeds second-band threshold 20.4169, one-band assumption not controlled. Full multi-band NR sign/value unresolved in double precision (cut 14..42 approximately ±5e−13; analytic C≥0). Full spectral f converges numerically ≈+1.27624e−7 with cut 30–42 (see cutoff table); conditional model only, not physical Rel. Contrast order 10^-6 does not determine microscopic carrier or identify X. Original M,ell selection OPEN; no new PRIMAT/LINX or BBN calculation; not a target or independent holdout.

## 6. Port readout, Fréchet and idealized power

With common isolated port E_p=0, pφ=1/Ξφ, C_iso=1−p0/pπ; Z_ring=(1−pφ)/pφ. Need prepare canonical equilibrium over port+cycle (e.g. equilibrate/couple then decouple without changing target populations; validate preparation); isolated state alone does not thermalize. For 100 shots each 50k independent atoms per phase n=5e6, first-order binomial σ_C=(p0/pπ)sqrt((1−p0)/(n p0)+(1−pπ)/(n pπ)). Under NR null, |C_f−C_NR|/σ_C is expected standardized separation, not measured significance or guaranteed power. At .2,.3,.5,.7,1,1.5,2 NN values ≈15.1,2.03,6.35,4.96,2.46,.84,.37σ; 1000 shots multiply sqrt(10). Local maxima from bounded searches (.02,.3) and (.3,.9): NN (.13670983,20.5380), (.51527873,6.36682); Optical (.10327029,15.55181), (.37691712,6.39790). NN NR/Rel crossing ~.32144; optical ~.23397. Correlations, interactions, calibration, preparation, thermometry, loss, systematics, multiple selection, readout efficiency not included; preregister prospective power with independent inputs; no experimental claim.

Daleckii–Krein derivative: Df_K[V]_ij=2Vij/(sqrt(1+2λi/M)+sqrt(1+2λj/M)), including equal eigenvalues λi=λj (not merely i=j). Scalar controls (a,b)=(.8269,6.1725),(2,11.518),(3,3) keV give .838709,.744763,.851704. For N6 K spectrum 0,1,1,3,3,4, seed 7 symmetric random V, eps=1e−5, closed vs secant 5.55e−16 supplied; forward matrix derivative max discrepancy 8.25030e−6 (reproduced). This is a mathematical matrix test, not full port/contact experiment. L=7 full family 13 passive×7=91, 5 active×7=35, total 126=3L(L−1); count, not generations proof.

## 7. Registry and gates

09-LAB-LONG-RANGE-A MODEL_PASS_WITH_SCOPE: winding proof, coefficients, moments, first-band sign, four-branch negative control. 09-LAB-LONG-RANGE-B OPEN: physical operator completeness, populations, band/precision convergence, independent J_r covariance and explicit probe, diamagnetic control where applicable; finite-dimensional synthetic ring may not require continuum bands but leakage must be bounded. Both tied to MODEL-LOCK and SCALE-10. **Revoke uniqueness of T^-1 as general discriminator**; preserve conditional theorem, add alternatives and control directly C. Full flux sweep, port-off/on, spectral weights and joint covariance; do not interpret single ratio or power as physical confirmation. Controlled varying J_r is candidate, not established in sinusoidal potential. No scientific acceptance; SCALE-09–12, 09-X, U006/U010, Gate D unchanged. No automatic merge.

## Уточнение следующего прохода — operator identifiability (27.11.2026)

[Новый отчёт и replay](../operator_identifiability_20261127/REPORT.md) уточняет, не заменяя long-range результаты: f(K_NN) тождественно positive Fourier hopping при всех φ; J_N aliases relative scalar detuning, AP antipode zero is reflection protection, weighted Wilson cancellations matter. **Iso = one-particle canonical port+cycle; 1 is the actual zero-energy port, not vacuum.** Arbitrary free LR can exactly mimic f; require independently calibrated intervention family. Complex seam dtype mandatory for intermediate phases; 0/π controls unaffected by previous real cast. Common-zero optical Δ2/J1²=−.04552745166, numerator term equality t≈9.88585. 09-LAB-OP-IDENTIFIABILITY OPEN_PHYSICAL; all prior physical statuses retained.
