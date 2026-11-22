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

## Спектральная генеалогия и проверка отзыва

[Доноры ГР и ГП, Конн, R132 и R140](HILBERT_POLYA.md) · [нормировки и остатки](spectral/ARITHMETIC.md). Из этого каталога выполнить

```sh
python spectral/corpus.py | diff spectral/corpus.json -
python -m pip install python-flint==0.9.0
python spectral/arithmetic.py | diff spectral/arithmetic.json -
```

Первый расчёт использует исходные объекты и точную арифметику SymPy. Второй использует интервалы Arb. Тест проверяет нули ζ и формулу Гинана–Вейля. Результаты эксперимента авторов дзета-троек приведены со ссылками на публикацию.

## От резонанса до выходов BBN

[Исследование, числа и источники](bbn/REPORT.md) · [результаты для сравнения](bbn/CHECKS.json). Повтор использует архив общей траектории и три закреплённых внешних источника. Проверены Python 3.12, NumPy 2.3.5 и SciPy 1.17.0. Нужны Git, системная библиотека GNU GSL для кулоновских функций и утилита pdftotext из Poppler для таблиц Burns. При наличии клонов укажите их существующие пути. Для пустого рабочего каталога источники подготавливаются так:

```sh
git clone --filter=blob:none --no-checkout https://github.com/CyrilPitrou/primat.git primat
git -C primat checkout --detach 6f7e5680614fb119d65a6c9c65a292240b27c61e
git clone --filter=blob:none --no-checkout https://github.com/cgiovanetti/LINX.git LINX
git -C LINX checkout --detach bfba07c77a5fcba1cc772d42f2d9e9be8a542df8
git clone --filter=blob:none --no-checkout https://github.com/Anne-KatherineBurns/bbn-sensitivity-atlas.git atlas
git -C atlas checkout --detach c658d7c5e007cdf2862f177b922c03362fd8603f
git init vm-lab-history
git -C vm-lab-history fetch --depth=1 https://github.com/IgorSabirov/vm-lab.git d503ee0f1f89c99c8560803dc46277d544ef15ba
```

Из каталога с этими источниками подставьте путь к файлу replay.py из R141 или распакованного комплекта:

```sh
OPENBLAS_NUM_THREADS=1 python /path/to/R141/bbn/replay.py \
  --primat primat --linx LINX --atlas atlas --vm_lab vm-lab-history --check
```

Без флага `--check` программа печатает полный JSON. При проверке строк, версий и состава данных требуется точное совпадение, для вещественных чисел применяются относительный допуск 1e−5 и абсолютный 1e−11. Четыре использованных файла траектории сверяются с исходным манифестом SHA‑256. В ZIP включена карта имён сети. Отчёты о смежных направлениях доступны в репозитории.
