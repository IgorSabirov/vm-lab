#!/usr/bin/env python3
"""Render operational Issue intake from the reviewed R135 task map; no API calls."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = 'https://github.com/IgorSabirov/vm-lab'
MAP_PATH = 'infra/r135/PIPELINE.json'


def ref(task):
    number = task.get('issue_number')
    return f"#{number}" if number else f"`{task['key']}` (связь в #155)"


def issue_body(task, plan):
    tasks = {t['key']: t for t in plan['tasks']}
    required = '\n'.join(f"- {ref(tasks[key])}: {tasks[key]['title']}" for key in task['depends_on'])
    conditional = '\n'.join(f"- {ref(tasks[d['key']])}: {d['when']}" for d in task['conditional_dependencies'])
    sources = '\n'.join(f"- [{p.rsplit('/',1)[-1]}]({REPO_URL}/blob/{task['source_commit']}/{p})" for p in dict.fromkeys(task['sources']))
    checks = '\n'.join(f"- [ ] **{c['id']}** — {c['criterion']}" for c in task['acceptance_checks'])
    consumers = [t for t in plan['tasks'] if task['key'] in t['depends_on']
                 or any(d['key'] == task['key'] for d in t['conditional_dependencies'])]
    onward = ', '.join(ref(t) for t in consumers) or '#155: итоговая приёмка заявленного объёма'
    responsibilities = '\n'.join('- ' + s for s in task['responsibility'].values())
    return f"""<!-- r135-pipeline-task:{task['key']} -->
### Тип работы
Аналитический вывод или аудит доказательства

### Рабочий блок R135
{task['block']}

### Главный вопрос
{task['goal']}

### Генеалогия
R135; R131–R134; C037; U006. Этапы: {', '.join(task['stages'])}. Область: {', '.join(task['claims'])}. Главный трекер #155; рабочий ключ `{task['key']}`.

### Исходный commit
{task['source_commit']}

### Уже получено
{task['known']}

### Входы
{task['inputs']}

### Что должно измениться в знании или репозитории
{task['deliverable']}

### Критерий завершения
{task['deliverable']} Приёмка требует выполнения перечисленных ниже критериев по первичным артефактам и отдельному воспроизводимому повтору; сообщение GPT или зелёный CI сами по себе недостаточны.

### Проверяемые результаты
{checks}

### Зависимости приёмки
{required or 'Безусловных зависимостей от других поставок нет.'}

Это зависимости **приёмки результата**, а не запрет параллельно искать данные, выводить метод и писать код.

### Условия по отдельным ветвям
{conditional or 'Дополнительных условных связей в текущем составе нет.'}

Снять применимый физический вход можно только проверяемым обоснованием для указанной ветви. Причина «быстрее» не является доказательством неприменимости.

### Что разблокирует
{onward}

### Ближайшее действие
{task['next_action']}

### Ответственность
{responsibilities}

### Разрешённый объём действий
Изменение кода и тестов

### Бюджет и ограничения
Поиск источников, аналитическая разработка, код и адресные проверки в согласованной задаче. Стоимость полного физического состава пока не установлена; измеренный прогноз оформляется задачей RESOURCES. Не назначать сроки «дни/недели» без измерений. Текущая Issue не является командой запуска полного опыта.

### Доказательства закрытия
Все критерии выше должны иметь артефакты с точным source SHA и SHA-256 входов, сохранённые результаты производителя и независимого повтора, описание метода и среды. Текущего completion record **нет**; задача открыта. Формат и защита от пустого закрытия: [порядок приёмки]({REPO_URL}/blob/main/infra/r135/README.md#приёмка-поставки). Научные статусы остаются в существующих R/U/D-реестрах.

### Уже имеющиеся источники
{sources}

Полная карта работы: [R135 Development Pipeline]({REPO_URL}/blob/main/infra/r135/README.md). Аудит основан на #159 `{plan['source_commits']['implementation']}` и #160 `{plan['source_commits']['design']}`; это исходная точка данной задачи, а не будущий SHA её результата.
"""


def tracker_body(plan):
    tasks = {t['key']: t for t in plan['tasks']}
    groups = []
    for block in dict.fromkeys(t['block'] for t in plan['tasks']):
        group = [t for t in plan['tasks'] if t['block'] == block]
        groups.append('#### ' + block + '\n\n' + '\n'.join(
            f"- [ ] {ref(t)} — {t['title'].removeprefix('R135 · ')}" for t in group))
    lines = '\n\n'.join(groups)
    focus = '\n'.join(f"- **{ref(tasks[k])}**: {tasks[k]['next_action']}" for k in plan['current_focus'])
    return f"""### Тип работы
Аналитический вывод или аудит доказательства

### Рабочий блок R135
F · Исполнение и приёмка

### Главный вопрос
Довести R135 от заданной физической реализации X до проверяемого результата по применимым наблюдениям либо воспроизводимого опровержения необходимого условия. XA (граф как носитель), самостоятельный XB (SU(3)) и граф как маркер XB получают **три отдельных вывода**.

### Генеалогия
R130–R135; C037; U006; BH1. Действующая реализация #159, дополнения проекта и доноров #160. Проект управления работой продолжает этот трекер, не создаёт второй научный реестр.

### Исходный commit
{plan['source_commits']['implementation']}

### Точка входа
[**R135 — рабочее представление существующей доски**](https://github.com/users/IgorSabirov/projects/2?query=label%3Ar135%3Adevelopment) · [**Порядок работы и карта зависимостей**]({REPO_URL}/blob/main/infra/r135/README.md) · [**Сопоставление с актуальным кодом**]({REPO_URL}/blob/main/infra/r135/AUDIT.md)

### Последняя подтверждённая программная база
#159 на `{plan['source_commits']['implementation']}`; #160 на `{plan['source_commits']['design']}`. В c3bc771 уже есть paired P7→P8→BBN→CLASS grid, уточнение историй, ядерный ансамбль и P10-replay. Это основание для продолжения, не завершённый физический опыт. Точный актуальный SHA PR смотрим в GitHub перед изменением кода.

На исходном аудите P0: **48 диагностических / 4 литературные / 0 независимо калиброванных точек X**. Физический прогон не запускался. Научный статус хранится в [карточке R135]({REPO_URL}/blob/main/analysis/NOW_RESULTS_SYNTHESIS_20261106/R135.md).

### Ближайшее действие
Начать с {ref(tasks['MODEL'])}: привести существующий P0 к трём проверяемым паспортам и точной применимости входов. Параллельно подготовлены {ref(tasks['EOS'])} (термодинамика) и {ref(tasks['NUCLEAR'])} (лабораторные ошибки). Ready означает доступную работу, а не запущенный расчёт.

### Первый рабочий набор
{focus}

### Поставки и их результаты
{lines}

### Как читать зависимости
Нативные **Blocked by** — безусловные зависимости приёмки конкретной поставки. Условные связи отдельно записаны в каждой Issue и карте: они проверяются для своей ветви. Можно параллельно разрабатывать метод, извлекать донорские данные и проверять интерфейс. XB не ждёт доказательства графового моста; статический маркер не получает автоматически физических часов. Существенный неизвестный вход нельзя убрать ради скорости или заменить произвольным prior.

### Критерий завершения
Каждая заявленная ветвь доведена до применимых наблюдений либо для неё воспроизводимо опровергнуто необходимое условие; P10 проверил первичные данные, полноту и область выводов; владелец принял научное решение в существующих реестрах. Пока обязательный вход открыт, весь R135 остаётся частичным.

### Доказательства закрытия
Закрытие данного трекера защищено completion record задачи {ref(tasks['ACCEPT'])}. Отметки checklist, текст отчёта, merge PR и зелёный CI недостаточны. Артефакты, точные SHA, отдельный replay и запись решения проверяются по [протоколу]({REPO_URL}/blob/main/infra/r135/README.md#приёмка-поставки). Автоматическая проверка целостности не является научным судьёй.

### Ответственность
Подготовка источников, методов, кода и доказательств — работа исполнителя соответствующей сессии, без перекладывания неизвестных формул на владельца. Независимый проверяющий/расчёт фиксируется до приёмки. Научное решение — IgorSabirov. GitHub-исполнители подзадач пока отдельно не назначены; это явно видно в Assignees.

### Разрешённый объём действий
Изменение кода и тестов

### Бюджет и ограничения
Управление разработкой и проверяемыми поставками. Полный ресурсный прогноз — {ref(tasks['RESOURCES'])}, по действительной среде и принятому физическому составу. Стоимость неизвестного не равна нулю. Закрытая необходимым отрицательным результатом ветвь не требует бесполезных downstream-расчётов.

### История трекера
[Исходное описание проектирования сохранено]({REPO_URL}/blob/main/infra/r135/review/tracker155_before.md). Прежние комментарии и PR остаются на месте. Эта редакция меняет операционную карту, не научные статусы.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((ROOT / MAP_PATH).read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    payloads = [{'key':t['key'],'issue_number':t['issue_number'],'title':t['title'],
                 'body':issue_body(t,plan)} for t in plan['tasks']]
    (args.out/'issues.json').write_text(json.dumps(payloads,ensure_ascii=False,indent=2)+'\n')
    (args.out/'tracker155.md').write_text(tracker_body(plan))
    print(json.dumps({'rendered_tasks':len(payloads),'out':str(args.out)}))


if __name__ == '__main__':
    main()
