"""Measure a local eta response without a likelihood or fitted physics verdict."""
import math
import common as c

def analyze(root):
    c.verify_freeze(root)
    plan=c.read(c.PKG/'PLAN.json');ids=[r['id'] for r in plan['runs']]
    reference=c.read(c.REFERENCE_ROOT/'runs/F0/RESULT.json')['result']
    data={rid:c.read(root/'runs'/rid/'RESULT.json') for rid in ids}
    audits={rid:c.read(root/'ETA_INPUTS'/f'{rid}.json') for rid in ids}
    channels=None
    for row in plan['runs']:
        rid=row['id'];x=data[rid];m=c.read(root/'runs'/rid/'MANIFEST.json')
        if x['status']!='ENGINEERING_PASS' or m['mode']!='S0' or m['clock']!={'f0':1.,'alpha_s_inv':0.}:raise ValueError('Unexpected physical mode')
        if len(m['network']['LT'])!=59 or len(m['network']['LT_channels'])!=428:raise ValueError('Incomplete network')
        if channels is None:channels=m['network']['LT_channels']
        if m['network']['LT_channels']!=channels:raise ValueError('Reaction inventory changed')
        if [e['era'] for e in x['eras']]!=['HT','MT','LT'] or not all(e['success'] for e in x['eras']):raise ValueError('Incomplete eras')
        if x['cache_before']!=x['cache_after']:raise ValueError('Cache mutation')
        if abs(audits[rid]['eta_resolved']/audits[rid]['eta_baseline']-row['eta_factor'])>1e-14:raise ValueError('Actual eta differs')
    lo,hi=ids;dlog=math.log(audits[hi]['eta_resolved']/audits[lo]['eta_resolved'])
    metrics={}
    for key in plan['observables']:
        yl,y0,yh=data[lo]['result'][key],reference[key],data[hi]['result'][key]
        if not all(math.isfinite(y) and y>0 for y in (yl,y0,yh)):raise ValueError('Invalid observable '+key)
        slope=math.log(yh/yl)/dlog
        left=math.log(yl/y0)/math.log(plan['runs'][0]['eta_factor'])
        right=math.log(yh/y0)/math.log(plan['runs'][1]['eta_factor'])
        metrics[key]={'low':yl,'baseline':y0,'high':yh,'dlnY_dlneta_secant':slope,
                      'left_secant':left,'right_secant':right,'secant_difference':right-left,
                      'absolute_span':abs(yh-yl)}
    c.write(root/'RESPONSE.json',{'status':'LOCAL_ETA_RESPONSE_COMPLETE','audits':audits,
        'observables':metrics,'scope':'Finite interval secants on fixed standard BBN; not a converged derivative, observational likelihood, or time-varying eta history.',
        'scientific_acceptance':False})
    lines=['# Sη: локальная чувствительность стандартного BBN','','Эталон F0 переиспользован; два новых прогона меняют только Omegabh2 через отображение eta.','','| Величина | η−1% | Эталон | η+1% | ΔlnY/Δlnη |','|---|---:|---:|---:|---:|']
    for k,v in metrics.items():lines.append(f"| {k} | {v['low']:.10g} | {v['baseline']:.10g} | {v['high']:.10g} | {v['dlnY_dlneta_secant']:.7g} |")
    lines+=['','Знак или размер отклика не используются как критерий успеха исполнения.','Это секущая на выбранном интервале; сходимость по ширине интервала и теоретические ошибки ядерных скоростей здесь не исследованы.','Не использован CMB/BBN posterior. Историческое различие eta_BBN и eta_CMB не моделируется.','']
    (root/'REPORT.md').write_text('\n'.join(lines))
    return {'status':'LOCAL_ETA_RESPONSE_COMPLETE'}
