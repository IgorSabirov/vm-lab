# Рабочая доска vm-lab

11 ноября 2026. Это схема операционного Project для текущих задач, а не второй научный реестр. R/C/L/U/N остаются в существующих JSON/Markdown-источниках.

## Принцип

В Project попадают активные задачи, решения и PR, а не все 129 результатов. Закрытие Issue, слияние PR или перемещение карточки в Done не меняет научный статус R/C/L/U и не закрывает предпосылку.

Формы задач находятся в `.github/ISSUE_TEMPLATE/`; PR-шаблон — `.github/pull_request_template.md`.

## Рекомендуемый Project

Создать один GitHub Project v2 на уровне репозитория или владельца: **vm-lab — рабочий поток**.

### Поля

| Поле | Тип | Значения / назначение |
|---|---|---|
| Stage | Single select | Inbox, Analysis, Ready, Running, Review, Done, Parked |
| Work class | Single select | Science, Evidence/QA, Infrastructure |
| Permission scope | Single select | Read-only, Docs-only, Local compute, VM plan, Explicit VM execution |
| Registry refs | Text | R/C/L/U/N IDs; ссылки на конкретные карточки |
| Parent / source | Text | Родительский commit, branch, issue или исходный артефакт |
| Acceptance criterion | Text | Наблюдаемый критерий завершения |
| Next action | Text | Следующее конкретное действие |
| Scientific status | Не дублировать | Читать только из реестра; не вычислять из Stage |

### Представления

1. **Активная доска:** Inbox → Analysis → Ready → Running → Review → Done.
2. **Научные вопросы:** только карточки Work class = Science; группировка по U/R/C.
3. **Инфраструктура:** CI, registry compiler, source provenance, templates, packaging.
4. **Заблокировано:** Stage = Parked; в карточке указывается конкретная зависимость.
5. **Готово к исполнению:** Ready плюс явно ограниченный Permission scope; это не разрешение на запуск само по себе.

## Правила автоматизации

- Новые активные Issue можно добавлять в Project вручную или правилом по метке, когда метки будут созданы в репозитории.
- Закрытие Issue может переместить операционную карточку в Done; оно не меняет научный статус.
- Слияние PR закрывает связанную инфраструктурную задачу только при наличии явного completion criterion.
- Не создавать Issue для каждой записи R/C/L/U/N.
- Не запускать ВМ из Project automation.
- Не автоматизировать научную приёмку, выбор субстрата, меры, закона или физической архитектуры.

## Ограничение текущей интеграции

В доступном GitHub API-коннекторе нет операций создания/настройки Projects v2 и custom fields. Поэтому этот файл фиксирует согласованную схему, но сама доска ещё не создана. После ручного создания Project его URL можно добавить сюда и в README.
