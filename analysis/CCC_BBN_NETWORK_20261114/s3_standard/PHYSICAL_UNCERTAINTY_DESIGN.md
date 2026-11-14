# S3_STANDARD — физические неопределённости: дизайн до исполнения

**Статус:** `DESIGN_ONLY / NOT_EXECUTED / SCIENTIFIC_ACCEPTANCE=false`  
**Родительская модель:** стандартная BBN на зафиксированном PRIMAT `6f7e5680614fb119d65a6c9c65a292240b27c61e`.  
**Назначение:** подготовить воспроизводимый контракт неопределённостей для сравнения стандартной BBN с наблюдениями. Этот документ не меняет физический закон, сетку, допуски S1 и не является likelihood.

## 1. Что уже измерено, а что ещё нет

Результат `S3_INPUT_AUDIT_20261114_r1` содержит локальные секущие по `eta/eta0 = 0.99, 1, 1.01` и коэффициент
`C_eta / Var(ln eta) = J_eta J_eta^T`. Это только чувствительность к одному скалярному входу. В нём нет выбранного распределения eta, дисперсии ядерных скоростей, слабой rate-covariance или совместного likelihood.

Нельзя складывать этот ранг-один коэффициент с опубликованными observational sigma и называть результат полной теоретической ковариацией. Неизвестная `Var(ln eta)` должна приходить из отдельно обоснованного CMB-only анализа; если eta интегрируется как nuisance-параметр в общей модели, её вклад должен учитываться внутри этой модели, а не добавляться второй раз как независимый Gaussian error.

## 2. Наблюдательные входы: версии и ограничения

### 2.1 Дейтерий

Для первичного S3-контракта следует заменить исторический единственный ориентир Cooke et al. (2018), `log10(D/H)_p = -4.5974 ± 0.0052`, на provenance-aware набор первичных absorber measurements, который можно восстановить из таблицы Particle Data Group 2026. В обзоре приведено 12 наиболее точных и недавних измерений и рекомендация
`10^6 (D/H)_p = 25.08 ± 0.29`; авторы увеличили исходную ошибку на `S = 1.08`, так как `chi2/(N−1) = 1.160`. Таблица указывает отдельные absorbers и ссылки на последние оценки, что позволяет не считать повторные публикации одного absorber независимыми измерениями.

Рекомендация PDG — готовая сводка, не замена исходным likelihood каждого absorber. До финальной фиксации нужно:
- сохранить 12 строк, идентификаторы absorber, redshift, metallicity, исходную версию публикации и выбранную последнюю оценку;
- сверить, какие ошибки статистические, какие систематические, и как в PDG применён scale factor;
- проверить повторное использование спектров/систем и не усреднять повторно компиляции, включающие те же absorbers;
- сохранять исходную шкалу каждого измерения (часто `log10(D/H)`) и только затем выполнять точное преобразование. Линейное `D/H` с симметричным Gaussian sigma не эквивалентно автоматически Gaussian в `log10(D/H)`.

Cooke et al. (2018), `log10(D/H)_p = -4.5974 ± 0.0052`, остаётся полезным историческим контрольным входом, но не должен параллельно включаться в likelihood вместе со сводкой PDG 2026: эти источники перекрываются по исходным absorbers.

Отдельный preprint de Grijs & Bono (2026), посвящённый provenance литературы D/H, сообщает, что большая часть опубликованных значений является повторным использованием прежних измерений/компиляций, а не новой независимой абсорбционной системой. Это не новая рекомендация по числу D/H; это предупреждение против псевдорепликации при построении выборки.

### 2.2 Гелий-4

Исторический вход `Yp = 0.2449 ± 0.0040` из Aver, Olive & Skillman (2015) оставить в архивной ветке чувствительности, но не считать единственным современным наблюдательным входом.

Новый кандидат — The LBT Yp Project IV (Aver et al., arXiv:2601.22238; опубликован в 2026): `yp = 0.08146 ± 0.00058` для 15 отобранных низкометалличных H II регионов, после чего авторы используют
`Yp = 4 yp / (1 + 4 yp) = 0.2458 ± 0.0013`.
Заявленная ошибка включает dispersion correction `S = 1.15`. У той же работы есть альтернативный regression result `Yp = 0.2451 ± 0.0022` с другой процедурой и `S = 1.70`; эти два значения нельзя трактовать как независимые измерения и усреднять.

До фиксации likelihood необходимо решить, использовать ли предпочтительный weighted-mean estimator LBT как единый наблюдательный вход или реконструировать likelihood по объектам и nuisance-параметрам. Нужны таблица выбранных объектов, правила screening, эмиссионные коэффициенты, поправки radiative transfer, reddening, underlying stellar absorption, electron temperature/density и их зависимость/ковариация. Указанные 15 H II регионов образуют один однородно обработанный набор, а не автоматически 15 полностью независимых cosmological measurements.

PDG 2026 BBN review приводит рекомендацию `Yp = 0.245 ± 0.003` и прямо предупреждает, что объединение частично перекрывающихся H II наборов не является тривиальным, а систематическая составляющая доминирует. Дата редакции этого обзора — август 2025; он предшествует LBT Project IV 2026 и поэтому не заменяет проверку новой работы. Не усреднять PDG summary и LBT result как два независимых входа.

Конвенция обязательна: если источник даёт number ratio `y = n(He)/n(H)`, перейти к mass fraction по формуле, принятой авторами и в BBN output. В LBT применяется `Y = 4y/(1+4y)`; при ненулевой металлическости авторы отдельно обсуждают `Y = 4y(1−Z)/(1+4y)`. Нельзя молча сравнивать `y`, массовую долю с поправкой на Z и кодовое `YPBBN`.

## 3. Физическая ковариация PRIMAT

### 3.1 Исходные параметры

Для каждого активного канала зафиксировать в машинном реестре:
- имя реакции, направление и обратный канал/detailed-balance связь;
- исходную rate table и SHA256 файла;
- температурную зависимость центральной скорости, единицы и интерполяцию;
- смысл поля error: log-normal sigma, доверительный интервал, оценка модели, рекомендованный scale factor либо placeholder;
- первичное экспериментальное/теоретическое происхождение, энергетический диапазон данных и авторскую функциональную форму;
- группу общих систематик (общая калибровка, нормировка пучка/мишени, stopping power, detector efficiency, common R-matrix/ab initio model и т.п.) и известную межканальную ковариацию.

Сначала нужен аудит реально активных реакций в закреплённой полной сети `large, amax=0` (профиль проекта `full_59_427` — внутренний ID, не имя сети PRIMAT). Не следует автоматически считать все 427 каналов равноинформативными: для каналов с широкими placeholder factors необходимо отдельно маркировать отсутствие измерительной вероятностной модели и проверять, не создают ли они искусственный хвост дисперсии.

### 3.2 Что даёт PRIMAT сейчас

Документация PRIMAT 0.3 описывает `p_<reaction>` как log-normal вариацию `rate = median × exp(p × sigma)`; стандартный Monte Carlo независимо семплирует активные `p_*` из `N(0,1)` и варьирует neutron lifetime. `run_mc()` возвращает sample covariance/correlation для совместных выходов. Следовательно, совместная covariance между `YPBBN`, `D/H` и другими abundance выходами доступна, но это не означает, что неопределённости самих реакций уже имеют физически полную межканальную covariance: независимость семплирования является предпосылкой этого baseline.

Документация также описывает ограничение variation factor через `mc_rate_rescale_cap` (по умолчанию 30) для подавления чрезмерных выбросов у слабо ограниченных/placeholder rate factors. Перед расчётом надо извлечь фактическое значение из закреплённого PRIMAT commit и провести отдельную проверку чувствительности к этому clamp. Нельзя принимать covariance, полученную после скрытого clipping, как неограниченную исходную Gaussian covariance.

### 3.3 Приоритетные физические неопределённости

1. **D/H:** прежде всего `D(d,n)3He`, `D(d,p)T`, `D(p,gamma)3He` и связанные температурные формы. PDG 2026 отмечает, что первые две реакции доминируют в текущем nuclear uncertainty budget и что эмпирический и theory-guided способы задания функциональной формы могут давать заметно разные D/H predictions. Новая работа Launders, Giovanetti & Liu (arXiv:2604.16600) также выделяет эти три реакции как основные рычаги D/H и указывает на важность измерений D+D S-factors в диапазоне 0.1–0.6 MeV. Это задаёт приоритет аудита, но их конкретные параметры/covariance должны быть извлечены из источников, а не подобраны под наблюдаемое D/H.
2. **Yp:** neutron lifetime и слабые `n ↔ p` rates около freeze-out; теоретические поправки (radiative, finite nucleon mass, Coulomb/plasma, thermal и neutrino-sector corrections) должны быть разделены от experimental uncertainty `tau_n`. PDG 2026 приводит `tau_n = 878.4 ± 0.5 s`; эта scalar uncertainty не заменяет rate-theory covariance.
3. **Остальные ядерные каналы:** включать в full-network propagation, но хранить channel-level contributions и sensitivity ranking. Для poorly constrained rates сначала проверить, не являются ли ошибки консервативными placeholders или артефактом формы аппроксимации.
4. **Общая систематика:** при наличии общих экспериментальных источников ввести блоки корреляций между rate parameters. Если источник covariance отсутствует, явно помечать независимое семплирование как provisional baseline; не назначать `rho=0` как установленный физический факт.

### 3.4 Распространение

Для вектора параметров `theta = (ln eta, ln rates, weak-rate parameters, tau_n, ...)` и выхода `z = (Yp, log10(D/H))` вычислять локальный response matrix
`J = d z / d theta`, затем
`C_theory = J C_theta J^T` для обоснованной вероятностной модели физических входов. Численная ошибка сохраняется отдельно как convergence bound; добавлять `C_numerical` допустимо только после обоснования её вероятностной модели, а не из одного solver tolerance.

Разделить и опубликовать компоненты:
- `C_nuclear` — только covariance rate parameters с provenance;
- `C_weak` — uncertainty weak-rate calculation, отдельно от scalar `tau_n`;
- `C_tau_n` — lifetime measurement propagated through the actual code interface;
- `C_eta` — CMB-derived eta covariance, не прежняя проектная ширина ±1%;
- `C_numerical` — solver/grid/cache convergence, измеренная численно, не физическая.
- cross terms, если исходные параметры зависимы.

Локальный Jacobian допустим только после step-size convergence и проверки нелинейности. Сравнить `J C_theta J^T` с прямым correlated Monte Carlo на закреплённом full network; фиксировать seed, backend, sample size, MC error of covariance elements, eigenvalues, rank, correlation matrix и вклад каждого rate block. Число реализаций выбирать по convergence diagnostics, а не объявлять заранее достаточным произвольный N.

## 4. Независимый CMB-вход для eta

Нужен posterior `P(omega_b h^2 | CMB data)` (или совместный `P(omega_b h^2, Yp, Neff, nuisance | CMB)`) с раскрытыми likelihood, dataset, priors и covariance. Нельзя использовать posterior, уже объединяющий CMB с BBN abundances, как независимый prior для того же сравнения.

Особая оговорка: базовый анализ ACT DR6 2025 использует primordial helium fraction по BBN-consistency relation. Его опубликованная комбинация ACT + крупномасштабный Planck + lensing + DESI BAO даёт `omega_b h^2 = 0.0226 ± 0.0001`, но это не готовый независимый CMB-only prior для проверки BBN: и состав данных шире CMB-only, и helium fraction фиксируется BBN-consistency. Для S3 требуется либо CMB likelihood с `Yp` свободным (с сохранением covariance `omega_b–Yp`), либо ясно обозначенная альтернативная модель и анализ того, какая BBN-зависимость остаётся. Если использовать ACT/Planck chains, сохранить точную конфигурацию и исходные цепи/likelihood; не копировать только marginal sigma.

## 5. Совместная статистическая модель

Первичная наблюдательная шкала:
`z_obs = (Yp, log10(D/H))`.
Теоретическая шкала должна быть приведена к той же convention до вычисления residual.

Предпочтительный вариант — явные nuisance parameters и их priors/likelihoods. Только если такой уровень исходных данных недоступен и это явно оговорено, допускается сжатый multivariate Gaussian:
`r = z_obs − z_BBN(theta)`,
`C_r = C_obs + C_theory`,
с отдельной записью причин каждого блока. Нулевые off-diagonal covariance нельзя подставлять только ради удобства. Нельзя включать одну и ту же неопределённость одновременно как параметр nuisance и как добавку в `C_theory`.

Не вычислять `chi2`, p-value, Bayes factor или «tension sigma» до завершения этих контрактов. Два исторических числа из `S3_INPUT_AUDIT` и матрица `J_eta J_eta^T` не являются готовым likelihood.

## 6. Gates перед любым вычислительным S3

- [ ] Зафиксированы source commit, сетка, конфигурация, активные каналы, cache identities и хеши всех физических входов.
- [ ] Для каждого rate документированы центральная функция, uncertainty semantics, первичный источник и covariance provenance; placeholders отмечены отдельно.
- [ ] Проанализированы D+D и D(p,gamma)3He данные/функциональные формы; выполнен отдельный аудит weak rates и `tau_n`.
- [ ] Заданы и обоснованы rate covariance blocks; отсутствие данных не замаскировано диагональной матрицей.
- [ ] D/H dataset построен на absorber-level provenance; повторные публикации и компиляции устранены как дубли.
- [ ] Yp source/estimator, sample selection, (y \to Y) convention, shared atomic/model systematics и covariance зафиксированы.
- [ ] CMB input является действительно заявленным CMB-only likelihood/posterior; BBN consistency and free-`Yp` assumptions раскрыты; BBN-conditioned posterior не переиспользован.
- [ ] Jacobian converged, MC covariance converged, numerical covariance отдельно измерена; все covariance matrices symmetric PSD within documented numerical tolerance.
- [ ] Только после этого зафиксированы likelihood, priors, nuisance model и joint residual statistic.

## 7. Ограничения исполнения

На момент подготовки `S3_INPUT_AUDIT` очередь отмечена `BUDGET_WAIT` до 2026-11-15 14:09:29 UTC. Этот документ — подготовка контракта, а не новый compute package. Не запускать повторный BBN/Monte Carlo сейчас, не менять S1 tolerances, не создавать `RUN_REQUEST`, не переводить `S3_STANDARD` из contract в executed/accepted. Научная приёмка остаётся false.

## 8. Источники, закреплённые для первичного аудита

- Particle Data Group, *Review of Particle Physics 2026*, §24 “Big Bang Nucleosynthesis”, revised August 2025; PDF dated 1 June 2026. В частности, таблицы 24.1–24.2 и разделы 24.2–24.3. https://ccwww.kek.jp/pdg/2026/reviews/rpp2026-rev-bbang-nucleosynthesis.pdf
- PRIMAT 0.3 documentation, “Rate variation and Monte-Carlo uncertainty” and API reference. https://primat.readthedocs.io/en/stable/howto/rate-variation-mc.html
- Aver et al. (2026), *The LBT Yp Project IV: A New Value of the Primordial Helium Abundance*, arXiv:2601.22238, DOI: 10.3847/1538-4357/ae879b. https://arxiv.org/abs/2601.22238
- Cooke, Pettini & Steidel (2018), *One percent determination of the primordial deuterium abundance*, arXiv:1710.11129v3. Historical benchmark only. https://arxiv.org/abs/1710.11129v3
- de Grijs & Bono (2026), *Thirty years of primordial deuterium abundances: A provenance-aware statistical reanalysis*, arXiv:2611.02289. Preprint/provenance audit, not a new abundance recommendation. https://arxiv.org/abs/2611.02289
- Louis et al. (2025), *The Atacama Cosmology Telescope: DR6 Power Spectra, Likelihoods and ΛCDM Parameters*, arXiv:2503.14452. https://arxiv.org/abs/2503.14452
- Launders, Giovanetti & Liu (2026), *A data-driven prediction for the primordial deuterium abundance*, arXiv:2604.16600. https://arxiv.org/abs/2604.16600

## 9. Ручной source/analytic audit от 14 ноября

[Отчёт и воспроизводимый экстрактор](manual_covariance_20261114/REPORT.md), задача #55. Закреплённые исходники и пять priority/placeholder tables проверены по SHA256. Установлены смысл `error=exp(sigma_log)`, independent-channel/one-parameter temperature model, detailed-balance связь, аналитический эффект cap=30 для f=10 и отличие p-response от uniform-rate response. Отдельно выявлена конечнопошаговая нормировка sensitivity helper; ранее полученный S_ETA использовал собственный корректный endpoint interval.

Это частичное закрытие source/semantics вопросов, не полный аудит 427 каналов и не covariance abundances. Межканальные и температурные posterior correlations, weak-theory covariance и observational/CMB gates остаются открыты. BBN/MC не запускались; execution и scientific acceptance не меняются.

## 10. Связь с фазовым сектором Anthropic

[Проработка S3–BH1](bh_bridge_20261115/REPORT.md) и [машинный контракт](bh_bridge_20261115/BRIDGE_CONTRACT.json), задача #56. Отдельный `S3_BH_BACKGROUND` зависит от `BH1` и `S3_STANDARD`: фоновый эффект при фиксированной SM-микрофизике не требует закона дрейфа S2. Прежний S3_EXTENDED сохраняет зависимость от S2_PREDICTION.

Получены условный запрет expansion-driven crossing для изолированного адиабатического конформного сектора с R proportional to a и связь поздней фотонной энтропии с eta и Neff_nu. Старый S_eta переиспользован только для eta-компоненты отклика; новый BBN/BH1 не запускался. Физическая идентификация X/R, полная энергия, триггер перехода, collision terms и кинетика остаются открыты. Контракт не допускает автоматическое исполнение, не меняет CONTROL/CURRENT/RUN_REQUEST или бюджет.
