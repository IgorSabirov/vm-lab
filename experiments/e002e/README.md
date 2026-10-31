# E002e — объединённый концепт v003

**Статус: G,baseline,F2 выполнены и проверены через GitHub. G:92 случая,
4,755с при6с; baseline:24полных случая,375,188с при383с; F2:20полных
случаев,29,288с при34с; все три гейта PASS. В F2 восемь количественных
прогнозов G1 опровергнуты, десять дополнительных знаковых поддержаны.
Научная приёмка остаётся за пользователем.**

- [Главный итог F2 и разбор отзыва](../../analysis/E002e_F2_v001/F2_RESULT.md).
- [Новый соседский отзыв: проверка1 ноября, единственность NESS и разложение h/p](../../analysis/E002e_NEIGHBOR_REVIEW_20261101/RESULT.md).
- [Проверка F2](F2_v001_r001_verification.json), [запуск](launches/E002e_F2_v001_r001.json).

- [Статус baseline и проверенные объёмы](BASELINE_STATUS_v001.md).
- [Машинная проверка baseline](BASELINE_v001_r001_verification.json).

- [Запись запуска baseline](launches/E002e_BASELINE_v001_r001.json).
- [Проверка G](G_v001_r002_verification.json).
- [Исправление экспорта и повторная калибровка](EXPORT_FIX_RESULT_v001.md):
  162,931 с при 166 с; 42/42 теста на ВМ. Первая попытка G с неполным отчётом
  сохранена. Актуальный паспорт — [calibration_verification_exportfix.json](calibration_verification_exportfix.json).

- [Итог калибровки и бюджет — один файл](CALIBRATION_RESULT.md).
- [Проверенный паспорт, точность и бюджет](calibration_verification_final.json).
- [Готовая конфигурация G](production_G_config.json), [baseline](production_baseline_config.json).
- [Граница технического ревью](implementation_review_exportfix.json): прежнее ревью
  Copilot плюс собственная проверка последующих изменений совместимости/ресурсов;
  новое ревью Copilot этих изменений не заявляется.

Ширина провала полной модели остаётся нерешённой. F2 выполнен после проверки
baseline и фиксации предсказаний; калибровка на F2 не выполнялась.

- [Итог кода и ревью](../../analysis/E002e_CODE_v001/RESULT.md).
- [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md) — контракт кода и этапов.
- [e002e_exp](../../e002e_exp) — вычислительное ядро и worker.
- [План проверки кода](../../analysis/E002e_CODE_v001/PLAN.md).
- [production_config.template.json](production_config.template.json) — неисполняемый до привязки проверенного ревью и калибровки шаблон.

- [CONCEPT_v003.md](CONCEPT_v003.md) — текущая самостоятельная редакция для рецензирования.
- [Разбор дымового отзыва](../../analysis/E002e_SMOKE_REVIEW_v001/RESULT.md) и [формульное приложение](../../analysis/E002e_SMOKE_REVIEW_v001/DERIVATIONS.md).
- [case_inventory_v003.json](case_inventory_v003.json) — 92 малые контрольные точки; большое ядро без изменения: 44 NESS, 94 статические/частотные правые части, 18 QRT-входов.
- [f2_prereg_predictions.template.json](f2_prereg_predictions.template.json) — только шаблон. Числовые прогнозы заполняются после объявленной обучающей части, затем закрепляются до запуска F2.

Перечисление случаев воспроизводится из корня репозитория командой `python experiments/e002e/build_inventory_v003.py`. Скрипт не собирает физический генератор и не решает NESS. Формулы отзывов проверены отдельно малыми алгебраическими примерами.

Предыдущие `CONCEPT_v002.md`, `case_inventory.json` и `build_inventory.py` сохранены без изменения. Их разбор — `analysis/E002e_INTEGRATED_REVIEW_v002/`. Более ранние материалы: `analysis/E002e_FANO_REVIEW_v001`, `analysis/E002e_SPECTRAL_REVIEW_20261031`, `analysis/DTL_MODEL_REVIEW_20261031`, `analysis/COPILOT_E002e_METHOD_v001`.
