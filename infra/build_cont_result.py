"""Build a small self-contained CONT review from a pinned GitHub download.

Input directory contains run.json and its exact downloaded artifacts. This script
does not read VM files or publish results. Original reports remain immutable.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from github_result_reader import read_github_result


def build(root, ref, source):
    rid = 'E001X_CONT_GH_v001_r001'
    if ref != 'fc7726bc30f21513200eb300fb76b6eba2c4e853' or source != 'f0c182527a9d1fd9208a56cbb1894d82510e4c79':
        raise ValueError('This retrospective renderer is specific to the verified CONT report')
    prefix = 'results/' + rid + '/'
    def fetch(repo, path, commit):
        assert repo == 'IgorSabirov/vm-lab' and commit == ref and path.startswith(prefix)
        return (root / path[len(prefix):]).read_bytes()
    accepted = read_github_result(fetch, repository='IgorSabirov/vm-lab',
                                 result_commit=ref, run_id=rid, source_commit=source)
    run = accepted['report']; artifacts = accepted['artifacts']
    m = json.loads(artifacts['files/metrics.json'])
    checks = json.loads(artifacts['files/checks.json'])
    manifest = json.loads(artifacts['files/data_manifest.json'])
    assert m['run_id'] == rid and m['source_commit'] == source
    assert set(m['cases']) == {'QQ_phi1', 'QQ_phi3', 'QP_phi1', 'QP_phi3'}
    assert run['full_data_inventory_errors'] == []
    for cid, case in m['cases'].items():
        names = sorted(Path(x['vm_path']).name for x in manifest['full_files'] if '/states/'+cid+'/' in x['vm_path'])
        assert names == ['rho_step%06d.npz' % step for step in range(10000,50001,100)]
        assert case['coverage']['source_records'] == 2001 and case['coverage']['observable_count'] == 164
        assert case['summary']['final_time'] == 500 and case['summary']['snapshots'] == 401
    lines = []
    def p(text=''):
        lines.append(text)
    def table(header, rows):
        p(); p('| ' + ' | '.join(header) + ' |'); p('|' + '|'.join(['---'] * len(header)) + '|')
        for row in rows:
            p('| ' + ' | '.join(str(x) for x in row) + ' |')
        p()
    def n(value):
        return format(value, '.17g')
    base = 'https://github.com/IgorSabirov/vm-lab/blob/' + ref + '/' + prefix
    wall = run['job']['finished'] - run['job']['started']
    preflight = m['preflight']['cases']
    cases = m['cases']
    p('# E001X_CONT — результат в одном файле')
    p('\nЭтот файл самодостаточен для обсуждения выводов и проверки приведённой арифметики. '
      'Он составлен после прогона из опубликованного отчёта GitHub; это не новая выгрузка с ВМ. '
      'Для повторной проверки всех исходных файлов нужны оригиналы по ссылкам в конце.')
    p('\nЗапуск: `' + rid + '`. Исходный коммит: `' + source + '`. Коммит исходного отчёта: `' + ref + '`.')
    p('\n## Вопрос, модель и ожидание')
    p('\nПроходят ли четыре ранее непройденные фазовые траектории критерий стационарности '
      'после продолжения с T=100 до T=500? Только непройденные следовало продолжить до T=1000. '
      'Прогноз до запуска: все пройдут к T=500, относительное отличие потока от сохранённой смеси T100 ≤ порядка 1e-5.')
    p('\nТри двухуровневых узла и три ребра с состояниями 0/R/L: размерность 216. '
      'Матрица плотности 216×216, комплексные числа float64+float64; точное уравнение Линдблада интегрируется численно RK4, dt=0.01. '
      'T — время модели в единицах J⁻¹, не секунды работы компьютера. '
      'QQ и QP имеют диагональный гейт образования Q. В растворении QQ использует Q, QP — проектор Π. '
      'Π=|ψ+⟩⟨ψ+|, ψ+=(|01⟩+|10⟩)/√2; Q=diag(Π). '
      'J=1, g=0.5, η=0.25, δ=0.1, κin=κout=0.5, φn=φe=0.05, γr=0.05, γbg=0.01. '
      'phi1/phi3 означают начальные фазы π/2 и 3π/2.')
    p('\nКритерий на последнем окне длиной 10: одновременно max(||Lρ||F/||ρ||F)≤1e-6, '
      'размах F/|Fкон|≤1e-4 и ||ρкон−ρнач||F/||ρкон||F≤1e-5. '
      'F=κout⟨n₂⟩ — поток через сток. Прогноз не заменяет численные проверки.')
    p('\nСохранённые ориентиры смеси T100: QQ='+n(cases['QQ_phi1']['summary']['case']['mixture_T100_flux'])+
      ', QP='+n(cases['QP_phi1']['summary']['case']['mixture_T100_flux'])+'. '
      'ΔF/F=(Fкон−Fсмеси)/Fсмеси. Эти смеси здесь не продолжались.')
    p('\n## Фактический ответ')
    p('\n' + ('Все четыре траектории прошли критерий при T=500. Продление до T=1000 не потребовалось.'
              if all(c['summary']['final_time'] == 500 and c['summary']['stationarity']['passed'] for c in cases.values())
              else 'Есть отличия от прогноза; смотреть таблицу и проваленные проверки ниже.'))
    rows = []
    for cid, c in cases.items():
        s=c['summary']; st=s['stationarity']; o=s['final_observables']
        rows.append([cid,n(s['final_time']),n(o['sink_flux']),n(s['mixture_T100_flux_relative_difference']),
                     n(st['max_relative_rhs']),n(st['relative_flux_range']),n(st['relative_rho_change']),st['passed']])
    table(['Случай','Tкон','Fкон','ΔF/F смеси T100','max RHS/ρ','Размах F','Изменение ρ','PASS'],rows)
    table(['Вариант','Fкон','hop в сток','form в сток','idle в сток','Число связей','B_L','M_L','E_L'],[
        [kind]+[n(cases[kind+'_phi1']['summary']['final_observables'][k]) for k in
                ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','sum_pL','B_L_total','M_L_total','E_L_total']]
        for kind in ['QQ','QP']])
    p('Во второй таблице показана phi1; ниже отдельно дана максимальная разница с phi3. '
      'hop — перенос по связям; form — перенос узлового возбуждения через правило образования; '
      'idle — через растворение. Это не ток конверсии R↔L. '
      'B_L=Σ⟨P_LΠ+⟩, M_L=Σ⟨P_LΠ−⟩, E_L=Σ⟨P_L(P00+P11)⟩; B_L+M_L+E_L=Σ⟨P_L⟩.')
    table(['Вариант','Макс. разница фаз по 164 конечным наблюдаемым','Разница F','Узловая когерентность, начало → конец'],[
        [kind,n(max(abs(cases[kind+'_phi1']['summary']['final_observables'][k]-cases[kind+'_phi3']['summary']['final_observables'][k])
                    for k in cases[kind+'_phi1']['summary']['final_observables'])),
         n(abs(cases[kind+'_phi1']['summary']['final_observables']['sink_flux']-cases[kind+'_phi3']['summary']['final_observables']['sink_flux'])),
         ' → '.join(n(float(x['node_coherence_fro'])) for x in
                    [list(csv.DictReader(io.StringIO(artifacts['files/diagnostics/'+kind+'_phi1.csv'].decode())))[i] for i in [0,-1]])]
        for kind in ['QQ','QP']])
    qa=cases['QQ_phi1']['summary']['final_observables'];pa=cases['QP_phi1']['summary']['final_observables']
    p('Когерентность здесь — норма Фробениуса недиагональной части редуцированной узловой матрицы. '
      'Поток QP относительно QQ: '+n(100*(pa['sink_flux']/qa['sink_flux']-1))+'%. '
      'Наличие ненулевой стационарной когерентности не доказывает сохранение начальной фазы или полезную защиту.')
    p('\n## Динамика и крайние значения')
    p('\nСтатистики учитывают все 2001 сохранённый отсчёт каждого случая, T=100…500 с интервалом 0.2. '
      'Экстремумы относятся к сохранённым отсчётам; поведение между ними не восстановлено.')
    table(['Случай','F при T100','F при T200','F при T500','min F @ T','max F @ T','Среднее F','σ F'],[
        [cid]+[n(next(x['observables']['sink_flux'] for x in c['summary']['selected_times'] if x['time']==t)) for t in [100,200,500]]+
        [n(c['statistics']['sink_flux']['min'])+' @ '+n(c['statistics']['sink_flux']['min_time']),
         n(c['statistics']['sink_flux']['max'])+' @ '+n(c['statistics']['sink_flux']['max_time']),
         n(c['statistics']['sink_flux']['mean']),n(c['statistics']['sink_flux']['stddev'])]
        for cid,c in cases.items()])
    p('\n## Численная корректность и сохранённые провалы')
    failed=[c for c in checks if not c['passed']]
    p('\nОпубликованные проверки: '+str(len(checks)-len(failed))+'/'+str(len(checks))+' PASS. '
      'Отчёт процесса: '+run['job']['state']+', exit_code='+str(run['job']['exit_code'])+'. '
      'export_errors='+json.dumps(run['export_errors'])+'; ошибки инвентаря='+json.dumps(run['full_data_inventory_errors'])+'.')
    if failed:p('\nПровалы без сокращения:\n```json\n'+json.dumps(failed,ensure_ascii=False,indent=2)+'\n```')
    state_checks=[x['actual'] for x in checks if x['name'].startswith('state_quality_')]
    table(['Проверка','Худшее фактическое значение','Допуск'],[
        ['Тождества операторов',n(max(x['actual_max_residual'] for x in checks if x['name'].startswith('operators_'))),'1e-10'],
        ['Ошибка следа ρ',n(max(x['trace_max'] for x in state_checks)),'1e-8'],
        ['Ошибка эрмитичности',n(max(x['hermiticity_max'] for x in state_checks)),'1e-8'],
        ['Минимальное собственное значение',n(min(x['minimum_eigenvalue'] for x in state_checks)),'≥ −1e-7'],
        ['Прямой/разреженный RHS, относительная ошибка',n(max(x['rhs_relative_error'] for x in preflight.values())),'1e-6'],
        ['RK4 против expm, относительная ошибка',n(max(x['expm_relative_error'] for x in preflight.values())),'2e-6'],
        ['Уменьшение dt вдвое, макс. разница наблюдаемых',n(max(x['dt_halving_max_observable_difference'] for x in preflight.values())),'2e-5']])
    p('Сравнение RK4/expm и dt/2 сделано на одном интервале времени от каждого входа T100, '
      'не повторяет весь длинный прогон. Положительность проверяется через 5 единиц времени; '
      'след и эрмитичность — через 1. Полная ρ не включена в этот файл.')
    p('\nИнтегральный баланс: ∫F = ∫hop + ∫form + ∫idle + n₂(T100)−n₂(T500). '
      'Баланс ресурса: ΔI = ∫pump−∫break. Интегралы имеют знак.')
    table(['Случай','∫F','∫hop','∫idle','Δзапаса n₂','Остаток транспорта','Остаток ресурса'],[
        [cid]+[n(c['summary']['integrals'][k]) for k in ['sink_flux','I_hop_sink','I_idle_sink','stored_sink','sink_balance_residual','inventory_balance_residual']]
        for cid,c in cases.items()])
    table(['Случай','∫pump','∫break','ΔI'],[
        [cid]+[n(c['summary']['integrals'][k]) for k in ['pump_flux','break_flux','inventory_change']]
        for cid,c in cases.items()])
    p('\n## Время, объём работы и данных')
    table(['Случай','Основных шагов','Матриц','Скалярных отсчётов','Время случая, с','Замер 100 шагов, с'],[
        [cid,c['summary']['last_snapshot']['step']-c['summary']['first_snapshot']['step'],c['summary']['snapshots'],
         c['coverage']['source_records'],n(c['summary']['elapsed_seconds']),n(preflight[cid]['seconds_per_100_steps'])]
        for cid,c in cases.items()])
    p('Всего: 160 000 основных шагов RK4, 1604 матрицы, 8004×164=1 312 656 скалярных значений. '
      'Сетка сохранений 100…500 через 1 без пропусков проверена по опубликованному манифесту. '
      'Это продолжение существующих четырёх состояний, не новый перебор параметров.')
    tz=timezone(timedelta(hours=3))
    clock=lambda t:datetime.fromtimestamp(t,tz).isoformat(timespec='milliseconds')
    p('\nНачало процесса: '+clock(run['job']['started'])+'; конец: '+clock(run['job']['finished'])+'. '
      'Длительность '+n(wall)+' с = 6 мин 34 с. От создания задания до старта: '+n(run['job']['started']-run['job']['created'])+' с. '
      'Это не измерение задержки от сообщения в чате. Время публикации сюда не входит.')
    p('\nПрежний устный прогноз 10–20 минут не выдержан: выполнение быстрее. '
      'По предзапусковым замерам 160 000 шагов требуют около '+n(sum(x['seconds_per_100_steps']*400 for x in preflight.values()))+' с. '
      'Остаток полного времени включает остальные расходы; их отдельного точного замера нет. '
      'Число шагов и сохранений совпало с планом. Разбор указывает на завышенную оценку времени. '
      'Формальный гейт времени принят после этого запуска и задним числом PASS ему не присваивается.')
    p('\nПолные файлы на ВМ, по опубликованному манифесту: '+str(manifest['full_bytes'])+' байт, '+str(manifest['full_file_count'])+' файлов. '
      'Исходный набор GitHub с run.json: '+str(sum(map(len,artifacts.values()))+len((root/'run.json').read_bytes()))+' байт, '+str(len(artifacts)+1)+' файлов. '
      'Одна плотная ρ: 216×216×16=746 496 байт (0.746 МБ, не 7.5 МБ). '
      'Все 1604 плотные матрицы: 1 197 379 584 байта; NPZ-снимки занимают 69 397 514 байт. '
      'Размер сжатого файла сам по себе не доказывает разреженность матрицы. '
      'Оценка до 2.7 ГБ относилась к максимальному горизонту T1000 без сжатия.')
    p('\n## Допустимый вывод и границы')
    p('\nДля этих четырёх траекторий выполнен конечновременной критерий стационарности. '
      'Различия двух начальных фаз исчезли в сохранённых наблюдаемых. '
      'QP сохраняет меньший поток, чем QQ, при ненулевом собственном idle-переносе. '
      'Ненулевая узловая когерентность остаётся. Это закрывает вопрос остаточного дрейфа CONT.')
    p('\nСравнение со смесью использует сохранённое значение при T100, а не вновь продолженную смесь. '
      'PP/PQ не продолжались, общий ранжир четырёх вариантов на едином новом горизонте не проверен. '
      'Здесь нет SQRT, J=0, повреждения или ремонта. Не доказаны единственность стационара, '
      'сохранение полной квантовой информации, самоподдержание, BIC или космологический тёмный сектор. '
      'Следующий согласованный вопрос — SQRT; этот документ ничего не запускает. Приёмка остаётся за пользователем.')
    p('\n## Происхождение и границы компактного файла')
    p('\nПеред построением файла проверены идентификатор запуска, исходный коммит, код завершения, '
      'полнота и SHA256/размеры всех '+str(len(artifacts))+' опубликованных файлов через github_result_reader.py. '
      'Весь исходный набор получен из одного закреплённого коммита GitHub. '
      'Этот файл не даёт независимого подтверждения без доверия к исходникам; для строгой проверки нужны оригиналы.')
    table(['Исходник','SHA256'],[['[run.json]('+base+'run.json)',hashlib.sha256((root/'run.json').read_bytes()).hexdigest()]]+
          [['['+name+']('+base+'files/'+name+')',run['files']['files/'+name]['sha256']] for name in ['metrics.json','checks.json','data_manifest.json']])
    p('Числовые таблицы сохраняют до 17 значащих цифр; арифметика балансов проверяема без скачивания других файлов. '
      'Этот файл содержит все четыре случая, все провалы проверок, конечные основные показатели, '
      'балансы и экстремумы F по всем 8004 отсчётам. Из 164 наблюдаемых выбраны показатели, '
      'нужные для вопроса CONT; полные ряды, экстремумы остальных величин, порядок событий и '
      'корреляции во времени требуют подробностей. Ничего не утверждается о несохранённых отсчётах между шагами 0.2. '
      'Инвентарь 1604 матриц не дублируется; он остаётся в исходном манифесте. '
      'Для обсуждения этого итога достаточно передать данный файл целиком; доступ получателя к приватному GitHub не требуется.')
    return '\n'.join(lines)+'\n'


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--github-cache',type=Path,required=True)
    ap.add_argument('--report-commit',required=True)
    ap.add_argument('--source-commit',required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    result=build(args.github_cache,args.report_commit,args.source_commit)
    size=len(result.encode('utf-8'))
    if size>24*1024:raise RuntimeError('Compact report exceeds 24 KiB; no silent truncation')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(result,encoding='utf-8')
    print(json.dumps({'bytes':size,'sha256':hashlib.sha256(result.encode()).hexdigest(),'output':str(args.output)}))
