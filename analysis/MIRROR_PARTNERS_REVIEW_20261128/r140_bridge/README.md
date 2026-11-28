# Мост #223 ↔ R140/H6

[Полный отчёт](REPORT.md) · [Регистры и наблюдаемые](REGISTER_PROOF.md) · [Когерентные истории и поле](HISTORY_PROOF.md) · [Независимая ревизия](REVIEW.md).

Исходный снимок: `fcc006b30e120fb536eba09288deeaf2dc42f167`. Постановка до вычисления сохранена в [RUN_PLAN.json](RUN_PLAN.json), происхождение решений — в [LINEAGE.json](LINEAGE.json), версии входов — в [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json).

Единый запуск из корня репозитория:

```sh
python -m pip install -r analysis/MIRROR_PARTNERS_REVIEW_20261128/r140_bridge/requirements.txt
python analysis/MIRROR_PARTNERS_REVIEW_20261128/r140_bridge/run.py
```

Результаты каждого исполнения сохраняются в собственном каталоге `runs/<run_id>/`. После успешного исполнения [LATEST.json](LATEST.json) указывает его результаты, среду, калибровку, прогноз, время и исходный SHA. Исторические входы не перезаписываются. Первое исполнение по принятому маршруту выполняется на GitHub Actions после независимой ревизии.
