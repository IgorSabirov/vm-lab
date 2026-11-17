# PRIMAT + LINX как два вычислительных backend нашего BBN bridge

Дата: 17 ноября 2026  
Родительская физическая спецификация: `analysis/CCC_BBN_NETWORK_20261114/s3_standard/bh_bridge_20261115/BRIDGE_CONTRACT.json`  
Статус: `COMMON_INTERFACE_SPECIFIED / BACKEND_COUPLING_NOT_IMPLEMENTED / BBN_NOT_EXECUTED`  
Научная приёмка: `false`

## 1. Назначение

PRIMAT и LINX должны быть не «мостом друг к другу» и не двумя независимыми графиками. Это два независимых вычислительных backend одного и того же физического BBN-входа, полученного из космологического bridge BH1 → X-sector → background → BBN.

Общий мост задаёт одну физическую историю и один набор входных физических предпосылок. Адаптеры переводят их в нативные API PRIMAT и LINX. Оба решателя возвращают abundances и диагностические истории. Сравнение выполняется только на совпадающей области сети, входов и определений наблюдаемых.

Схема:

```
BH1 thermodynamics + X-sector model
                 |
                 v
      COSMOLOGICAL BACKGROUND
      a(t), H(t), T_gamma(t), n_b(t),
      neutrino distributions, energy transfer
                 |
                 v
        CANONICAL BBN HISTORY
       + nuclear-rate realization
                 |
          +------+------+
          |             |
          v             v
       PRIMAT          LINX
       adapter         adapter
          |             |
          v             v
     abundances     abundances
          +------+------+
                 |
                 v
      COMMON OBSERVABLE / RESIDUAL
      and cross-backend validation
```

Это целевая архитектура, а не утверждение, что адаптеры уже реализованы.

## 2. Общий вход: Canonical BBN History

Вводится единый версионируемый объект `BBNHistory`. Все массивы относятся к одной физической временной сетке и имеют общий SHA-256 манифест. Минимальные поля:

- `time_s`: физическое время, секунды, строго возрастающая сетка;
- `scale_factor`: масштабный фактор с объявленной нормировкой;
- `H_s_inv`: скорость расширения, s^-1;
- `T_gamma_MeV`: фотонная температура, MeV;
- `n_b_cm3`: физическая барионная плотность, cm^-3;
- `f_nu_e`, `f_antinu_e`: электронные нейтринная и антинейтринная спектральные функции либо строго определённый эквивалентный набор моментов;
- `T_nu_MeV`: только если спектр действительно описывается термальным распределением;
- `phase_state`, `rho_X`, `p_X`, `Q_Xem`, `Q_Xnu`, `Q_emnu`: provenance/диагностика источника и передачи энергии;
- `comoving_entropy`: диагностическая величина с явным сектором и определением.

Не допускается подмена нейтринных спектров одним суммарным (N_{eff}), если модель использует неравновесные спектры. Не допускается независимо пересчитывать (H), (T_gamma), (n_b) в каждом backend: они должны поступать из одной истории.

Валидация истории: конечность; единицы; общий размер массивов; монотонность времени; согласованная нормировка (a); отсутствие неоговорённых скачков; проверка уравнений энергетического баланса и Friedmann на стороне генератора истории. Монотонность (T_\gamma(t)) не предполагается автоматически: если backend не поддерживает немонотонную температуру, такой участок должен быть явно исключён условием области применимости, а не молча переставлен или интерполирован.

## 3. Ядерный вход и идентичность

Отдельный объект `NuclearRateSet` содержит:

- именованный каталог реакций и нуклидов;
- (T_9)-узлы и значения скоростей с размерностями;
- соглашение о прямых/обратных реакциях и detailed balance;
- неопределённости и covariance с идентичностью их источника;
- единицы, интерполяцию, хвосты вне табличного диапазона;
- фиксированный порядок реакций и SHA-256 каждого массива.

Один физический rate realization передаётся обоим backend. Нельзя считать одинаковыми два входа только потому, что совпадают имена реакций: проверяются значения, узлы, единицы, порядок и правила detailed balance.

### Область сравнения

LINX-адаптер сейчас документирован для `key_PRIMAT_2023`: 8 нуклидов и 12 реакций; D+D-внешний override меняет две таблицы, сохраняя остальные штатные скорости. PRIMAT документирует small (8 нуклидов, 12 ядерных реакций), large_a8 и large (59 нуклидов, 427 ядерных реакций).

Для PRIMAT small и LINX key_PRIMAT_2023 уже построена машинная таблица соответствия имён и стехиометрии: `NETWORK_MAP.json`. Совпадают 8 видов и 12 направлений реакций; `a` в LINX соответствует физическому He4. Это подтверждает топологическое соответствие сети, но не тождество таблиц скоростей, Q-values, единиц, интерполяции и неопределённостей. Сравнение full-network PRIMAT с 8/12 LINX не является тестом идентичности решателей. Для полной сети требуется расширить LINX или ограничить PRIMAT строго тем же подграфом и доказать корректность замыкания сети.

## 4. Два backend-контракта

### PRIMAT adapter

Точка входа upstream: `primat.backend.run_bbn(params)`. Версия закреплена: `6f7e5680614fb119d65a6c9c65a292240b27c61e`.

Адаптер обязан:
1. Запустить pinned upstream без изменения авторских таблиц.
2. Принимать каноническую историю только через реально поддерживаемый Python `background=` интерфейс.
3. Явно фиксировать режим weak-rate cache. При изменённой нейтринной истории использовать `weak_rate_cache=False` и `save_nTOp=False`, чтобы исключить кеш слабых скоростей от другой истории.
4. Не использовать табличный `custom_background` как эквивалент полного нейтринного фона: документированный путь отключает incomplete decoupling и spectral distortions.
5. Возвращать abundances, временную/температурную историю, solver diagnostics и полный input receipt.

### LINX adapter

Точка входа и API-патч берутся только из закреплённого PR #57 / LINX commit `bfba07c77a5fcba1cc772d42f2d9e9be8a542df8`.

Адаптер обязан:
1. Сохранить upstream pristine-копию и единственный разрешённый API override отдельно.
2. Передать общий `BBNHistory` в LINX только через проверенный native API; текущий D+D adapter сам по себе не является адаптером произвольного космологического фона.
3. Передавать две D+D-скорости через существующий `rate_tables_override`, сохраняя все прочие q/rates и detailed balance.
4. Проверить поддержку временной сетки, нейтринных спектров и возможной немонотонности температуры. Отсутствующая возможность маркируется как backend capability gap, не имитируется.
5. Возвращать те же классы выходов и полный input receipt.

## 5. Уровни проверки — строго по порядку

**B0 — нативные эталоны.** Каждый решатель воспроизводит собственный стандартный контроль по исходной документации. Это проверка backend, не сравнение между ними.

**B1 — одинаковая малая сеть.** Проверить точное соответствие PRIMAT small ↔ LINX key_PRIMAT_2023. Сравнить реакции и нуклиды, затем одинаковые rates, weak sector, initial conditions, cosmology и единицы. Если точного совпадения нет, сначала документировать минимальный общий подграф.

**B2 — identity override LINX.** Исполнить уже подготовленную пару `native_pristine` / `identical_override` по замороженному `BBN_IDENTITY_CONTRACT.json`. Это проверка адаптера, не физическая валидация PRIMAT.

**B3 — общий background.** Подать одну и ту же сериализованную `BBNHistory` обоим backend. До интеграции подтвердить, что оба адаптера реально используют все обязательные компоненты, а не только одинаковое (H(T)). Если нейтринная часть не может быть общей, сравнение маркируется как conditional и не выдаётся за cross-validation.

**B4 — общий nuclear-rate realization.** Один и тот же вектор скоростей/covariance по общим реакциям передаётся обеим системам. Сначала deterministic control, затем ансамбль/GP. PRIMAT и LINX не должны независимо генерировать «одинаковые» случайные реализации из разных priors.

**B5 — BH1/CCC physical history.** Только после фиксации физического embedding и полного набора (H,T_\gamma,n_b,f_\nu,Q) прогонять сценарии NULL, DECOUPLED, CONFORMAL, ENERGY_BARYON, LATE_PHOTON, NU_SPECTRUM и NUMERICAL из родительского контракта. Сценарии, которые не поддерживаются обоими backend, остаются отдельными, а не смешиваются в одном сравнении.

## 6. Сравнение и критерии

На каждом уровне сохраняются:
- полный вектор abundances по именам нуклидов;
- (Y_p), D/H, He3/H, Li7/H и Be7/H с однозначными определениями;
- история abundances по общей физической сетке либо правила её сопоставления;
- conservation residuals, solver steps/rejections и convergence diagnostics;
- hashes истории, rate set, contracts, upstream commits, runtime и environment.

Нельзя назначить один универсальный численный допуск для разных solver/network до B0/B1 калибровки. Для тождественного LINX override действует отдельный заранее замороженный критерий из `BBN_IDENTITY_CONTRACT.json`. Для PRIMAT↔LINX критерии фиксируются после подтверждения совпадающих сетей и входов, но до просмотра сравнительных исходов. Никакой допуск не подгоняется по результату.

Cross-backend disagreement раскладывается на: network mismatch, rate mismatch, weak/neutrino mismatch, background mismatch, initial-condition mismatch, interpolation/extrapolation, solver/convergence. Не вводить поправочный коэффициент, пока причина расхождения не локализована.

## 7. Что уже есть и что отсутствует

| Компонент | Текущее свидетельство | Статус для этого моста |
|---|---|---|
| PRIMAT pinned source/resources | `PRIMAT_INTEGRATION_20261113`, 20 ресурсных ссылок | Есть |
| PRIMAT Python entry point | `run_bbn(params)` | Документирован |
| PRIMAT custom Python background | upstream docs и ограничения кешей | Частично документирован; общий history adapter отсутствует |
| LINX D+D adapter | PR #57, 30 engineering checks | Есть для D+D table override |
| LINX full BBN identity pair | `BBN_IDENTITY_CONTRACT.json` | Подготовлена, не исполнена |
| Common BBNHistory schema/validator | `BBN_HISTORY.schema.json`, `validate_contract.py`; 6 tests | Структурная проверка есть; физическая полнота не проверяется |
| Reaction/species equivalence map | `NETWORK_MAP.json`, 8 species / 12 reactions | Топология сопоставлена; численная идентичность rates не установлена |
| PRIMAT history adapter | — | Нет |
| LINX common-history adapter | — | Нет |
| Shared rate/covariance realization | — | Нет |
| Cross-backend comparison harness | — | Нет |
| BH1 physical embedding | `BRIDGE_CONTRACT.json` | Открыт; sector X и кинетика не заданы |

## 8. Следующая реализация

Первая инженерно-научная задача — не запускать сразу BH1 и не переписывать оба решателя. Реализовать в vm-lab общий сериализуемый контракт `BBNHistory` + `NuclearRateSet`, валидатор и reaction/species map для PRIMAT small и LINX key_PRIMAT_2023. Затем сделать два тонких backend adapter без копирования upstream-кода/таблиц.

Первый контрольный тест: оба адаптера читают один frozen fixture и возвращают receipt, доказывающий одинаковые входные физические данные. Следующий тест — standard baseline каждого backend, затем общий подграф. Только после этих гейтов подключать BH1-историю.

Это не меняет `BRIDGE_CONTRACT.json`, `CONTROL`, `CURRENT`, `RUN_REQUEST`, очередь вычислений или статусы R/C/L/U. Никакого BBN/BH1 исполнения этим документом не заявляется.


## 9. Implementation status (17 November 2026)

Committed in `analysis/PRIMAT_LINX_BBN_BRIDGE_20261117/`:

- `BBN_HISTORY.schema.json`: machine-readable input envelope.
- `validate_contract.py`: strict cross-field validator for finite values, aligned history arrays, monotonic physical time, positive background quantities, reaction stoichiometry, interpolation constraints and canonical SHA-256 provenance.
- `test_validate_contract.py`: six local unit tests passed (valid fixture and five negative controls).
- `NETWORK_MAP.json`: explicit 8-species/12-reaction mapping between PRIMAT small and LINX `key_PRIMAT_2023`.
- `LINEAGE.md`: parent genealogy and status boundaries.

The map confirms matching network topology, not numerical equality of rate arrays or full solver equivalence. Pinned LINX source inspection also confirms that its documented abundance interface takes photon, neutrino and new-physics energy-density/pressure arrays, and assumes a common neutrino temperature in the described `rho_nu_vec` pathway. It is not an arbitrary electron-neutrino spectral-history adapter. PRIMAT has a Python custom-background route, but tabulated custom backgrounds disable documented incomplete-decoupling and spectral-distortion corrections. These are real adapter capability gaps, not implementation details to paper over.

**Not yet implemented:** PRIMAT history adapter; LINX canonical-history adapter; rate-array/unit reconciliation; common weak/neutrino treatment; backend execution harness; PRIMAT↔LINX numerical comparison. No BBN, GP or BH1 integration was executed. Parent BH1 embedding remains open. Scientific acceptance remains false.

## 10. Соединение с R130

По поручению владельца этот интерфейс связан с [общим R130–BH1–BBN контрактом](../R130_BH1_BBN_CONNECTION_20261117/REPORT.md) и его [машинной записью](../R130_BH1_BBN_CONNECTION_20261117/CONNECTION_CONTRACT.json). R130 поставляет проверенные безразмерные наблюдаемые роста, комбинаторной энтропии и локальной активности. BH1 ограничивает возможную термодинамику и энергобаланс. Между ними и BBNHistory требуется явное физическое сопряжение: часы, геометрия/объём, X, энергия/давление, температуры и обмен em/nu. Оно пока не задано.

C1-разрежение и активный ограниченный цикл C2 — разные контрольные случаи исследовательской постановки. Они не преобразованы в космологический фон. Число вершин не назначается scale_factor, а итерация — time_s. Общая история, rates и нейтринный режим по-прежнему должны быть одинаковыми для PRIMAT/LINX.

Уточнение текущего implementation status: минимальный валидный envelope не является полной физической историей; нейтринные поля опциональны, уравнения Friedmann/энергии/барионного баланса не проверяются, документированная comoving_entropy ещё отсутствует в schema v1. Эти проверки относятся к будущему генератору и расширению контракта. Научный запуск данным соединением не выполнялся.
