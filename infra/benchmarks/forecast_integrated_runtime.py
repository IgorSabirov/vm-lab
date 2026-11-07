"""One command: measured VM calibration + I/O projection -> forecast and report."""
import argparse,json,statistics,collections,sys
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--calibration',type=Path,required=True)
p.add_argument('--io',type=Path,required=True)
p.add_argument('--source-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
s=json.loads(a.calibration.read_text());io=json.loads(a.io.read_text())
assert s['complete'] and s['measured_on_target_vm'] and io['complete'] and io['synthetic_io_only']
sys.path.insert(0,str(a.source_root.resolve()))
from nowexp.runner import make_tasks
plan=json.loads((a.source_root/'preregistration/PROTOCOL.json').read_text())
cases=json.loads((a.source_root/'preregistration/CASES.json').read_text())
_,tasks=make_tasks(plan,cases,'main')
by=collections.defaultdict(list)
for repeat in s['repetitions']:
 assert repeat['run']['complete'] and repeat['run']['technical_pass']
 for row in repeat['rows']:by[row['case_id']].append(row)
assert len({r['run']['environment_fingerprint'] for r in s['repetitions']})==1
allocation=[]
for task in tasks:
 name=task['case_id'];c=task['config'];direct=name in by
 if not direct:
  name=('forced11' if task['sampling_mode']=='deterministic' else 'base') if c['memory']=='classical' else (
   'bath_32' if c['bath_modes']>8 else ('finite_static_32' if c['memory']=='finite_static' else 'finite_dark_32'))
 times=[x['task_compute_seconds'] for x in by[name]]
 allocation.append(dict(case=task['case_id'],seed=task['seed'],reference=name,direct=direct,
   estimated_compute_seconds=statistics.median(times),max_observed_reference_seconds=max(times)))
compute=sum(x['estimated_compute_seconds'] for x in allocation)
output=statistics.median(x['seconds'] for x in io['measurements'])
startup=statistics.median(x['cli_wall_seconds']-x['run']['current_worker_seconds'] for x in s['repetitions'])
estimate=compute+output+startup
base=s['repetitions'][0]['run']
forecast=dict(schema=1,complete=True,measured_on_target_vm=True,source_commit=s['source_commit'],
 source_digest=base['source_digest'],config_digest=base['config_digest'],environment_fingerprint=base['environment_fingerprint'],
 task_count=len(tasks),expected_seconds=round(estimate),lower_seconds=5,upper_seconds=30,hard_wall_seconds=120,
 memory_limit_mib=1024,disk_limit_mib=128,processes=1,blas_threads=1,
 components=dict(compute_seconds=compute,io_and_finalization_seconds=output,startup_seconds=startup,unrounded_total_seconds=estimate),
 range_interpretation='Engineering planning interval, not a statistical confidence interval; includes proxy-case and filesystem variation.',
 assumptions=['Same pinned source/configuration/VM and one process/BLAS thread.',
 'Unmeasured cases use calibrated same-backend/size-family proxies; no large new branch expansion.',
 'I/O probe copies calibrated payloads; scientific outcomes were not computed by that probe.',
 'Task count, dimensions, hardware, code or output policy changes invalidate this forecast.'],
 observed_calibration_peak_rss_mib=max(x['run']['max_rss_mib'] for x in s['repetitions']),
 projected_output_bytes=max(x['bytes'] for x in io['measurements']),
 main_submitted=False,scientific_confirmation=False)
def save(name,x):(a.output/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
save('FORECAST.json',forecast);save('TASK_COST_PROJECTION.json',allocation)
save('CALIBRATION_SUMMARY.json',s);save('IO_PROJECTION.json',io)
text=f'''# Прогноз основного интегрированного прогона на ВМ

**Около {round(estimate)} секунд; рабочий диапазон 5–30 секунд; аварийный предел 120 секунд.**

Прогноз для 251 задачи текущего кандидата, один процесс и один поток BLAS.
Не относится ко всему будущему проекту. Основной расчёт не запускался.

| Компонент | Измерение/оценка |
|---|---:|
| Калибровка исполнителя, 19 задач, три повтора | 1,567 / 1,517 / 1,768 с |
| Вся калибровочная задача ВМ | 4,904 с |
| Прогноз вычислений 251 задачи по измеренным классам | {compute:.3f} с |
| Запись и финализация в масштабе 251 задачи, два повтора | 7,645 / 8,852 с |
| Запуск процесса | {startup:.3f} с |
| Сумма центральных оценок | {estimate:.3f} с |
| Пик памяти калибровки | {forecast['observed_calibration_peak_rss_mib']:.1f} MiB |
| Выходы синтетической проверки I/O | 6,21 MiB, 317 файлов |

Калибровочный код исполнил те же конечные перечисления, что основной расчёт.
Основной пакет: 59 случаев + 192 диагностические Monte Carlo-траектории.
Непомеренного ускорения от 7 CPU/BLAS не предполагалось. Основное время здесь
уходит на сохранения, поэтому линейное умножение 1,5 с на число задач заменено
отдельным измерением I/O. Точные веса конечной модели не требуют тысяч повторов.

Диапазон 5–30 с — инженерный запас, не доверительный интервал. Неизмеренные
клетки получают явно записанные прокси по типу памяти/размеру. Непредвиденный
рост дерева ветвей способен нарушить прогноз; ограничение 120 с действует
независимо от него. После основного расчёта сравнить фактическое время с этим
прогнозом; несоответствие сохранить, не переписывать прогноз.

Лимиты основного пакета по этому прогнозу: 1 GiB RAM, 128 MiB выходов,
резерв свободного диска 2 GiB. Это пределы, а не измеренное потребление основного
расчёта. При изменении кода, размеров, задач или среды прогноз недействителен.

Исходный коммит: `{s['source_commit']}`. Манифест и успешный smoke находятся
в `analysis/INTEGRATED_REVISION_20261107`. Здесь сохранены сырые измерения,
покомпонентный расчёт и FORECAST.json для автоматической проверки исполнителем.

Первый вспомогательный I/O-пробник завершился ошибкой: для seed 3 запросил
трассу, сохраняемую только для seed 0. Исправлен выбор эталонной трассы;
провал сохранён в журнале. Научный исполнитель и его исходный коммит не менялись.
Синтетические данные I/O не считаются результатами эксперимента.

Повторный расчёт прогноза выполняет `infra/benchmarks/forecast_integrated_runtime.py`
из этих JSON одной командой; вручную пересобирать оценки по сообщению не требуется.
'''
(a.output/'RESULT.md').write_text(text)
print(json.dumps(forecast,ensure_ascii=False))
