# Рабочая доска GitHub Projects для vm-lab

Статус: **создана и проверена 12 ноября 2026**: [vm-lab — рабочая очередь](https://github.com/users/IgorSabirov/projects/2). Доска частная, привязана к IgorSabirov/vm-lab. Первая успешная квитанция: [PROJECTS_STATUS.json](PROJECTS_STATUS.json), [запуск Actions](https://github.com/IgorSabirov/vm-lab/actions/runs/43207606456). Проверены 10 полей и 7 карточек. Квитанция — датированный снимок; текущие сверки доступны в Actions.

## Назначение

Одна доска для активной работы, не копия научного реестра. Не создавать 129 карточек для 129 R-записей. На доске находятся только задачи, требующие действия.

## Поля

| Поле | Тип | Значения/смысл |
|---|---|---|
| Status | Single select | Inbox, Analysis, Ready, Running, Review, Done, Parked |
| Work kind | Single select | Science, Analysis, Code, Infrastructure, Documentation |
| Permission | Single select | Read-only, Docs, Code, Local compute, VM-authorized |
| Lineage | Text | R/C/L/U/N IDs; ссылки на реестр |
| Next action | Text | Одно ближайшее действие |
| Acceptance | Text | Наблюдаемый критерий завершения |
| Budget | Text | Известный предел; неизвестное не подменять оценкой |

**Status — только рабочее положение карточки.** Закрытие Issue, слияние PR и перемещение в Done не меняют научный статус R/C/L/U/N.

## Создание и синхронизация через Actions

Секрет `PROJECTS_TOKEN` хранится в GitHub Actions; значение не попадает в код,
отчёт или чат. Workflow [Projects working board](../.github/workflows/projects-sync.yml)
проверяет/создаёт одну доску указанного владельца и названия, добавляет поля,
сохраняет ID и дополнительные варианты существующих select-полей, связывает vm-lab.
Закрытая доска или несколько одноимённых досок вызывают явную остановку.

Первый запуск подхватывает открытые Issues/PR. Последующие проверяют открытые
задачи и уже отслеживаемые закрытые. Архивированные вручную элементы и элементы
других репозиториев не меняются. Поля формы Issue переносятся только в пустые
поля Projects. У PR обновляется Exact source SHA. Permission — описание текста
поручения, **никогда не выдача полномочий или команда запуска**.

Правила Status:

- Новая Issue или draft PR → Inbox; готовый PR → Review.
- Завершённая Issue / слитый PR → Done; not_planned Issue / закрытый без слияния PR → Parked.
- У открытых задач сохраняются ручные Analysis, Ready, Running, Parked и дополнительные статусы.
- Открытая задача с прежним Done возвращается в Inbox/Review; смена draft у PR меняет Inbox/Review.

Запуски: события Issues; завершение короткого [Project events](../.github/workflows/project-events.yml)
для событий PR; изменение кода настройки в main; ручной запуск; почасовая сверка
на 23-й минуте (расписание GitHub может задерживаться). При PR не читаются артефакты
и не выполняется код ветки: секрет доступен только шагу синхронизации кода из main.
`pull_request_target` не используется. Все изменения проверяются повторным чтением
API (до шести чтений, ожидания 1/2/4/8/16 s для задержек отображения записи; мутации не повторяются); квитанция с URL, полями и изменёнными элементами сохраняется в Actions на 7 дней.

Встроенный auto-add Projects не требуется: его задачу выполняет эта синхронизация.
Она не закрывает научные U-вопросы, не редактирует реестры, не запускает ВМ,
не сливает PR и не изменяет видимость доски.

## Почему нет work:active по умолчанию

В текущем репозитории не подтверждено существование согласованной системы меток. Форма Issue поэтому не присваивает выдуманную метку. Сначала владелец создаёт её в настройках Labels либо решает оставить автоматическое добавление всех Issues/PR.

## Связь с остальной инфраструктурой

- Intake: [Issue Form](../.github/ISSUE_TEMPLATE/research-task.yml).
- Приёмка изменений: [PR template](../.github/pull_request_template.md).
- Научные результаты и вопросы остаются в своих реестрах.
- Типизированная навигация: [Registry Links](../analysis/REGISTRY_LINKS/INDEX.md).
- Разделение науки и инфраструктуры: [директива](../SCIENCE_INFRASTRUCTURE_SEPARATION.md).

Официальная документация GitHub: [Quickstart for Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/quickstart-for-projects) и [automatic item addition](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/adding-items-automatically).

## Проверка 12 ноября

Ранний снимок 12 ноября: браузер и CLI не были авторизованы, репозиторий был приватным. Позже 12 ноября GitHub API подтвердил public и admin для коннектора. Методов Projects/административных мутаций в коннекторе нет; на том этапе доска ещё не была создана. После добавления PROJECTS_TOKEN владельцем создание и readback выполнены через Actions; текущая ссылка приведена выше. Дополнительные поля: Decision IDs, Run ID, Exact source SHA. Значения Permission — описание поручения, а не credential или разрешение запуска. Встроенное автодобавление включать только для vm-lab и активных задач; научные статусы не синхронизировать из Status.

## Команды

`python tools/github_setup.py project` показывает план без изменений.
`python tools/github_setup.py project --apply` выполняет настройку и сверку через
явно переданный GH_TOKEN. Actions использует ту же реализацию:
`python tools/project_sync.py --apply`, а не выводит секрет наружу.
Проверка работоспособности — URL и verified=true в PROJECTS_STATUS.json после
повторного чтения API. Наличие секрета само по себе не считается успехом.
