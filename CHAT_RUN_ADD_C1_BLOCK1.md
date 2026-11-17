# Запуск ADD C1, блок 1, в обычном Chat

Дата: 17 ноября 2026. Задача: [#83](https://github.com/IgorSabirov/vm-lab/issues/83).
Подготовлено в Work; новый расчёт здесь не запускался.
Родители: R126 → R130 → ADD_C1_AUTHOR_REPRO_20261116.

## Поручение и точный объём

Владелец поручил: «Пиши ком в гит и чат ком поднимет и выполнит. Посмотрим что получится».
Исполнитель — обычный Chat с исполнением Python. Задание, исходники, логи и результаты передаются через GitHub.

Выполни полный **уже готовый конечный блок 1**: 6032 входа; отдельная калибровка — 128 входов.
Это проверка воспроизводимости в другой среде и передачи GitHub → Chat → GitHub.
Общий протокол ADD с Lemma 1, асимптотикой и энтропийными теоремами этим повтором не выполняется.
Вычисления на ВМ, GitHub Actions, платный API и переключение в Work не входят в поручение.

Источник кода и эталонных результатов:
`d24f1577c070595aa791b3b2dbd875d20b71d34b`
в `IgorSabirov/vm-lab`, каталог
`analysis/ADD_C1_AUTHOR_REPRO_20261116/`.

[Исходный отчёт](https://github.com/IgorSabirov/vm-lab/blob/d24f1577c070595aa791b3b2dbd875d20b71d34b/analysis/ADD_C1_AUTHOR_REPRO_20261116/REPORT_BLOCK1.md).
Предыдущее основное вычисление заняло 7.771495 секунды. Это ориентир другой среды.
В Chat получи собственную калибровку и прогноз до основного расчёта.
Подготовку файлов, чтение GitHub, общение и публикацию учитывай отдельно от машинного расчёта.
Прогноз — не таймер остановки; произвольного проектного потолка нет.

## 1. Получить исходники

Через подключённый GitHub прочитай на указанном **точном ref** восемь файлов:
`SPEC.json`, `PLAN.json`, `ring_engine.py`, `graph_engine.py`,
`run_block1.py`, `SOURCE_MANIFEST.sha256`, `RESULTS.json`, `WITNESSES.json`.

Сохрани точные UTF-8 байты в локальный каталог `chat_add_c1_input`.
Если Python-среда не имеет сети, перенеси содержимое через доступный GitHub-инструмент в файлы Python-среды.
Не копируй код вручную по смыслу, не исправляй его и не меняй параметры.
При несовпадении хеша перечитай исходный файл, сохранив исходные переводы строк.
При наличии разрешённого сетевого доступа можно получать exact raw:
`https://raw.githubusercontent.com/IgorSabirov/vm-lab/d24f1577c070595aa791b3b2dbd875d20b71d34b/analysis/ADD_C1_AUTHOR_REPRO_20261116/<filename>`.

Не загружай весь репозиторий, не перечитывай всю историю, не запускай отдельный аудит.
Требуются Python 3 и стандартная библиотека; runner использует Linux /proc и модуль resource.
Проверь доступность Python-исполнения и инструментов записи GitHub в этом Chat.
Если записи нет, реальный расчёт всё равно допустим; после него честно укажи, что публикация заблокирована.
Не требуй от владельца вручную переносить результаты или передавать токен в разговор.

Ниже два последовательных блока Python. Сохрани их в одной сессии.
Если загрузил входы в другое место, меняется только путь `src`.
Исторические PLAN/SPEC остаются побайтно исходными; текущую площадку и поручение фиксирует новый RECEIPT, а не правка замороженного PLAN.

## 2. Проверить байты, откалибровать и показать прогноз

```python
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess, sys, time, os, platform

src = Path("chat_add_c1_input").resolve()
expected = {
    "SPEC.json": "523adf2f6881ccecbc1e136ae1c93943866cc46881ede6d2e11050278e53f802",
    "PLAN.json": "c7052e21988edad8a59608ce22e767b2c465c00d9f5c2a49bb9da04aef334ecc",
    "ring_engine.py": "ec7f16b9df95464c3cdc249bc5704491a71a5a916cfa82ffe97650ce15cf79a9",
    "graph_engine.py": "023b69fd2fee66193db8917a82e5bcd255f58028395b4970855c4c001c83b8c4",
    "run_block1.py": "508a17f4c92b9853538add38ad3d9cab1e41f2286e344a301aec9c84240f6c23",
}
for name, digest in expected.items():
    assert hashlib.sha256((src/name).read_bytes()).hexdigest() == digest, name
baseline = json.loads((src/"RESULTS.json").read_text())
baseline_witnesses = json.loads((src/"WITNESSES.json").read_text())
run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
out = Path("chat_add_c1_runs").resolve()/run_id
out.mkdir(parents=True, exist_ok=False)
for name in [*expected, "SOURCE_MANIFEST.sha256"]:
    shutil.copyfile(src/name, out/name)

def save(name, value):
    (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

def invoke(flag, logfile):
    started = time.perf_counter()
    with (out/logfile).open("x", encoding="utf-8") as log:
        process = subprocess.run(
            [sys.executable, str(out/"run_block1.py"), flag],
            cwd=out, stdout=log, stderr=subprocess.STDOUT
        )
    return {"exit_code": process.returncode, "process_wall_seconds": time.perf_counter()-started}

receipt = {
    "run_id": run_id, "source_commit": "d24f1577c070595aa791b3b2dbd875d20b71d34b",
    "execution_location": "ordinary_chat_python_sandbox",
    "owner_instruction": "Выполнить через Chat; вся передача через GitHub.",
    "purpose": "reproduction_of_existing_block1_in_new_environment",
    "historical_plan_kept_unchanged": True,
    "billing_status": "NOT_MEASURED", "source_sha256": expected,
    "python": sys.version, "platform": platform.platform(),
    "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
    "disk_free_bytes_before": shutil.disk_usage(out).free,
}
save("RECEIPT.json", receipt)
receipt["calibration"] = invoke("--calibrate", "calibration.log")
save("RECEIPT.json", receipt)
assert receipt["calibration"]["exit_code"] == 0, "Сохранить лог; к основному запуску не переходить"
preflight = json.loads((out/"PREFLIGHT.json").read_text())
assert preflight["main_allowed_by_checks"]
assert preflight["planned_main_inputs"] == 6032
print(json.dumps({
    "output_directory": str(out),
    "forecast_seconds": preflight["forecast_seconds"],
    "range_seconds": preflight["range_seconds"],
    "main_inputs": 6032,
    "calibration_inputs": preflight["calibration_inputs"]
}, ensure_ascii=False, indent=2))
```

Сообщи полученный прогноз одной строкой и сразу переходи к следующему блоку.
Повторного разрешения не требуется: запуск в Chat уже поручен владельцем.
Не включай время подготовки и общения в прогноз вычислительного блока.

## 3. Выполнить основной корпус и сверить результат

```python
receipt["main"] = invoke("--run", "run.log")
save("RECEIPT.json", receipt)
if not (out/"RESULTS.json").exists():
    raise RuntimeError("RESULTS.json не создан; сохранить RECEIPT и run.log как технический отказ")
actual = json.loads((out/"RESULTS.json").read_text())
stable_keys = [
    "case_counts", "total_case_inputs", "total_input_vertices", "corpus_sha256",
    "metrics", "unexpected_failures", "status", "scope",
    "source_sha256", "negative_validation_controls", "P_raw"
]
comparison = {key: actual.get(key) == baseline.get(key) for key in stable_keys}
comparison["WITNESSES"] = (
    (out/"WITNESSES.json").exists()
    and json.loads((out/"WITNESSES.json").read_text()) == baseline_witnesses
)
comparison["source_bytes_after"] = all(
    hashlib.sha256((out/name).read_bytes()).hexdigest() == digest
    for name, digest in expected.items()
)
comparison["main_exit_zero"] = receipt["main"]["exit_code"] == 0
save("COMPARISON.json", {
    "reference_commit": "d24f1577c070595aa791b3b2dbd875d20b71d34b",
    "checks": comparison,
    "reproduction_status": "MATCH" if all(comparison.values()) else "MISMATCH",
    "ignored_reference_fields": "timestamps, timings, environment, RSS, runtime_plan_actual",
})
receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
receipt["runtime_plan_actual"] = actual.get("runtime_plan_actual")
receipt["disk_free_bytes_after"] = shutil.disk_usage(out).free
save("RECEIPT.json", receipt)
print(json.dumps({
    "run_id": run_id,
    "status": actual.get("status"),
    "reproduction": "MATCH" if all(comparison.values()) else "MISMATCH",
    "cases": actual.get("total_case_inputs"),
    "corpus_sha256": actual.get("corpus_sha256"),
    "main_process_wall_seconds": receipt["main"]["process_wall_seconds"],
    "runner_compute_seconds": actual.get("elapsed_seconds"),
    "comparison": comparison
}, ensure_ascii=False, indent=2))
```

Ожидаемая сверка: 6032 входа; хеш корпуса
`9664c31a36a817d65b3924af18b1e96aa4d31c390c427b0ad67b1d226d9af99c`;
у A нет нарушений; у P_ring ровно по 6011 нарушений Q²=τ и TQT=Q⁻¹,
других нарушений нет; две реализации совпадают.
Эти отрицательные контроли ожидаемы. Не исправляй их ради PASS.
Время, RSS и описание среды должны отражать новый запуск, их совпадения с эталоном не требуется.

## 4. Вернуть результаты в GitHub

Напиши короткий `REPORT.md` в `out`: вопрос, исходный SHA, место исполнения,
полнота 6032 входов, MATCH/MISMATCH, результаты A/P_ring/P_raw,
прогноз/факт основного вычисления, отдельное процессное wall time,
границы вывода и статус публикации. Отдельно запиши:
«Списание кредитов не измерено; успешный расчёт не доказывает бесплатность».

Создай `MANIFEST.sha256` для всех остальных файлов нового `out`.
Опубликуй содержимое каталога в:
`analysis/ADD_C1_CHAT_REPRO_20261117/<run_id>/`
в ветке `work/chat-add-c1-handoff-20261117`.
Используй GitHub-инструменты записи; предпочтителен один commit всего набора.
Если доступно только create_file, публикуй последовательными коммитами;
MANIFEST последним, затем перечитай файлы на итоговом SHA и проверь их байты/хеши.
Исходный каталог ADD_C1_AUTHOR_REPRO_20261116 и его результаты не перезаписывай.
Не коммить весь рабочий каталог или посторонние файлы.
Ветка и связанный PR уже подготовлены в Work; при наличии PR добавь ссылку на результат.
Задача — #83; никакой команды автономного контроллера или отдельного запуска Actions не требуется.

После вычисления ошибка публикации исправляется из уже сохранённых файлов, без повторного прогона.
Если GitHub может читать, но не писать, сохрани вычисленное в текущей среде и сообщи точное отсутствующее действие.
Если Python-исполнения нет, не выдавай прочитанный эталон за новый результат.
Если запуск прерван внешней платформой, сохрани имеющиеся артефакты и укажи фактическую причину.
При отсутствии GitHub вообще сообщи отказ чтения; не запрашивай секреты и не меняй площадку.

Заверши коротко: выполнено/не выполнено, 6032 или фактическое число входов,
MATCH/MISMATCH, время, ссылка на итоговый commit либо конкретный отказ публикации.
Не меняй статусы научного реестра: проверка передачи и повтор конечного блока не доказывают новые теоремы.
