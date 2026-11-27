# SCALE-09: уточнённый словарь носитель / оператор / наблюдаемая / независимые входы

| Донор | Ветвь и наблюдаемая | Входы | Граница |
|---|---|---|---|
| Cassé | ballistic K, AB transport, одна радиальная подзона | r, независимая материальная m* | Δ13 прогноз, не измеренный модовый holdout |
| Fuhrer | многоподзонное кольцо, Coulomb-blockade addition spectroscopy, constant-interaction extraction | AB ΔB, lever arm, EC; m* не same-device | w≈65 nm, Δ≈180 μeV после EC; явные моды/ковариация OPEN |
| Keyser | K/contact crossover, AB гармоники и добавление | r, материальная m*, контактный режим | назначение гармоник и переходов OPEN |
| Bleszynski-Jayich | diffusive Thouless E_Th, persistent current | witness D и C | не ballistic K, не одна D для всех r |
| Na/Rb BEC | циркуляция, фазовый слабый контакт | атомная масса, радиус | GPE/interaction, не одночастичный спектр |
| Münning/Cho TI | линейная D, Berry π, flux seam/subband/transport | vF, окружность, поток | явный U_TI и граничная форма R132 OPEN |
| Debbarma | орбитальная чётность/AB π, avoided crossings, g_orb | поток, lever arm, l (независимость надо проверить) | структурный аналог интерференции, не тождественный R133 H |
| CR/SdH | циклотpонная масса/температурное затухание | B,T,f, sample provenance | Kriisa — иной Hall bar; same-wafer/device не доказаны |
| Орбитальная магнитометрия | наклон E(B), известный l | независимое l, lever arm, поле, confinement | METHOD_FOUND_WITH_SCOPE; масса условна |
| X/R135 | неизвестный физический носитель, условное K-вложение | M,ℓ назначены | TARGET_X OPEN; no calibration from BBN |

Первичные источники и ограничения: [донорский аудит](DONOR_AUDIT_20261126.md), [ревизия](REVIEW_20261127.md), [holdout](SCALE10_HOLDOUT_PREREG.md). Для каждого будущего измерения записать source/version/sample ID, Hilbert space, H, phase convention, mapping U/observable/projector, preparation/probe, energy units, covariance, independent inputs, scope/negative control. Статусы FOUND означают наличие донора, а не доказанный операторный изоморфизм.

## Массивная дисперсия и голономия (27.11.2026)

Новый conditional Rel donor mapping: massive D_M positive branch на свободном кольце, TI — линейная D и Berry-фаза (не X); Debbarma — контроль contact/parity; Roy — programmable six-site open chain (не замкнутый портовый носитель); persistent current — ∂F/∂Φ, не прямой Gibbs contrast. Различить f(K)+V и f(K+V), измерить физические M,J,C независимо. Никакой физической приёмки. [Доказательства, код и донорский паспорт](../relativistic_holonomy_20261127/REPORT.md).

## Программа LAB (27.11.2026)

Добавить два кандидата: momentum-state ring (Li 2022 ladder, Gou 2020 dissipative ring — не полный R150, J=ℏΩ/2 при указанной two-level convention, импульсный шаг ≠ ℓ); real painted ring + azimuthal lattice + side port (Bell/Gauthier — предшественники, не полная комбинация). J_width≠J1 автоматически; deep-lattice formula asymptotic; при s=4.463 численно J_width/E_R=.0761682, равенство 1/π² при s≈3.401819. TI retrospective desk-study: E_edge=(ℏv_F/R)min_l|l+1/2−Φ/Φ0|, full gap=2E_edge; independent v_F, geometry/flux, sample lineage, lever arm, Zeeman, band bending and oxide; U_TI/spinor/domain OPEN. TI не единственный D-аналог. GaAs: same-device/same-wafer independent mass, lever arm, mode identity and multi-subband/interaction systematics; predicted Δ13 not observed. TOF populations not automatically A_ab(ω), common reference needed for C_hol. Все новые ссылки — candidate metadata, физические данные не приняты. [Аудит](MODEL_LOCK_REVIEW_20261127.md) · [MODEL-LOCK](MODEL_LOCK.md).

## Важный результат / ограничение: winding, long-range и полнота следа (27.11.2026)

For optical ring, separate Fourier J1 and quarter bandwidth J_width (s_F=3.35203828, s_width=3.40181871). Signed J2…J6, winding and band scope must be independently calibrated. A finite synthetic ring can realize winding links only with explicit phase/path convention; sinusoidal J_r are correlated, not independently programmable. Direct C error and band leakage/precision, port equilibrium and full spectral weights required. T^-1 nonunique. 09-LAB-LONG-RANGE-B OPEN. [Общий отчёт, данные и replay](long_range_20261127/REPORT.md).
