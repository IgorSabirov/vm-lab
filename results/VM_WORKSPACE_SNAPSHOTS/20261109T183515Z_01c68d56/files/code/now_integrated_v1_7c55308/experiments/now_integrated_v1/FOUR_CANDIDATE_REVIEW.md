# Техническая ревизия патча 0.4

Это код к прежнему NOW_INTEGRATED_CONTINUATION_V1. Полный план:
[PATCH_20261108.md](../../analysis/INTEGRATED_EXPERIMENT_20261107/PATCH_20261108.md).
Ревизор проверяет реализацию и предсказанные отрицательные контроли; изучение
теоремы статьи не является условием работы над нашей моделью.

До авторских дымовых проверить:

- уникальность полезной нагрузки при split/merge и на шве цикла;
- полноту будущих маршрутов, заданных часов и snapshot с пакетом в пути;
- независимость Y_task от health/K и глобального правильного ответа;
- новый read после повреждения; действительно оплаченная перезапись B;
- одинаковый фиксированный резерв ON/OFF/SHAM и явный недостаток ресурса;
- отсутствие переноса исходных ADD-секторных чисел или старого прогноза времени;
- все 123 прежних случая неизменны, 210 случаев / 160 контрастов / 413 задач;
- контрольные геометрии явно не названы равновесными ансамблями;
- исключены положительные научные выводы из smoke.

Новые исходники: `nowexp/carrier.py`, `task_probe.py`, `geometry_diagnostics.py`,
`amendment_report.py`. Изменены прежние `engine.py`, `state.py`, `local_instruments.py`,
`observables.py`, `runner.py`, `provenance.py`; входы и тесты лежат в прежних каталогах.
Изолированного второго исполнителя нет.

Команды ниже — для ревизора после checkout фиксированного исходного коммита.
`PATCH_COMMIT` означает SHA этого исходника, не позднейший коммит с квитанцией.
Из корня репозитория:

```bash
python3 experiments/now_integrated_v1/tools/source_receipt.py --commit PATCH_COMMIT --output /tmp/NOW_PATCH_SOURCE.json
cd experiments/now_integrated_v1
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -m unittest discover -s tests -v
python3 run.py --phase reviewer --reviewer-name REVIEWER --source-commit PATCH_COMMIT --source-manifest /tmp/NOW_PATCH_SOURCE.json --output /tmp/NOW_PATCH_REVIEW
```

Для собранного по существующей инструкции Serbian C++ добавить к runner
`--signature-library /ABS/libsignature.so`. Хеш бинарника входит в fingerprint
возобновления и каждый диагностический отчёт. Отсутствие библиотеки оставляет
`NOT_REQUESTED`; автоматического NumPy-заменителя под именем Serbian нет.

После технической ревизии используется прежний `tools/smoke_suite.py` с квитанцией
принятия и соответствующим source digest. Замораживание и прогноз 0.3 не подходят.
При сбое по времени, размеру графа или диску регистрировать неполное вычисление;
не уменьшать молча панель и не перенормировать только успешные траектории.

Статус при публикации: CODE_WRITTEN / STATIC_CHECKED / REVIEW_PENDING.
Новые unit, smoke, VM-calibration и main автором не исполнялись.
