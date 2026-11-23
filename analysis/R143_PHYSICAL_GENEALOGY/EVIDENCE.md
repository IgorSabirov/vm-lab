# Адресные свидетельства

В поле «Результат блока» указана операция на стороне корпуса. Отдельная строка указывает, какое утверждение R142 эта операция затрагивает. Ссылки ведут к проверенным строкам фиксированной ревизии. Полный список адресатов каждой записи с техническими файлами и каталогами содержится в [evidence.json](evidence.json).

<a id="e01"></a>
## E01. Связанные квантовые точки с двумя электронами

**Оболочки квантовых точек** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R022](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r022) · [C016](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json) · [E002c](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/E002c_literature_review_20261029/REVIEW.md#L133).

В R022 разобран расчёт двухэлектронного тёмного состояния Pöltl–Emary–Brandes; в E002c рассмотрен одноэлектронный магнитотранспорт Emary.

**Реализация.** Собственный расчёт корпуса относится к модельной сети E002c. Обе работы о точках теоретические.

**Данные.** Экспериментальный спектр добавления Tarucha в E002c отсутствует.

**Область вывода.** семейство. Ток при блокировке и спектр добавления при заполнении — разные наблюдаемые.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/E002c_literature_review_20261029/REVIEW.md#L133) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/E002c_REVIEW.md#L89)

<a id="e02"></a>
## E02. ⁴He в выходном канале ³He(d,p)⁴He

**Классические замыкания ядер** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [R141](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r141) · [BBN-Rmatrix](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/R141_RIEMANN_CORPUS/bbn/REPORT.md#L25).

Идентифицировано ядро с Z=N=2. Скорость пересчитана по одному уровню ⁵Li и двум каналам.

**Реализация.** resonance.py и таблица пяти температур.

**Данные.** Опубликованные параметры анализа сечений и табличные скорости; отдельного фитирования 214 исходных точек здесь нет.

**Область вывода.** nuclear.1. Ни ширина уровня ⁵Li, ни выход ⁴He не измеряют щель ⁴He; совпадение касается только nuclear.1.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/R141_RIEMANN_CORPUS/bbn/REPORT.md#L25) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/R141_RIEMANN_CORPUS/bbn/resonance.py#L1)

<a id="e03"></a>
## E03. ⁴He в парных траекториях LINX/PRIMAT

**Классические замыкания ядер** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · основной выход.

**Адреса.** [BBN-pair](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/PRIMAT_LINX_BBN_BRIDGE_20261117/PAIRED_RUN_20261120.md#L7) · [#140](https://github.com/IgorSabirov/vm-lab/issues/140) · [PR144](https://github.com/IgorSabirov/vm-lab/pull/144).

В двух сетях вычислен Yp, сохранены траектории восьми содержаний и передача в CLASS.

**Реализация.** 17 пар с общими скоростями, два собственных эталона; отдельно шесть расчётов CLASS.

**Данные.** Табличные скорости и численные траектории. Yp здесь расчётный.

**Область вывода.** nuclear.1. Yp не проверяет замыкания остальных ядер и не измеряет собственный спектр ⁴He.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/PRIMAT_LINX_BBN_BRIDGE_20261117/PAIRED_RUN_20261120.md#L7)

<a id="e04"></a>
## E04. Лёгкие ядра в сети BBN, выход гелия

**Классические замыкания ядер** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [R135](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r135) · [#171](https://github.com/IgorSabirov/vm-lab/issues/171) · [task:CASCADE](https://github.com/IgorSabirov/vm-lab/issues/171).

В программной поставке P7/P8 сохранены контрольные содержания при переданной истории.

**Реализация.** Нативные адаптеры и контроль с фиксированными входами.

**Данные.** Сохранённые выходы модели; независимая оценка оболочечной щели отсутствует.

**Область вывода.** nuclear.1. Остаток #171 включает физику каскадов и возврат энергии.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/c3bc771d1daa292d5d9fd3e1d17bf4d3d6d01c92/analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/extensions_reference/p7_bbn_control/linx/0/observables.json#L1)

<a id="e05"></a>
## E05. Первичный ⁴He как массовая доля Yp в газе

**Классические замыкания ядер** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [R137](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r137) · [U014](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md#u014) · [#196](https://github.com/IgorSabirov/vm-lab/issues/196).

Yp входит в подсчёт электронов при полной ионизации и проверку оптической толщины.

**Реализация.** verify.py, интеграл τ при z<3.

**Данные.** Параметр симуляции и таблица Lumina; лабораторного измерения ядра здесь нет.

**Область вывода.** nuclear.1. Проверена роль количества ядер, а не их внутренний спектр.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/R137_LUMINA/REPORT.md#L27) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/R137_LUMINA/verify.py#L1)

<a id="e06"></a>
## E06. Первичный гелий на входе рекомбинации

**Классические замыкания ядер** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [R138](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r138) · [U014](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md#u014) · [#199](https://github.com/IgorSabirov/vm-lab/issues/199).

Yp связывает состав BBN с числом атомов и свободных электронов; указано требование одинаковых входов.

**Реализация.** Контроль готовых таблиц drft/RECFAST выполнен; отдельный запуск HYREC-2 указан в плане.

**Данные.** Референсная вычислительная таблица.

**Область вывода.** nuclear.1. Для передачи Yp нужна единая барионная нормировка.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/R138_POST_BBN_DONORS/REPORT.md#L11)

<a id="e07"></a>
## E07. Гелий в атомной рекомбинации

**Замкнутые электронные оболочки** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R138](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r138) · [U014](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md#u014) · [#199](https://github.com/IgorSabirov/vm-lab/issues/199).

Физический переход ионов к связанным состояниям He входит в задачу HYREC-2; xₑ и Tgas рассматриваются как выходы.

**Реализация.** Из drft считана таблица RECFAST; новый расчёт уровней He отсутствует.

**Данные.** Опубликованная модельная таблица; лабораторные энергии ионизации не использованы.

**Область вывода.** noble.1. Ряд благородных газов и скачок ионизации вне этого опыта; возможен только He.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/R138_POST_BBN_DONORS/REPORT.md#L11) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/R138_POST_BBN_DONORS/check_tables.py#L11)

<a id="e08"></a>
## E08. He III в расчёте ионизации газа Lumina

**Замкнутые электронные оболочки** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R137](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r137).

Для He III у ядра нет связанных электронов. Это отдельно размеченный контроль ошибочного переноса атомной оболочки.

**Реализация.** Прочитана история объёмной доли He III.

**Данные.** Таблица расчёта газа Lumina.

**Область вывода.** noble.1. Для замкнутой электронной оболочки He требуется нейтральное основное состояние и соответствующая наблюдаемая.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/R137_LUMINA/REPORT.md#L14)

<a id="e09"></a>
## E09. Нейтральный атомарный H в симуляции Lumina

**Серия Бальмера водорода** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [R137](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r137) · [#196](https://github.com/IgorSabirov/vm-lab/issues/196).

Таблица H I даёт эволюцию нейтральной доли; в отчёте определено пересечение 0,5.

**Реализация.** Обработка опубликованных таблиц и вычисление τ.

**Данные.** Симуляция, без спектров линий Бальмера.

**Область вывода.** семейство. Прямой проверки переходов n→2 в этом блоке нет.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/R137_LUMINA/REPORT.md#L13)

<a id="e10"></a>
## E10. Рекомбинирующий водород

**Серия Бальмера водорода** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R138](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r138) · [U014](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md#u014) · [#199](https://github.com/IgorSabirov/vm-lab/issues/199).

В постановке HYREC-2 присутствует связанный водород; контрольный расчёт читает xₑ, Tgas.

**Реализация.** check_tables.py на контрольных таблицах RECFAST/drft.

**Данные.** Численные таблицы; спектры Hα–Hδ не входят.

**Область вывода.** семейство. Для проверки серии нужны разрешённые переходы и шкала длин волн.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/R138_POST_BBN_DONORS/REPORT.md#L11) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/R138_POST_BBN_DONORS/check_tables.py#L34)

<a id="e11"></a>
## E11. Эффективная рекомбинационная модель и полная ёмкость слоя

**Ёмкость главного слоя атома** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R138](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r138).

Наличие связанных состояний атома само по себе не устанавливает полный набор n,l,m,s в используемой таблице.

**Реализация.** Считываются xₑ и Tgas.

**Данные.** Контрольная таблица drft.

**Область вывода.** семейство. Нужно явное перечисление подуровней и вырождений для утверждения о 2n².

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/0adbf1e757e48fdf98a6da5a2cc3cf11b12b554a/analysis/R138_POST_BBN_DONORS/check_tables.py#L34)

<a id="e12"></a>
## E12. Четырёх- и пятиточечные струнные амплитуды

**Критическая размерность бозонной струны** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R134](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r134).

Рассчитаны полюса и вычеты амплитуд семейства Венциано. Это содержательное присутствие струнной теории.

**Реализация.** verify.py; таблица пятиточечных вычетов.

**Данные.** Аналитические и численные результаты; экспериментальных событий нет.

**Область вывода.** string.1. Мироволистовый баланс c_mat+c_gh в R134 не вычислен; вычет не подтверждает D=26.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R134_STRINGS_CONNES_ADD_20261120/REPORT.md#L19) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R134_STRINGS_CONNES_ADD_20261120/verify.py#L1)

<a id="e13"></a>
## E13. Амплитуда Вирасоро–Шапиро и вопрос о секторе

**Критическая размерность суперструны** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R134](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r134).

Сверка отношения гамма-функций не устанавливает RNS-содержание материи и духов.

**Реализация.** Проверены девять вычетов в принятой кинематике.

**Данные.** Расчёт.

**Область вывода.** string.2. Для прямой идентификации D=10 отделить кинематический множитель и сектор, задать мироволистовые поля.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R134_STRINGS_CONNES_ADD_20261120/REPORT.md#L20)

<a id="e14"></a>
## E14. Четырёхмерная группа СМ и струнное рассеяние

**Сокращение десятимерной аномалии** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R132](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r132) · [R134](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r134).

В R132 задано представление СМ; в R134 рассчитаны амплитуды. Ни одна операция не задаёт хиральный десятимерный спектр.

**Реализация.** Сохранены разные расчёты обоих блоков.

**Данные.** Теоретические.

**Область вывода.** anomaly.1. Нужно построить I₁₂ и его факторизацию для указанной алгебры.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R132_ADD_YM_CCM_20261119/REPORT.md#L1) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R134_STRINGS_CONNES_ADD_20261120/REPORT.md#L20)

<a id="e15"></a>
## E15. Цвет SU(3) в спектральной геометрии Стандартной модели

**Цветовое калибровочное поле SU(3)** · проверяемая физическая величина уже выведена или используется как вход · донор.

**Адреса.** [R132](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r132).

У донора CCM явно заданы SU(3), цветовой триплет кварков и цветовые синглеты лептонов. Размерность присоединённой алгебры фиксирована этой группой.

**Реализация.** В корпусе проверено препятствие для представления M₃(C) в собственной алгебре меток. Отдельного детекторного счёта глюонов нет.

**Данные.** Теоретический вывод при заданной алгебре.

**Область вывода.** color.1. Графовый сектор R130 сам группу цвета не вывел.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R132_ADD_YM_CCM_20261119/REPORT.md#L1) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R132_ADD_YM_CCM_20261119/REPORT.md#L20)

<a id="e16"></a>
## E16. Свободная чистая SU(3) на компактной сфере

**Цветовое калибровочное поле SU(3)** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · контроль.

**Адреса.** [BH1-sphere](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/ADD_BH1_CCC_PENROSE_20261119/REPORT.md#L3).

Проинтегрирована голономия; наблюдаемая — восприимчивость следа U. Присоединённый характер выражается через фундаментальный след.

**Реализация.** В отчёте заданы интеграл, мера и численная проверка конечного N.

**Данные.** Теоретический численный эталон.

**Область вывода.** color.1. Свободная конечная система имеет свою область применимости относительно взаимодействующей макроскопической плазмы.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/ADD_BH1_CCC_PENROSE_20261119/REPORT.md#L3)

<a id="e17"></a>
## E17. Равновесные фазы чистой SU(3), эталон XB

**Цветовое калибровочное поле SU(3)** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [R135](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r135) · [#161](https://github.com/IgorSabirov/vm-lab/issues/161) · [#167](https://github.com/IgorSabirov/vm-lab/issues/167) · [task:MODEL](https://github.com/IgorSabirov/vm-lab/issues/161) · [task:EOS](https://github.com/IgorSabirov/vm-lab/issues/167) · [PR159](https://github.com/IgorSabirov/vm-lab/pull/159) · [PR185](https://github.com/IgorSabirov/vm-lab/pull/185).

По опубликованным решёточным энтропиям восстановлены p,e,w и тепловой скачок. Для скрытого X отождествление условно.

**Реализация.** replay_eos.py и готовый результат для двух устойчивых фаз.

**Данные.** Решёточные данные Giusti и др., вычислительные; детекторного измерения нет.

**Область вывода.** color.1. Ветви заданы совместно при Tc; метастабильное перекрытие для Δp(T) остаётся открытым.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/research/20261121_donors/xb_su3_eos/README.md#L1) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/research/20261121_donors/xb_su3_eos/replay_eos.py#L1)

<a id="e18"></a>
## E18. Независимые решёточные поля SU(3)

**Цветовое калибровочное поле SU(3)** · представитель явно задан в научном задании · основной объект задания.

**Адреса.** [#164](https://github.com/IgorSabirov/vm-lab/issues/164) · [#165](https://github.com/IgorSabirov/vm-lab/issues/165) · [task:SU3](https://github.com/IgorSabirov/vm-lab/issues/164) · [task:BRIDGE](https://github.com/IgorSabirov/vm-lab/issues/165).

Требуются ансамбли, четырёхточечный отклик и отложенная проверка маркера графа.

**Реализация.** Зарегистрированы критерии #164 и #165.

**Данные.** Предусмотрены первичные решёточные конфигурации; результат термометрии #193 их не заменяет.

**Область вывода.** color.1. Нужно измерение оператора на независимой выборке и проверка мощности, затем перенос.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L518) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L664)

<a id="e19"></a>
## E19. Глюболы в условной чистой теории SU(3)

**Цветовое калибровочное поле SU(3)** · представитель явно задан в научном задании · основной объект задания.

**Адреса.** [#169](https://github.com/IgorSabirov/vm-lab/issues/169) · [task:RELIC](https://github.com/IgorSabirov/vm-lab/issues/169).

Поставлена задача о сети состояний, порталах и распадах; одних восьми цветовых компонент недостаточно для скоростей.

**Реализация.** Имеются контрольные входы; полное замыкание сети записано в критериях.

**Данные.** Требуются матричные элементы и коррелированные скорости.

**Область вывода.** color.1. Нужны реакции, ширины и баланс энергии заявленного сектора.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L1533)

<a id="e20"></a>
## E20. Деконфайнмент чистой SU(3), решётки Shirogane

**Цветовое калибровочное поле SU(3)** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · основной объект.

**Адреса.** [R136](https://github.com/IgorSabirov/vm-lab/blob/414be6e3dc2d294e693689a8cbc506374a735ae1/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r136) · [U013](https://github.com/IgorSabirov/vm-lab/blob/414be6e3dc2d294e693689a8cbc506374a735ae1/analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md#u013) · [#193](https://github.com/IgorSabirov/vm-lab/issues/193) · [#201](https://github.com/IgorSabirov/vm-lab/issues/201) · [PR194](https://github.com/IgorSabirov/vm-lab/pull/194).

На векторных материалах восстановлены шкала температуры и фазовые скачки при общей β.

**Реализация.** extract.py и проверки температурного отображения, межобъёмного контраста и ошибок.

**Данные.** Опубликованные результаты решёточного Монте-Карло, EPS и таблицы. Это не физический детектор.

**Область вывода.** color.1. Для строгой совместной значимости нужны корреляции и детали реализации калибровки.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/414be6e3dc2d294e693689a8cbc506374a735ae1/analysis/R136_SHIROGANE_CALIBRATION/REPORT.md#L5) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/414be6e3dc2d294e693689a8cbc506374a735ae1/analysis/R136_SHIROGANE_CALIBRATION/extract.py#L1)

<a id="e21"></a>
## E21. Дисковые галактики с измеренными кривыми вращения SPARC

Продолжение E21 фиксирует раздельные оценки a₀ и H₀, тест низкопараметрического порога, независимые оценки окружения и внешние профили. [Расчёт](sparc/followup/README.md)

**Галактические ускорения и MOND** · представитель в донорском исследовании, пакете или данных · общий донор данных.

**Адреса.** [CCC-SPARC](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_TL_REVIEW_20261112/REPORT.md#L83) · [review:CCC_TL_20261112](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_TL_REVIEW_20261112/REPORT.md) · [external:CCC_SPARC](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/CCC_SPARC.json).

CCC разбирает обратную реконструкцию с Vobs, а R142 оценивает a₀ на калибровке и отложенных галактиках.

**Реализация.** Исполнены обратный расчёт авторов, прямой оператор CCC и MOND, проверка 130/35 и парный bootstrap по галактикам. [Полный расчёт SPARC](sparc/README.md).

**Данные.** По идентификатору и радиусу совпали 3 391 строка исходного каталога. Авторская выборка содержит 165 галактик и 3 345 общих точек.

**Область вывода.** семейство. Прямой прогноз условен относительно фиксированных D, i, M/L, сферической геометрии и переноса единого порога плотности.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_TL_REVIEW_20261112/REPORT.md#L83) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/CCC_SPARC.json#L6) · [источник 3](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEIGHBOR_EXTERNAL_DATA_USE_20261119/REPORT.md#L74)

<a id="e22"></a>
## E22. Свободные протон и электрон, отношение масс в S2

**Отношение масс протона и электрона** · проверяемая физическая величина уже выведена или используется как вход · компонент.

**Адреса.** [S2](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L27) · [#45](https://github.com/IgorSabirov/vm-lab/issues/45).

В диагностическом базисе записан измеренный m_p/m_e. Указана собственная граница вариации по квазару.

**Реализация.** Численная опора сохранена в JSON; S2 имеет статус проекта.

**Данные.** CODATA 2022 и опубликованное ограничение, без нового фитирования спектра.

**Область вывода.** mass_ratio.1. Для дрейфа нужна модель измерения во времени; число в паспортe служит входом.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L27) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_MICROPHYSICS_AND_ANTHROPIC.md#L371)

<a id="e23"></a>
## E23. α_EM в микрофизике первичного нуклеосинтеза

**Электромагнитная постоянная тонкой структуры** · проверяемая физическая величина уже выведена или используется как вход · компонент.

**Адреса.** [S2](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L27) · [#45](https://github.com/IgorSabirov/vm-lab/issues/45).

В базисе S2 отдельно задана постоянная тонкой структуры; в спецификации названы связанные с ней поправки захвата.

**Реализация.** Проверен путь параметра в спецификации PRIMAT; автоматический override покрывает не все поправки.

**Данные.** CODATA и опубликованные агрегированные ограничения разных эпох.

**Область вывода.** alpha_input.1. Для физического отклика требуется пересчитать согласованный набор скоростей.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L19) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/SPEC.md#L216)

<a id="e24"></a>
## E24. Измеренная α_EM и исторические формулы для неё

**Формулы Эддингтона и Уайлера** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [S2](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L27).

Использование α_EM как входа не реализует гипотезу Эддингтона или формулу Уайлера.

**Реализация.** Есть диагностические поля.

**Данные.** CODATA.

**Область вывода.** семейство. У исторических гипотез свой прогноз и история выбора.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L19)

<a id="e25"></a>
## E25. Электрон-протонная пара и гравитационная связь

**Большое отношение Дирака** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [S2](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L27) · [#45](https://github.com/IgorSabirov/vm-lab/issues/45).

Реестр S2 задаёт α_EM, μ=m_p/m_e и α_G,p. Они определяют отношение сил α_EM μ/α_G,p. В R143 выполнена подстановка.

**Реализация.** Вычисление по сохранённому базису и низкоэнергетической α из R142.

**Данные.** Производная величина из табличных констант.

**Область вывода.** Dirac.1. Отношение сил не задаёт закон G(t); общая масса входит в две переменные.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/S2_PARAMETER_BASIS.json#L33)

<a id="e26"></a>
## E26. Дрейф G в модели Gupta и гипотеза G∝1/t

**Большое отношение Дирака** · проверенная граница переноса или аналогия · контроль двух законов.

**Адреса.** [CCC-drift](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_BBN_DRIFT_20261113/REPORT.md#L22) · [#37](https://github.com/IgorSabirov/vm-lab/issues/37) · [review:CCC_TL_20261112](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_TL_REVIEW_20261112/REPORT.md).

CCC вычисляет G/G₀=f³ при экспоненциальном f. Можно сопоставить безразмерные производные при заданных часах.

**Реализация.** calculate.py, интеграл часов и дрейф за окно BBN.

**Данные.** Расчёт из параметров донора; локального измерения Ġ/G здесь нет.

**Область вывода.** Dirac.1. Требуются отдельный перенос к локальным часам и данные лунной локации.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_BBN_DRIFT_20261113/REPORT.md#L22) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_BBN_DRIFT_20261113/calculate.py#L1)

<a id="e27"></a>
## E27. Λ в опубликованном фоне космологической симуляции Lumina

**Космологическая постоянная и планковский масштаб** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [R137](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r137) · [#196](https://github.com/IgorSabirov/vm-lab/issues/196).

В интеграле τ заданы H₀ и ΩΛ; из них в R143 получены Λℓₚ² и ρΛ/ρₚ.

**Реализация.** verify.py задаёт параметры фона и интеграл τ.

**Данные.** Параметры референсной космологии, таблицы симуляции; отсутствует независимое измерение Λ из τ этим расчётом.

**Область вывода.** Lambda.1. Указать конвенцию и общий вход H₀; микроскопический механизм величины остаётся открытым.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/R137_LUMINA/verify.py#L48) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/R137_LUMINA/verify.py#L56)

<a id="e28"></a>
## E28. Матрицы Юкавы и смешивание нейтрино в донорской СМ

**Смешивание активных нейтрино** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R132](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r132).

Состав конечного оператора CCM допускает массы и смешивание; значения углов требуют входов.

**Реализация.** R132 исследует представления; реакторный фит в нём отсутствует.

**Данные.** Математическая модель.

**Область вывода.** mixing.1. Нужны конкретные PMNS, θ₁₃ и статистика для проверки точного Ue3=0.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R132_ADD_YM_CCM_20261119/REPORT.md#L17)

<a id="e29"></a>
## E29. Заряженные лептоны в фермионном секторе CCM

**Отношение Коиде** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R132](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r132).

Лептонные представления и параметры масс входят в модель; отношение трёх масс не навязано.

**Реализация.** R132 проверяет алгебру представлений. Прогноза массы τ здесь нет.

**Данные.** Теоретическая модель.

**Область вывода.** Koide.1. Для проверки Коиде нужны три массы в одной схеме, датировка входов и правило выбора решения.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R132_ADD_YM_CCM_20261119/REPORT.md#L17) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R132_ADD_YM_CCM_20261119/REPORT.md#L20)

<a id="e30"></a>
## E30. Активные ароматы реликтовых нейтрино

**Смешивание активных нейтрино** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R135](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r135) · [component:NEUTRINO_KINETIC_BRIDGE](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEUTRINO_GW_ARCHITECTURE_20261118/REPORT.md#neutrino_kinetic_bridge).

Mangano et al. решают задачу с осцилляциями; пакет заимствует оператор Лиувилля, множители Паули и баланс энергии.

**Реализация.** В sources.json явно ограничен перенос полной матрицы; контроль слабых скоростей отдельно исключает осцилляции.

**Данные.** Донорский расчёт; реакторных событий Daya Bay здесь нет.

**Область вывода.** mixing.1. Реализовать или подключить полный flavour-оператор прежде чем испытывать гипотезу смешивания.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/c3bc771d1daa292d5d9fd3e1d17bf4d3d6d01c92/analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/neutrino_reference/sources.json#L15) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/c3bc771d1daa292d5d9fd3e1d17bf4d3d6d01c92/analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/extensions_reference/validate_p7_bbn.py#L4)

<a id="e31"></a>
## E31. Осциллирующие атмосферные нейтрино в KM3NeT/ORCA

**Смешивание активных нейтрино** · представитель в донорском исследовании, пакете или данных · донор наблюдений.

**Адреса.** [component:KM3NET_NEUTRINO_CONSTRAINTS](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEUTRINO_GW_ARCHITECTURE_20261118/REPORT.md#km3net_neutrino_constraints) · [review:NEUTRINO_GW_ARCHITECTURE_20261118](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEUTRINO_GW_ARCHITECTURE_20261118/REPORT.md) · [#100](https://github.com/IgorSabirov/vm-lab/issues/100).

Зарегистрированы зависимые анализы одной выборки ORCA, измеряющие параметры расширений осцилляционной модели.

**Реализация.** Сохранены паспорта пределов; полное правдоподобие не восстановлено.

**Данные.** Опубликованные экспериментальные пределы; сырые события и реакторные спектры отсутствуют.

**Область вывода.** mixing.1. Для TBM нужна собственная измерительная модель θ₁₃; предел NSI её не заменяет.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEUTRINO_GW_ARCHITECTURE_20261118/REPORT.md#L70) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEUTRINO_GW_ARCHITECTURE_20261118/KM3NET_NEUTRINO_CONSTRAINTS.json#L7)

<a id="e32"></a>
## E32. Двоичные кольца и определитель на сериях единиц

**Фибоначчиева квазипериодическая цепочка** · проверенная граница переноса или аналогия · методический контроль.

**Адреса.** [R141](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r141) · [C028](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json) · [L07](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json) · [U010](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md#u010).

Рекурсия трёхдиагонального блока даёт F(2l+1). В R142 порядок двух типов узлов задаётся подстановкой; проверяется спектральная щель.

**Реализация.** Точный расчёт в обоих блоках, роли операторов различны.

**Данные.** Численные и алгебраические результаты; эксперимент поляритонной цепи к R141 не отнесён.

**Область вывода.** phi.1. Перенос потребовал бы физического отображения узлов, связей и измерительной процедуры.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/R141_RIEMANN_CORPUS/spectral/FIBONACCI.md#L7) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/15052f12371f1366e8e51f5d251033b1376739c0/analysis/R142_MAGIC_NUMBERS/GENEALOGY.md#L11)

<a id="e33"></a>
## E33. Локальное удвоение периода спинов у донора DTL

**Каскад Фейгенбаума и контроль другого класса** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R027](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r027) · [C017](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json).

Обнаружен конкретный донор удвоения периода, но у него описаны локальные переключения фазы. Последовательность порогов каскада не извлечена.

**Реализация.** Прочитан препринт; E002d рассчитывает другие временные корреляции.

**Данные.** Модель донора и численные пробы E002d.

**Область вывода.** семейство. Нужны семейство карт и последовательные бифуркации одного максимума.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/DTL_MODEL_REVIEW_20261031/REVIEW.md#L15)

<a id="e34"></a>
## E34. Табличная ссылка на δ в исторической выписке

**Каскад Фейгенбаума и контроль другого класса** · проверенная граница переноса или аналогия · методическая аналогия.

**Адреса.** [historical-excerpts](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RECOVERED_SOURCE_EXCERPTS.md#L562).

Ссылка сопоставляет δ с монотонностью N2; карты и параметры бифуркации отсутствуют.

**Реализация.** Текстовая гипотеза.

**Данные.** Отсутствуют.

**Область вывода.** семейство. На таком основании адрес физического каскада не добавляется.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RECOVERED_SOURCE_EXCERPTS.md#L562)

<a id="e35"></a>
## E35. Предложенная осцилляторная ванна для континуума

**Оболочки изотропного 3D-осциллятора** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [X26](https://github.com/IgorSabirov/vm-lab/blob/b919e64ad89a5afe2c395a0218895c856088c57d/analysis/X26_NEIGHBOR_REVIEW_20261109/NEIGHBOR_SOURCE.txt#L349).

Донор предлагает описать резервуар набором гармонических осцилляторов. Структура трёхмерной оболочки с заполнением не задана.

**Реализация.** Это предложение в отзыве.

**Данные.** Отсутствуют.

**Область вывода.** семейство. Требуются изотропная ловушка, тройки квантовых чисел и заполнение по спину.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/b919e64ad89a5afe2c395a0218895c856088c57d/analysis/X26_NEIGHBOR_REVIEW_20261109/NEIGHBOR_SOURCE.txt#L349)

<a id="e36"></a>
## E36. Ядерные спины, дырки и протонные дефекты

**Щель Холдейна** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [C021](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json) · [L05](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json).

Карточка C021 обсуждает многочастичную организацию. Наличие спинов не задаёт антиферромагнитную цепь S=1.

**Реализация.** В карточке нет измерения щели Холдейна.

**Данные.** Для этой щели данных нет.

**Область вывода.** Haldane.1. Нужны гамильтониан, спин узла, геометрия, J и предел длины.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json#L5689)

<a id="e37"></a>
## E37. Цветовая SU(3) и ароматная SU(3) барионного декуплета

**Декуплет барионов и Ω⁻** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R132](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r132) · [R136](https://github.com/IgorSabirov/vm-lab/blob/414be6e3dc2d294e693689a8cbc506374a735ae1/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r136).

Действие цветовой алгебры и чистая глюодинамика не образуют декуплет u,d,s. Для Ω⁻ нужны аромат и барионные операторы.

**Реализация.** Решёточная EOS и отчёт о представлениях.

**Данные.** Нет измерения массы Ω⁻ в этих работах.

**Область вывода.** Omega.1. Установить оператор бариона и данные спектроскопии.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R132_ADD_YM_CCM_20261119/REPORT.md#L20)

<a id="e38"></a>
## E38. ⁴He как ядро в BBN и как вещество двумерной плёнки

**Переход БКТ** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [BBN-pair](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/PRIMAT_LINX_BBN_BRIDGE_20261117/PAIRED_RUN_20261120.md#L7).

В таблице BBN записана массовая доля гелия; температура плёнки, вихри и её жёсткость отсутствуют.

**Реализация.** Вычислены содержания.

**Данные.** Численные выходы BBN.

**Область вывода.** BKT.1. Для БКТ нужны плёнка и Υ(T) при подходящих частоте и размере.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/PRIMAT_LINX_BBN_BRIDGE_20261117/PAIRED_RUN_20261120.md#L7)

<a id="e39"></a>
## E39. Активные ароматы нейтрино в FortEPiaNO

**Смешивание активных нейтрино** · представитель в донорском исследовании, пакете или данных · донор программного пакета.

**Адреса.** [external:FORTEPIANO_QKE](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/FORTEPIANO_QKE.json).

Контракт задаёт полный эталон Стандартной модели с импульсной и ароматной матрицей.

**Реализация.** Контракт поставлен в draft, запуск по этому паспорту отключён.

**Данные.** Теоретический пакет.

**Область вывода.** mixing.1. Для вывода о Ue3 нужен отдельный осцилляционный тест и соответствующее экспериментальное правдоподобие.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/FORTEPIANO_QKE.json#L8)

<a id="e40"></a>
## E40. ⁴He как продукт двух BBN-сетей

**Классические замыкания ядер** · представитель в донорском исследовании, пакете или данных · программные доноры.

**Адреса.** [external:PRIMAT](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/PRIMAT.json) · [external:LINX](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/LINX.json) · [component:BBN_RESPONSE_BRIDGE](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEUTRINO_GW_ARCHITECTURE_20261118/REPORT.md#bbn_response_bridge).

Реализации независимо адресованы в реестре пакетов, фактическое исполнение засвидетельствовано парным отчётом.

**Реализация.** PRIMAT, LINX, сравнение общих и нативных входов.

**Данные.** Массивы численного выхода и ядерные скорости.

**Область вывода.** nuclear.1. Одинаковые скорости в 17 парах надо считать общим входом.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/PRIMAT_LINX_BBN_BRIDGE_20261117/PAIRED_RUN_20261120.md#L10) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/LINX.json#L8) · [источник 3](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/infra/external/contracts/PRIMAT.json#L8)

<a id="e41"></a>
## E41. Дискретный тример и защита тёмного состояния

**Эфимовские тримеры** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R040](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r040) · [X26](https://github.com/IgorSabirov/vm-lab/blob/b919e64ad89a5afe2c395a0218895c856088c57d/analysis/X26_NEIGHBOR_REVIEW_20261109/NEIGHBOR_SOURCE.txt#L349).

Трёхузельная система рассмотрена в контексте BIC. Для неё не заданы три резонансных бозона и последовательность длин рассеяния.

**Реализация.** Имеется таблица тримера в аудите и отдельный вычислительный прототип X26.

**Данные.** Модельные результаты.

**Область вывода.** Efimov.1. Требуются резонансный короткодействующий потенциал и минимум два трёхчастичных масштаба.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/BIC_SMOKE_AUDIT_20261103/PEER_CLAIMS.json#L29)

<a id="e42"></a>
## E42. Четырёхконтактный отклик графа

**Контактное число в 3D** · проверенная граница переноса или аналогия · контроль границы.

**Адреса.** [R135](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r135).

Физический смысл контакта в графовом контроле задаётся операциями на графе. Геометрия равных касающихся сфер в нём не задана.

**Реализация.** Имеется программный контроль отклика графа.

**Данные.** Расчёт.

**Область вывода.** kissing.1. Для числа касаний требуется упаковка неперекрывающихся равных сфер в евклидовом пространстве.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/README.md#L16)

<a id="e43"></a>
## E43. Супергравитация типа IIB на глобальном AdS₅×S⁵

**Критическая размерность суперструны** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · основной объект.

**Адреса.** [BH1-A∞](https://github.com/IgorSabirov/vm-lab/blob/98c101bc9621d99439a462140980166cd9610378/analysis/CCC_BBN_NETWORK_20261114/s3_standard/BH1_AINF_K1_20261116/AINF_KK_GAS_CONTRACT.md#L5).

В контракте тепловой ветви явно заданы десятимерный фон и спектр Калуцы–Клейна типа IIB. Это собственный адрес именно десятимерного сектора за пределами R142.

**Реализация.** Аналитический контракт и проверка каталога; полная тепловая сумма приостановлена до разбора характера k=2.

**Данные.** Теоретический донор; нового машинного или физического эксперимента в этой поставке нет.

**Область вывода.** string.2. Десять измерений заданы выбором фона. Вывод критической размерности из мироволистовой аномалии — другая операция.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/98c101bc9621d99439a462140980166cd9610378/analysis/CCC_BBN_NETWORK_20261114/s3_standard/BH1_AINF_K1_20261116/AINF_KK_GAS_CONTRACT.md#L5) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/98c101bc9621d99439a462140980166cd9610378/analysis/CCC_BBN_NETWORK_20261114/s3_standard/BH1_AINF_K1_20261116/REPORT.md#L4)

<a id="e44"></a>
## E44. Фон base-ΛCDM наблюдательного контроля Planck

**Космологическая постоянная и планковский масштаб** · представитель в донорском исследовании, пакете или данных · донор данных.

**Адреса.** [R135](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r135) · [Planck-PR3](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/planck_pr3/README.md#L13).

Проверены опубликованный опорный спектр и компоненты правдоподобия TT/TE/EE. Наличие Λ в модели засвидетельствовано выбором эталона.

**Реализация.** Сверены файлы ESA/IRSA, манифест и значения ln L на контрольных векторах.

**Данные.** Наблюдательные продукты Planck и ковариации; эталонный теоретический спектр отмечен отдельно.

**Область вывода.** Lambda.1. Одно значение ln L на эталоне не даёт собственной оценки Λ или её планковского масштаба.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/planck_pr3/README.md#L13)

<a id="e45"></a>
## E45. ⁴He как связующее звено BBN и CMB у доноров ACT/CAMB

**Классические замыкания ядер** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · компонент.

**Адреса.** [review:BBN_DONORS_TRANSFER_20261120](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEIGHBOR_EXTERNAL_DATA_USE_20261119/BBN_METHOD_TRANSFER.md) · [component:BBN_CMB_OBSERVATIONS](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEUTRINO_GW_ARCHITECTURE_20261118/REPORT.md#bbn_cmb_observations) · [ACT-CAMB](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEIGHBOR_EXTERNAL_DATA_USE_20261119/REPORT.md#L28).

Сверено 1300 координат двух таблиц. В опубликованном интерфейсе раздельны 4nHe/nb и массовая доля; они передают ядерный результат к расчёту CMB.

**Реализация.** Корпус сравнил файлы двух версий PRIMAT из CAMB; наблюдательный анализ ACT приведён по публикации.

**Данные.** Таблицы теоретических выходов; данные CMB относятся к последующему анализу доноров.

**Область вывода.** nuclear.1. Нужно сохранять определение Yp при межпакетной передаче. Оболочечный гамильтониан здесь не восстанавливался.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEIGHBOR_EXTERNAL_DATA_USE_20261119/REPORT.md#L28) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/NEIGHBOR_EXTERNAL_DATA_USE_20261119/REPORT.md#L30)

<a id="e46"></a>
## E46. Скрытый сектор на основе чистой SU(3), условная шкала релаксации

**Цветовое калибровочное поле SU(3)** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · контроль.

**Адреса.** [BH1-relaxation](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/BH1_SU3_RELAXATION_GATE_20261120/REPORT.md#L65).

Рассчитано отношение микроскопического времени к времени расширения при mX=Tc и отсутствии критического замедления.

**Реализация.** Сохранён расчёт и явно ограниченный вывод о времени.

**Данные.** Публикационные решёточные входы и теоретическая подстановка.

**Область вывода.** color.1. Микроскопический контроль не задаёт затухания коллективной координаты, нуклеации и роста.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/BH1_SU3_RELAXATION_GATE_20261120/REPORT.md#L65)

<a id="e47"></a>
## E47. Чистая SU(3) как возможный физический источник в задаче GW

**Цветовое калибровочное поле SU(3)** · представитель явно задан в научном задании · компонент задания.

**Адреса.** [#174](https://github.com/IgorSabirov/vm-lab/issues/174) · [task:GW_SOURCE](https://github.com/IgorSabirov/vm-lab/issues/174).

В поставке #174 явно указан вариант XB с данными двух фаз. Это реальный выбор донора для построения источника.

**Реализация.** EOS и численная передача существуют раздельно; весь спектр из пузырей и плазмы не выведен.

**Данные.** Термодинамические данные решёточных расчётов, без независимого наблюдения GW от этого X.

**Область вывода.** color.1. Нужны метастабильные ветви, динамика превращения и стресс источника.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/research/20261121_donors/xb_su3_eos/README.md#L3)

<a id="e48"></a>
## E48. Массовая доля ⁴He как тест переноса слабых скоростей

**Классические замыкания ядер** · представитель явно задан в научном задании · контроль задания.

**Адреса.** [#55](https://github.com/IgorSabirov/vm-lab/issues/55) · [#172](https://github.com/IgorSabirov/vm-lab/issues/172) · [task:WEAK](https://github.com/IgorSabirov/vm-lab/issues/172).

В #172 критерий WEAK-03 задаёт проверку Yp в двух решателях. В #55 та же наблюдаемая входит в постановку ковариации.

**Реализация.** Контроль задан в работе с BBN-сетями; точностное требование проверяется отдельно.

**Данные.** Модельный выход, которому передаётся неопределённость микрофизики.

**Область вывода.** nuclear.1. Нужны независимая ошибка эталона и исполнение критерия WEAK-03.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L2085)

<a id="e49"></a>
## E49. ⁴He как выход распространения лабораторных ошибок ядерных реакций

**Классические замыкания ядер** · представитель явно задан в научном задании · контроль задания.

**Адреса.** [#176](https://github.com/IgorSabirov/vm-lab/issues/176) · [task:NUCLEAR](https://github.com/IgorSabirov/vm-lab/issues/176).

В конечном совместном распределении явно заданы Yp и D/H. Источниками ошибок служат связанные скорости, а не магичность ⁴He.

**Реализация.** Для прежнего приора имеются прогоны; целевому ковариационному переносу нужны новые расчёты.

**Данные.** Лабораторные сечения и ошибки по реакциям; Yp здесь предсказывается.

**Область вывода.** nuclear.1. Сохранить совместные выборки и температурные корреляции, провести через обе сети.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L2756)

<a id="e50"></a>
## E50. Размерная шкала, часы и нуклеация в варианте XB чистой SU(3)

**Цветовое калибровочное поле SU(3)** · представитель явно задан в научном задании · компонент заданий.

**Адреса.** [#162](https://github.com/IgorSabirov/vm-lab/issues/162) · [#166](https://github.com/IgorSabirov/vm-lab/issues/166) · [#168](https://github.com/IgorSabirov/vm-lab/issues/168) · [task:SCALE](https://github.com/IgorSabirov/vm-lab/issues/162) · [task:CLOCK](https://github.com/IgorSabirov/vm-lab/issues/166) · [task:NUCLEATION](https://github.com/IgorSabirov/vm-lab/issues/168).

В задачах определены разные физические выходы: абсолютный масштаб, динамическая релаксация и образование пузырей. Решёточная термодинамика выступает входом или ограничением.

**Реализация.** Есть паспорт EOS и отдельные условные контроли. Полный расчёт всех трёх выходов не предъявлен.

**Данные.** Решёточные доноры, вычислительные результаты.

**Область вывода.** color.1. Раздельно получить масштаб, кинетический коэффициент и префактор нуклеации. Один статический скачок их не определяет.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L203) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L821) · [источник 3](https://github.com/IgorSabirov/vm-lab/blob/e10e02021a06916aaca3eaa3e767b44bb31d4d2e/infra/r135/PIPELINE.json#L1276)

<a id="e51"></a>
## E51. Чистые решёточные поля SU(3) у спектрального донора R141

**Цветовое калибровочное поле SU(3)** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R141](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r141) · [Gattringer](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/R141_RIEMANN_CORPUS/donor_replay/REPORT.md#L131).

Gattringer выражает петлю Полякова спектральной суммой; в первичной работе явно проверены quenched SU(3) конфигурации. На ADD воспроизведена техника выделения по фазе границы.

**Реализация.** В R141 проверена конечная графовая операция. Полный измеренный SU(3) ансамбль донора в неё не перенесён.

**Данные.** Численный эксперимент первоисточника; собственный контроль ADD теоретический.

**Область вывода.** color.1. Для проверки переноса нужна одна и та же физическая наблюдаемая на независимых решёточных полях.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/da82cff22e5a791ea06e04393917bfa062e0af6e/analysis/R141_RIEMANN_CORPUS/donor_replay/REPORT.md#L131)

<a id="e52"></a>
## E52. Нейтральный He I в химической сети симуляции Lumina

**Замкнутые электронные оболочки** · представитель в донорском исследовании, пакете или данных · донор.

**Адреса.** [R137](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md#r137) · [external:LUMINA](https://github.com/IgorSabirov/vm-lab/blob/a8cb47fd47a1597c115b8afda7dfac9a8403590f/infra/external/contracts/LUMINA.json) · [review:CCC_TL_20261112](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/CCC_TL_REVIEW_20261112/REPORT.md).

В описании использованного физического донора явно указана реионизация He I и He II. Для отдельной собственной проверки R137 извлечена доля He III; эти объекты размечены раздельно.

**Реализация.** Сеть H/He работает у донора. Корпус повторил интеграл τ и обработал несколько опубликованных таблиц.

**Данные.** Численная радиационная гидродинамика и её открытые агрегаты.

**Область вывода.** noble.1. Показать спектральную подпись электронной оболочки нейтрального He из сетевой доли нельзя.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/a8cb47fd47a1597c115b8afda7dfac9a8403590f/analysis/CCC_TL_REVIEW_20261112/REPORT.md#L121) · [источник 2](https://github.com/IgorSabirov/vm-lab/blob/873480d376f20e304a1d9649c22cc88be6fef975/analysis/R137_LUMINA/REPORT.md#L14)

<a id="e53"></a>
## E53. Первичный ⁴He в полном контрольном прогоне CCC–BBN S1

**Классические замыкания ядер** · тот же конкретный носитель, иная наблюдаемая или новый пересчёт в R143 · основной выход.

**Адреса.** [CCC-S1](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/s1_fullnet/results/S1_FULLNET_20261114_r1/REPORT.md#L3) · [#50](https://github.com/IgorSabirov/vm-lab/issues/50).

Сопоставлены Yp в контрольном, общем масштабировании часов и отрицательном контроле только охлаждения.

**Реализация.** В опубликованной таблице Yp=0,2470017859, 0,2470017863 и 0,0560519871 соответственно.

**Данные.** Три результата интегрирования; экспериментальной таблицы оболочечных уровней нет.

**Область вывода.** nuclear.1. Общий масштаб времени проверен условно. Для происхождения ядерной щели нужен отдельный гамильтониан.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/6a42f7ebed1b00df878b4f9d21d97f47ee958ba0/analysis/CCC_BBN_NETWORK_20261114/s1_fullnet/results/S1_FULLNET_20261114_r1/REPORT.md#L3)

<a id="e54"></a>
## E54. Первичный гелий как предполагаемая наблюдаемая сопряжения BH1–BBN

**Классические замыкания ядер** · представитель явно задан в научном задании · компонент задания.

**Адреса.** [BH1-BBN](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R130_BH1_BBN_CONNECTION_20261117/REPORT.md#L69) · [#92](https://github.com/IgorSabirov/vm-lab/issues/92).

В контракте явно задана пара Yp и D/H, необходимая для различения тепловых историй. Это отдельная постановка на стыке блоков.

**Реализация.** У собственного автомата ADD нет опубликованного вывода этих содержаний из шага графа.

**Данные.** Контракт опирается на существующие BBN-пакеты.

**Область вывода.** nuclear.1. Требуются физические часы, энергия и закон передачи в плазму. Этот адрес не приписывает ядерный гамильтониан R130.

[источник 1](https://github.com/IgorSabirov/vm-lab/blob/fd94fd351f1cef2b269529ad07d3116b3040385d/analysis/R130_BH1_BBN_CONNECTION_20261117/REPORT.md#L69)
