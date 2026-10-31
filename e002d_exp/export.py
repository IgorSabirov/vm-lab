"""One compressed, self-describing case artifact; medium-v1 size limits stay fixed."""
import hashlib,json,gzip
from pathlib import Path
import numpy as np
from e002c_exp.export import extrema,evidence,array_spec,digest
from e002_exp.model import save_json
from .plan import CONTRACT

def export_case(report,r,mode):
    (report/"cases").mkdir(exist_ok=True)
    a,b=r["series"],r["diagnostics"];end=r["summary"]["horizon"]
    t=b[:,0]
    chosen=np.ones(len(t),bool) if mode!="production" else (((t>=190)&(t<=200))|((t>=end-10)&(t<=end)))
    times=t[chosen];indices=[int(np.argmin(abs(a[:,0]-x))) for x in times]
    keep_a=(a[:,0]<=10+1e-8)|np.isclose(a[:,0]/4,np.round(a[:,0]/4),atol=1e-9)
    keep_b=(b[:,0]<=20+1e-8)|np.isclose(b[:,0]/4,np.round(b[:,0]/4),atol=1e-9)
    ev={"e_"+k:v for k,v in evidence(r).items()}
    np.savez_compressed(report/"cases"/(r["summary"]["case"]["id"]+".npz"),
        series=a[keep_a],diagnostics=b[keep_b],window_time=times,
        window_blocks=r["certs"]["blocks"][chosen],window_scalar=a[indices],window_diagnostics=b[chosen],**ev)
    hidx=1+r["names"].index("h")
    return dict(scalar=extrema(a),diagnostic=extrema(b),scalar_records=len(a),diagnostic_records=len(b),
                h_t_positive=extrema(a[a[:,0]>0][:,[0,hidx]])[0],h_start=float(a[0,hidx]))

def write_manifest(report,full):
    records=[];original=[]
    for root,out in ((report,records),(full,original)):
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.name=="data_manifest.json":continue
            row=dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
            if root==report and p.suffix==".npz":row["arrays"]=array_spec(p)
            out.append(row)
    save_json(report/"data_manifest.json",dict(exported=records,full=original,
        full_bytes=sum(x["bytes"] for x in original),selection=CONTRACT["report"],
        limitations=["Full-state positivity and node-edge negativity cannot be recovered from reduced node blocks.",
          "Full-target Frobenius norms use the VM full state; reduced complex coherences are independently reconstructible.",
          "Full-grid extrema are computed before sampling; omitted samples stay on VM.",
          "Short calibration windows are not stationary scientific data."]))
    files=[p for p in report.rglob("*") if p.is_file()];cfg=CONTRACT["report"]
    total=sum(p.stat().st_size for p in files)
    if len(files)>cfg["maximum_files"] or total>cfg["maximum_bytes"] or any(p.stat().st_size>cfg["maximum_file_bytes"] for p in files):
        raise ValueError(f"Report budget exceeded: {len(files)} files, {total} bytes")
    return dict(bytes=total,files=len(files))

def compact(metrics,checks):
    rt=checks["runtime_gate"];analysis=metrics["analysis"]
    text=[f"Время: прогноз {rt['expected_seconds']:.3f} с; диапазон {rt['lower_seconds']:.3f}–{rt['upper_seconds']:.3f}; внутренний факт {rt['actual_seconds']:.3f}; статус {rt['status']}.",
      "Полное время процесса, включая завершение отчёта, проверяется по run.json; очередь и публикация отдельно.",
      "",f"# E002d v003 | {metrics['identity']['run_id']} | {metrics['mode']}",
      f"Исходный commit: {metrics['identity']['source_commit']}. Ядро SHA256: {metrics['environment']['kernel_sha256']}.",
      "A: изменение зазора QS/RR воздействиями N1/N2. B: центральный контраст m6,N2. C: изменение контраста воздействиями m6.",
      "Модель: 3 кубита×3 qutrit,216 состояний; начальная смесь |100;RRR>/|010;RRR>. J=1,g_QS=.5,eta=.25,delta=.1,gamma_bg=.01,gamma_r=.05,source=sink=.5,phi_e=.05. RR с прежними фиксированными скоростями сохраняет когерентный hop.",
      "Phi задаётся theta02=-Phi; epsilon*n1; phi_n=.05/.25. T/C=sqrt(gamma)(Pa∓Pb)Qm; композиции независимы.",
      "A: S2a=m2(5,6),S2b=m4(3,6),S1a=m2(1,2),S1b=m4(1,4). S2/S1 — пары этих мишеней. M2=m6(5,6)+(3,6),M1=m6(1,2)+(1,4).",
      "A: Phi=epsilon=0,noise=.05,одиночные gamma=.1,композиции .05/.1/.2. B: Phi/pi=.5,epsilon=0,±.0625,±.125,±.25,±.5,noise=.05/.25; Phi=0 контроль0,±.125. C: Phi/pi=.5,epsilon=0,±.125,noise=.05,gamma=.1.",
      "Fine/coarse=.005/.01; coarse у A только gamma=.1,у B только epsilon=0,±.125; C весь paired. Общий горизонт200 или400; mean=Simpson по6точкамчерез2.",
      f"Объём план/факт: {metrics['work']}. Численные/технические замечания: {checks['failures']}.",
      "trace/hermiticity<=1e-10,eigen>=-1e-8. Стационарность RHS<=1e-7,drift<=1e-6,rangeF<=1e-8+1e-5|F|. dt<=1e-6+1e-4*scale. Неопределённость примитива=1e-8+10*(dt-разность+max оконных диапазонов); интервалы распространяются. Это не статистическая значимость.",
      "Условные значения требуют p-u>1e-6,u<=.1p. Структурная метка использует допуск1e-6+.01*scale и численный запас; не отменяет полный эффект.",
      "", "Все случаи: Q=QS,R=RR; f/c=.005/.01. Условие P=Phi/pi,e=epsilon,n=phi_n; базовая ветка b. ! означает непрошедшую стационарность или dt; s — без coarse. hmin/max получены по всем точкам t>0.",
      "|случай/условие|T|h окна|hmin@t / hmax@t|качество|",
      "|---|---:|---:|---|---|"]
    for s in metrics["cases"]:
        c=s["case"];hm=(s.get("reference") or {}).get("h");e=s["h_extrema"]
        case=f"{c['label']}:{'Q' if c['model']=='QS' else 'R'},{c['target']}{c['kind']},g{c['gamma']:g},P{c['phi_over_pi']:g},e{c['detuning']:g},n{c['dephasing']:g},{'f' if c['dt']==.005 else 'c'}"
        flag="!" if not s["stationarity"]["pass_gate"] or s["refinement_status"]=="failed" else "s" if s["refinement_status"]=="not_refined" else "ok"
        text.append(f"|{case}|{s['horizon']:g}|{hm:.7g}|" + f"{e[0]:.5g}@{e[1]:g}/{e[2]:.5g}@{e[3]:g}|{flag}|" if hm is not None else f"|{case}|{s['horizon']:g}|null|{e[0]:.5g}@{e[1]:g}/{e[2]:.5g}@{e[3]:g}|{flag}|")
    if metrics["mode"]!="production":
        text+=["","Короткая техническая калибровка/проверка: стационарность и научный эффект не оцениваются."]
    else:
        text+=["","E=(hQST-hQSC)-(hRRT-hRRC);S=E/G0. S<0 означает уменьшение зазора относительно C, не долю механизма. Q и r — дополнительные.",
               "|A:цель,g,T|E|S|статус|","|---|---:|---:|---|"]
        for r in analysis["A"]:
            if "E" not in r:text.append(f"|{r['target']},{r['gamma']:g},{r['horizon']:g}|—|—|{r['status']}|");continue
            sv=r["S"]["value"];text.append(f"|{r['target']},{r['gamma']:g},{r['horizon']:g}|{r['E']['value']:.7g}|{sv if sv is not None else 'null'}|{r['status']}|")
        text+=["","D=j(0)-(j(-delta)+j(delta))/2,j=h_m6N2/p_m6N2. D<0 не доказывает минимум; отдельный статус проверяет обоих соседей.",
               "|B:M,P,n,delta,T|D|статус|ниже обоих соседей|","|---|---:|---|---|"]
        for r in analysis["B"]:
            dv=r.get("D",{}).get("value")
            text.append(f"|{r['model']},{r['phi_over_pi']:g},{r['dephasing']:g},{r['delta']:g},{r['horizon']:g}|{dv if dv is not None else 'null'}|{r['status']}|{r.get('minimum',{}).get('status')=='CENTER_BELOW_BOTH_SAMPLED_NEIGHBORS'}|")
        text+=["","|C:сравнение,T|delta D|статус|","|---|---:|---|"]
        for r in analysis["C"]:
            ident=r.get("model","")+r.get("target","")+r.get("comparison","")+r.get("fixed","")
            dv=r.get("delta_D",{}).get("value")
            text.append(f"|{ident},{r['horizon']:g}|{dv if dv is not None else 'null'}|{r['status']}|")
    text+=["","Полные условия и ID: case_registry.json. Все компоненты,знаменатели,структурные сдвиги,комплексные цели,арифметическое разложение и причины отказов: metrics.json и analysis.json.gz (lossless,хеш ссылки проверяется).",
      "Экстремумы всех величин до разрежения: extrema.json.gz. Один lossless NPZ на случай: cases/. Ряды .2 до10 затем4; диагностика2 до20 затем4; все окна/матрицы через2. Счётчики,размеры и SHA256: data_manifest.json. Цифры текста округлены,NPZ/JSON сохраняют точность.",
      "Полные матрицы и полные ряды остаются на ВМ. Проверяющий отчёт восстанавливает токи,веса,когерентности и основные контрасты из узловых блоков; полные positivity/node-edge NPT по ним не восстанавливаются.",
      "Нет автоматического статуса Фано; N2 не доказывает GME; нулевые свидетели не доказывают сепарабельность. A и B/C не доказывают общий механизм. Научная приёмка — пользователь."]
    result="\n".join(text)+"\n"
    if len(result.encode())>24*1024:raise ValueError(f"Compact report too large: {len(result.encode())}")
    return result

