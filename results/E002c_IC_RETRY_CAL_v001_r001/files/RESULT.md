Время: прогноз 34.000000 с; диапазон 0.000000–94.000000 с; внутренний факт 26.900877267005853; статус REVIEW_REQUIRED.
Полный факт проверяется отдельно по run.json: job.finished − job.started; очередь и публикация отдельно.
Запуск E002c_IC_RETRY_CAL_v001_r001; код 8352ddb5f2ced04e7cc03e5f5c4a64d5519c99f8; kernel 2b9fff174f4ee1f03f8fc5065f0684341c35085722826772465101b1ed8b6b0d.
Объём: 3 траекторий, 12000 шагов, 48000 RHS, 1203 scalar, 123 diagnostic, 25 snapshots.
Проверки: volume=False; failures=['Time-integral certificate inconsistent with survival series', 'work_volume_mismatch'].
IC-статусы: {'ic_structural_status': 'not_run', 'ic_transport_status': 'not_evaluated'}. Шесть целей pL/ell, три alpha, никаких новых каналов; hop не входит в поиск.
Калибровка: две пробы T20 и одна T200, dt=.02. Стационарность коротких проб не является гейтом production.

|Проба|Шаги|Полное время траектории, с|Стационарность|
|---|---:|---:|---|
|RETRY_CAL_1|1000|2.325878642994212|False|
|RETRY_CAL_2|1000|2.307900839979993|False|
|RETRY_CAL_3|10000|18.879180324991466|True|

Подробности: metrics.json, checks.json, data_manifest.json. Исходные прогоны и их статусы не изменены.
