# E002d v003 — проверки до Copilot

Прогноз всего набора: 60 с, диапазон 0–300 с, закреплён до тестов в e7d050d11ec97b2c301f2d000bf99f94998011b1.
Факт unittest: 38.946 с; статус времени PASS. Внутренняя длительность smoke:16.5509 с.

Семь групп PASS:
1. 184 уникальных случая;112fine/72coarse;5.92Mшагов;252связи сравнений;общий класс продления.
2. Карты всех восьми операций на216×216;2.5gamma/.5gamma на пересечении;контрпример ошибочному D[L1+L2].
3. Обе модели,все операции,T/C,ненулеваяфаза/detuning/шум: совпадение с полной сборкой Линдблада и прямым RHS на общей случайной PSD-матрице.
4. Аналитический знак E/S,отрицательныйD у монотоннойкривой,блокировка утверждения приошибкеdt.
5. Интервалы,малые/неопределённые знаменатели,дваодносторонних сравнения.
6. Полный компактныйотчёт для184случаев/продленияT400 укладывается24KiB на синтетическом наборе.
7. Сквознойsmoke10траекторийT2,3000шагов/12000RHS,нулевая/ненулеваяфаза,N1/N2,обаdt;независимаяреконструкция иотклонение поврежденияхеша ифальсифицированного тока с пересчитаннымхешем.

Отчётsmoke:602338байт,23файла.Это не калибровка полного научного запуска и не научный результат.
Исходные шесть базовых файлов совпадают побайтно с Git blobs коммитаc2237f62333a892be652fc1edbf455aeb90d3169; source_base_hashes.json.

Не завершено:техническое ревьюCopilot,проверкаего замечаний,окончательная калибровкаВМ и производственный бюджет.

## Дополнение перед передачей

Проверка размеров выявила реальный риск: подробный двухгоризонтный metrics.json мог превышать8MiB(синтетический широкий формат чисел11,524,002байта). Убрано дублирование оконных средних; полный анализ вынесен в lossless analysis.json.gz с проверкой хеш-ссылки. Ничего не отброшено.
Добавлен независимый тест шести точек на искусственной положительной матричной кривой с аналитически известным средним; подмена среднего отклоняется. Добавлен тест лимита metadata с длинными числовыми представлениями.
Итоговый повтор:8группPASS за43.958с,при прежнем прогнозе60с и диапазоне0–300с. Smoke:16.5632с,545443байта,24файла.
Отдельно исправлен классификатор моста: реальный ответ No authentication information found теперь AUTH_REQUIRED; проверен на полученном сообщении.

## Review regression checks — preregistered before execution
31 October 2026. After Copilot review: forecast 90 seconds, interval 0–300 seconds.
Basis: original 8 groups took43.958 seconds; add another short smoke run with an injected failure, independent full184-case derived-field corruption checks, nonfinite and provenance tests.
Planned13 test groups; no production evolution. Actual results will be appended separately.

Review regression result:13 groups PASS in56.078s, exit0, forecast90s[0,300]=>PASS.
Includes all184 synthetic cases at both horizons; independently reconstructed derived values/envelopes/statuses and9 semantic corruptions per horizon.
Normal10-case smoke16.385s,545642bytes24files. Injected-failure smoke13.499s retained all10 cases including partialT=.4;9 other cases completedT2; whole cohort FAILED and scientific comparisons withheld, as intended.
Nonfinite, pinned-record mismatch, extension failure and resource/programming abort regressions passed.
No acceleration integrated; full-CSR RK4 unchanged. Final VM calibration remains48cases,T10,72000steps,forecast180s[60,480].
