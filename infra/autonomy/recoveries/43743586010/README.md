# Восстановление публикации BBN r3 без повторного расчёта

Прогон: https://github.com/IgorSabirov/vm-lab/actions/runs/43743586010
PR: #75. Source: 5183eb818d2b3c746d2e919b1f3561a08e7d1b09. Результат: b24c7e0cc47ff964d576f903ce7ba507d2dd731e.

Исходные SUMMARY=FAIL / NOT_EVALUATED, EXECUTION_FAILURE и ledger=FAILED сохранены.
Оба строгих процесса завершились с exit_code=0, stop=null. Сбой возник после сравнения при JSON-сериализации checks.interval_valid (numpy.bool). В действующий runner/verifier изменения не внесены; новых интеграций нет.

Проверены длины и SHA-256 всех 21 файлов ARTIFACTS.json, включая оба бинарных background.npz. SUMMARY/ARTIFACTS совпадают с CURRENT и ledger. Неизменённая функция compare из замороженного source повторно применена к готовым native/RESULT.json и override/RESULT.json. Только при записи отчёта скаляры NumPy преобразованы через item(); предикаты и пороги не менялись.

Результат: все восемь компонент побайтно равны, максимальная невязка 0; одинаковы начальные значения, фон, таблицы, порядок реакций, q, версии, интервал и строгие настройки. Оба solver: 1201 шаг, 900 принятых / 301 отклонённый. Калибровка 58.048 с; native 57.352 с; override 32.676 с.

Это проверка эквивалентности реализации в одной замороженной точке. Это не S3 posterior, не физический мост и не эмерджентность шести моделей. scientific_acceptance=false, R/C/L/U не изменены.

## Воспроизведение восстановления

В отдельную директорию INPUTS выгрузить файлы из
analysis/CCC_BBN_NETWORK_20261114/s3_standard/linx_dd_adapter_20261115/full_run_20261115/results/LINX_BBN_IDENTITY_20261115_r3/
на result SHA выше, сохранив пути и байты. Добавить verify_identity.py из identity/ и BBN_IDENTITY_CONTRACT.json из full_run_20261115/ на source SHA выше. Выполнить `python recover_report.py INPUTS`. Скрипт проверяет закреплённые хеши manifest, verifier, contract и всех 21 артефакта, не импортирует LINX и не запускает solver. Он создаёт отдельный RECOVERED_VERIFICATION.json, не переписывает SUMMARY.

## Продолжение

S3 remains DESIGN_ONLY: observational data/covariance, theory/rate uncertainty propagation and likelihood/prior independence audit missing; S2 physical mappings remain missing. No ready independent frozen package.

Автоматический повтор r3 запрещён. Этот технический FAIL не требует повторять уже завершённые BBN-прогоны. Исправление сериализации будущего runner — отдельная версия; восстановленный результат доступен для дальнейшей подготовки S3, научная приёмка остаётся у владельца.
