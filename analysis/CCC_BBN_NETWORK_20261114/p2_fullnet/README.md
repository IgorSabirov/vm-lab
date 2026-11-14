# P2_FULLNET — отдельный S0-инженерный запуск

**Исходный срез:** `900a67f879621b501f74f8b1da561494fa3c4ae6`  
**Upstream:** PRIMAT 0.3.3, commit `6f7e5680614fb119d65a6c9c65a292240b27c61e`  
**Сеть:** 59 нуклидов, 427 ядерных реакций + слабый (n\leftrightarrow p) канал.  
**Статус этого пакета:** автоматизация подготовлена; BBN здесь не запускалась.

## Генеалогия

Пакет создан от точного source commit `900a67f...`, который наследует P0/P1 launcher, source lock, cache identity, процессные лимиты и проверенные numerical gates. PR [#44](https://github.com/IgorSabirov/vm-lab/pull/44) содержит шесть успешных P0/P1 интегрирований, но прямо ограничивает P2 статической инвентаризацией. Этот пакет закрывает только пробел подготовки исполнения полной сети.

Связи и границы записаны в [PROVENANCE.json](PROVENANCE.json). Основные внутренние родители: CCC+TL drift report, joint-law review, PRIMAT integration report, внешний PRIMAT contract/resource manifest, `link:L10` и `question:U006`. Последние две записи остаются открытыми. S2/Anthropic, Sη, B07 и S3 не являются условиями стандартного S0.

## Что означает full_59_427

`full_59_427` — **внутренний ID профиля vm-lab**, не имя встроенной сети PRIMAT. В upstream конфигурация должна быть `network="large"` с отсутствующим/нулевым `amax`. Иное имя заставило бы PRIMAT искать пользовательский файл сети. Полная сеть используется только в LT; HT остаётся n/p, MT — фиксированная 18-канальная подсеть согласно upstream.

Тяжёлый хвост сети имеет ограничения точности, обусловленные AC2024 rate floors. Результат нельзя превращать в «эталон точности тяжёлых элементов».

## Кэш и калибровочная проба

Проба меняет только:
- `numerical_precision: 1e-6`;
- `rate_grid_npts: 1000`.

Она **не** меняет `sampling_temperature_per_decade=2000`, `T_start/T_end`, weak-rate sampling, thermal sampling, VEGAS параметры, QED/радиативные/нейтринные флаги или физические константы. Эти величины входят в weak/thermal fingerprint либо задают саму авторскую фоновую историю. `cache_dir` — отдельный overlay для новых локальных файлов, а слабые таблицы при этом разрешаются в те же frozen upstream-файлы.

Ожидаемая единственная локальная добавка — electron-thermo cache для (T_{start}=100) MeV; upstream shipped electron cache рассчитан на другое (T_{start}). Любая новая weak cache запрещена. Проба использует отдельный overlay, чтобы не прогреть main cold run.

## Порядок действий

Путь по умолчанию — `analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/results/P2_FULLNET`.

1. Установить upstream PRIMAT ровно на pin выше в отдельный checkout (не копировать и не изменять таблицы). Существующее окружение vm-lab должно содержать PRIMAT dependencies и NumPy/SciPy/threadpoolctl.
2. Перейти на ветку `s0-fullnet`, выполнить:
   ```sh
   ./analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/run_fullnet.sh prepare --upstream /path/to/primat
   ./analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/run_fullnet.sh probe --upstream /path/to/primat
   ```
3. Скрипт сохраняет пробу, CPU/wall/RSS, логи, cache delta, static network inventory. Он **не** запускает полный прогон автоматически. Сгенерируйте forecast, указав диапазон и обоснование после просмотра замеров:
   ```sh
   ./analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/run_fullnet.sh forecast --low 200 --central 350 --high 570 --basis "указать основание по фактической калибровке"
   ```
   Числа здесь только пример синтаксиса, **не прогноз и не рекомендация**.
4. Опубликуйте forecast и пробные артефакты в draft PR:
   ```sh
   ./analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/run_fullnet.sh publish
   ```
5. Только после просмотра forecast и его публикации — явно подтвердите SHA forecast. Перед cold-запуском скрипт отдельно публикует `APPROVAL.json` и соответствующую запись в `LEDGER.jsonl`:
   ```sh
   ./analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/run_fullnet.sh approve --forecast-sha <SHA256> --approved-by <operator> --max-upper-seconds 600
   ```
   Эта команда создаёт approval receipt и затем запускает cold и warm как два отдельных процесса, в пределах **600 секунд на каждый процесс**; суммарный предел cold+warm — 1200 секунд.
6. После завершения:
   ```sh
   ./analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/run_fullnet.sh publish
   ```
   Отправьте получившийся PR на ревью. Скрипт сам не мержит его и не меняет научные статусы реестра.

Для явного автоматического разрешения forecast допускается флаг `--auto-approve --max-upper-seconds N` в команде `forecast`; он действует только на уже заданный пользователем верхний предел, после публикации forecast в GitHub. Авторазрешение без верхней границы и публикации запрещено.

## Gates и статусы

Технические gates: три успешные эпохи HT/MT/LT; LT содержит 59 различных нуклидов; конечные значения конечны; baryon residual не выше (10^{-10}); сырой минимум не ниже (-10^{-12}); две замороженные weak tables действительно прочитаны; weak cache не пересоздавался; нет неожиданных файлов cache; cold/warm совпадают численно. `RAW_SOLVER.npz` хранит исходные solver times и массивы Y по всем трём эпохам, а `RESULT.json.clamp_checks` показывает сырые/итоговые минимумы, список изменённых видов и `Y_final − Y_raw,LT` по каждому виду.

Отсутствие результата из-за wall/RSS cap или исключения — **ENGINEERING_TIMEOUT / FAILED_TECHNICAL**, а не FAIL физической модели. P2 не сравнивается с P1 авторскими (Y_p), D/H reference tolerances. Они относятся к `large, amax=8`, а не к полной сети.

Файл `SOLVER_CHECKPOINT.pkl` появляется лишь после успешного завершения всех трёх интеграций. Он нужен для восстановления отчёта после ошибки сериализации/проверки, но не умеет возобновлять интеграцию, остановленную тайм-аутом. Автоматического retry/resume нет.

**Научная приёмка: false.** Результат — условная инженерная проверка выбранной конфигурации PRIMAT, а не подтверждение CCC+TL, не вывод S2, не независимая репликация и не закрытие L10/U006.
