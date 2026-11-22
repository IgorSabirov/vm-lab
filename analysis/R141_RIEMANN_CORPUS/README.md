# Воспроизведение R141

[Скачать весь комплект R141](R141_replay.zip) · [Основной отчёт](REPORT.md) · [решения по отзыву](REVIEW.md) · [разбор доказательства Римана](donor_replay/REPORT.md).

Для проверки конечных опытов нужны Python 3, SymPy и NumPy. Зафиксированные версии NumPy 2.3.5, SymPy 1.14.0. В корне этого каталога выполнить:

```sh
python reproduce.py --check
(cd donor_replay && sha256sum -c SHA256SUMS)
(cd donor_replay && python experiments.py) | diff donor_replay/results.json -
(cd donor_replay && python followup.py) | diff donor_replay/followup.json -
(cd donor_replay && python previous.py) | diff review/evidence.json -
```

При запуске reproduce.py без флага обновляются CHECKS.json и SCHEDULES.json. Графовые расчёты и проверки матриц используют целую и рациональную арифметику. Приближения в CHECKS.json приведены для чтения. Аудиты внешнего доказательства и файлы закреплённой ревизии перечислены в основном отчёте.
