"""Run all R141 continuations against immutable source data."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

import mpmath
import numpy as np
import scipy
import sympy

import cosmology
from nuclear import analyze, ideal_power, selected
from observations import operators, zeros

HERE=Path(__file__).resolve().parent
CORPUS=HERE.parents[1]/'analysis/R141_RIEMANN_CORPUS'
sys.path[:0]=[str(CORPUS/'bbn'),str(CORPUS/'spectral')]


def dump(path,value):
    def convert(v):
        if isinstance(v,np.generic):
            return v.item()
        raise TypeError(type(v))
    path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2,default=convert)+'\n')


def report(results,out,elapsed):
    lines=['# R141. Измеренные резонансы, конечное окно и выходы BBN','',
           'Прямой прогон GitHub Actions. Время вычислительных стадий %.1f с.'%elapsed,'',
           '## Проверка закона Портера–Томаса','',
           'Первые две трети уровней по энергии задают масштаб. Положительная разность средних логарифмических оценок на отложенных уровнях благоприятствует Портеру–Томасу относительно экспоненты. Интервал условен на обучении и относится только к отобранным уровням.','',
           '| EXFOR | Всего в секторе | Обучение / проверка | Разность оценок без отсечения | Условный 95% интервал | p для соответствия ПТ | ρ ширины со следующим интервалом / p |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for key,v in results['experiments'].items():
        t=v['tests']['0.0']
        lo,hi=t['conditional_interval']
        c=v['gap_left_width']
        lines.append(f"| {key} | {t['train']+t['test']} | {t['train']} / {t['test']} | {t['mean_log_PT_minus_exp']:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {v['pt_parametric_bootstrap_p']:.3f} | {c['rho']:+.3f} / {c['conditional_p']:.3f} |")
    power=results['ideal_width_power']
    lines+=['','При точных полных независимых выборках сбалансированная доля правильных решений для ПТ и экспоненты равна '+', '.join(f"{v['balanced_accuracy']:.1%} при N={n}" for n,v in power.items())+'. Отбор по обнаружению и ошибки присвоения в эксперименте могут изменить эти величины.',
            '','## Нули, оператор и запись','',
            'На нулях 61–657 средние отношения соседних зазоров измерены в непересекающихся окнах. AUC ниже относится к калибровке на COE/CUE. Квантили моделей и все измеренные окна приведены в zeros.json.','',
            '| Зазоров | Окон ζ | Медиана окна ζ | AUC по моделям |','|---:|---:|---:|---:|']
    for n,v in results['zeros']['windows'].items():
        lines.append(f"| {n} | {v['nonoverlap_windows']} | {v['observed_window_median']:.4f} | {v['paired_source_auc']:.3f} |")
    op=results['operators']
    lines+=['',f"На кольцах 6–48 проверено унитарное отображение свободного генератора сдвига и сжатого оператора Грама R132. Максимальная ошибка переноса Грама {max(max(v['compressed_gram_errors']) for v in op['finite_fourier_intertwiner'].values()):.2g}. Арифметическое возмущение полного оператора Конна остаётся открытым.",
            '',f"В R140 при вероятности физической записи p определитель трёх чтений равен `{op['mixture_determinant']}`. Полная запись оставляет два наблюдаемых направления. Сингулярные значения при промежуточных p сохранены в operators.json.",
            '','## Температурная история и выходы','',
            'Интегрированы восемь компонент сети при заданной тепловой истории от T₉=2 до конца архива. Общий множитель применён также к слабым и обратным скоростям. Для выборочного изменения d(p,γ)³He прямое и обратное направления менялись согласованно.','',
            '| Режим | D/H | Yₚ | Δ(D/H)/(D/H) | ΔYₚ/Yₚ |','|---|---:|---:|---:|---:|']
    b=results['bbn']
    for k,v in b['observables'].items():
        d=b['fractional_change'][k]
        lines.append(f'| {k} | {v[0]:.7g} | {v[1]:.7g} | {d[0]:+.3g} | {d[1]:+.3g} |')
    lines+=['',f"Изменение решения при ужесточении допуска, D/H и Yₚ: {b['tolerance_refinement_relative']}. Отклонение восстановленного фона от сохранённого конца траектории: {b['baseline_vs_archived_relative']}.",
            '', 'В bbn.json также приведена условная проверка с одинаковой дисперсией сил для двух ансамблей. Она предполагает независимые силы, долю линий 10% и шаг 10 кэВ. Наблюдения железа характеризуют чувствительность метода. Физическая резонансная компонента для лёгкой реакции и общий механизм с нулями ζ остаются открытыми.',
            '', 'Данные об отборе и допущения приведены в [протоколе](../../README.md).']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser()
    for key in ['exfor','zeros','history','primat','out']:
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    times={}
    def stage(name,fn):
        print('Running',name,flush=True)
        start=perf_counter()
        value=fn()
        dump(a.out/(name+'.json'),value)
        times[name]=perf_counter()-start
        return value
    def revision(folder):
        return subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()
    assert revision(a.exfor)=='2efecedd83bd22133350a3e1b15bf74839a1c0c7'
    assert sha256((a.primat/'primat/network_builder.py').read_bytes()).hexdigest()=='d326254e4132f310b48850564b1423522ca16568ec0fe17f20b75a86083ee17d'
    inputs=stage('selected',lambda:selected(a.exfor))
    assert [len(inputs[k]['rows']) for k in ('21803002','10172047')]==[24,8]
    analyzed=stage('experiments',lambda:{k:analyze(v['rows'],141000+i) for i,(k,v) in enumerate(inputs.items())})
    for v in analyzed.values():
        assert abs(v['injected_monotonic_control']['rho']-1)<1e-12
    power=stage('ideal_width_power',lambda:ideal_power(141024))
    assert power['256']['balanced_accuracy']>power['8']['balanced_accuracy']
    z=stage('zeros',lambda:zeros(a.zeros))
    op=stage('operators',lambda:operators(CORPUS))
    b=stage('bbn',lambda:cosmology.run(CORPUS,a.primat,a.history,a.out,analyzed['21803002']['cv2_train']))
    data=dict(experiments=analyzed,ideal_width_power=power,zeros=z,operators=op,bbn=b)
    elapsed=sum(times.values())
    report(data,a.out,elapsed)
    dump(a.out/'RECEIPT.json',dict(computation='PASS',source=revision(HERE),run_id=os.getenv('GITHUB_RUN_ID'),
        template='R141_INTEGRATED_20261122',seconds_by_stage=times,total_stage_seconds=elapsed,
        forecast_s=[10,180],forecast_delta_from_range_s=max(10-elapsed,elapsed-180,0),
        python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,
        sympy=sympy.__version__,mpmath=mpmath.__version__,exfor=revision(a.exfor),primat=revision(a.primat),
        baseline_archive='d503ee0f1f89c99c8560803dc46277d544ef15ba',zero_run='45038065048'))
    manifest=a.out/'MANIFEST.sha256'
    manifest.write_text(''.join(sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n'
                        for f in sorted(a.out.iterdir()) if f.is_file() and f!=manifest))
    print((a.out/'REPORT.md').read_text())


if __name__=='__main__':
    main()
