# Рабочая доска GitHub Projects для vm-lab

Статус: **настройка описана, Project V2 не создан и не подключён из этого коммита**. Доступный GitHub-коннектор позволяет работать с файлами, Issues, ветками и PR, но не предоставляет операции создания/настройки Projects V2. Поэтому здесь фиксируется точная конфигурация для однократного включения через авторизованный Projects API или UI; это не имитация созданной доски.

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

## Однократная настройка

1. Создать один Project V2 уровня пользователя с названием «vm-lab — рабочая очередь».
2. Создать перечисленные поля; Status должен содержать перечисленные значения.
3. Добавить репозиторий IgorSabirov/vm-lab.
4. Включить встроенное правило добавления для новых Issues и PR. Начать с фильтра is:issue,pr; при появлении отдельной метки work:active сузить до is:issue,pr label:work:active.
5. Включить правило: новый элемент получает Status = Inbox (не Done).
6. Не создавать автоматизацию, которая меняет научные статусы или закрывает вопросы U по состоянию Issue/PR.

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

Ранний снимок 12 ноября: браузер и CLI не были авторизованы, репозиторий был приватным. Позже 12 ноября GitHub API подтвердил public и admin для коннектора. Методов Projects/административных мутаций в коннекторе нет; доска всё ещё не создана. Дополнительные поля: Decision IDs, Run ID, Exact source SHA. Значения Permission — описание поручения, а не credential или разрешение запуска. Встроенное автодобавление включать только для vm-lab и активных задач; научные статусы не синхронизировать из Status.

## Готовая автоматизация настройки

`python tools/github_setup.py project` показывает конкретный план; `--apply`
создаёт/дополняет одну доску, сохраняет ID существующих options, связывает репозиторий
и добавляет открытые Issues/PR. Требуется явно переданный GH_TOKEN с Projects-доступом.
Репозиторий публичный; это не выдаёт токен этому скрипту. Built-in auto-add настраивается
в UI один раз и скриптом не заявляется включённым. Статус Done не меняет R/U/N.
