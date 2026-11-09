# Синтез отзывов NOW / U008, 9 ноября 2026

Основной документ: [SYNTHESIS.md](SYNTHESIS.md).

Исходные отзывы: [S1](sources/S1.md), [S2](sources/S2.md), [S3](sources/S3.txt).
[Источники](SOURCE_INDEX.json), [арифметическая проверка](CHECKS.json),
[скрипт](verify_neighbor_synthesis.py). Новые вычислительные опыты не запускались.

## Воспроизведение арифметики

В локальном clone vm-lab получить refs, указанные в SOURCE_INDEX.json, затем:

```bash
mkdir -p /tmp/now-neighbor-inputs
git show b85fca0252c74effdce4a2adfa7a8cf5adde01b0:results/NOW_LONG_da72a3a_20261108_RAW/main_output/FOUR_CANDIDATE_RETURN.json > /tmp/now-neighbor-inputs/four.json
git show b85fca0252c74effdce4a2adfa7a8cf5adde01b0:results/NOW_LONG_da72a3a_20261108_RAW/main_output/rows/001318.json > /tmp/now-neighbor-inputs/row1318.json
git show b919e64ad89a5afe2c395a0218895c856088c57d:analysis/U008_CAUSAL_20261109/SUMMARY.json > /tmp/now-neighbor-inputs/SUMMARY.json
git show b919e64ad89a5afe2c395a0218895c856088c57d:experiments/now_integrated_v1/u008/PROTOCOL.json > /tmp/now-neighbor-inputs/PROTOCOL.json
python3 analysis/NOW_U008_NEIGHBOR_SYNTHESIS_20261109/verify_neighbor_synthesis.py --inputs /tmp/now-neighbor-inputs --output /tmp/now-neighbor-checks.json
```

Скрипт импортирует только стандартную библиотеку, читает JSON и пересчитывает агрегаты.
Локальные байтовые хеши в CHECKS отражают полученные через подключение текстовые
копии; канонические JSON-хеши в SOURCE_INDEX позволяют проверить входы независимо
от конечного перевода строки. Численные результаты должны совпасть.
