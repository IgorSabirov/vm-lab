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
