"""Independent CSV arithmetic; does not call experiment metric/report functions."""
import csv,io,json
import numpy as np
from scipy.integrate import simpson

def verify(artifacts):
    m=json.loads(artifacts['files/metrics.json']);man=json.loads(artifacts['files/data_manifest.json']);cfg=m['protocol']
    assert m['source_commit']==man['source_commit'] and m['run_id']==man['run_id']
    assert set(m['cases'])=={c['id'] for c in cfg['cases']}
    assert len(man['full_files'])==man['full_file_count']
    assert sum(f['bytes'] for f in man['full_files'])==man['full_bytes']
    def read(path):
        rows=list(csv.DictReader(io.StringIO(artifacts['files/'+path].decode())))
        return {k:np.array([float(r[k]) for r in rows]) for k in rows[0]}
    refs={};arrays={}
    for cid,r in m['cases'].items():
        p=read('pre/'+cid+'.csv');t=p['time'];refs[cid]={k:float(simpson(v,x=t)/(t[-1]-t[0])) for k,v in p.items() if k!='time'}
        for k,v in refs[cid].items():assert np.isclose(v,r['reference'][k],atol=1e-12,rtol=1e-12)
        a=read('series/'+cid+'.csv');arrays[cid]=a;t=a['time'];case=r['summary']['case']
        assert len(t)==round((case['horizon']-case['damage_time'])/cfg['observable_interval'])+1
        assert np.allclose(t,np.arange(len(t))*cfg['observable_interval']+case['damage_time'],atol=1e-10,rtol=0)
        q=r['recovery']['integrals']
        for k in ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','pump_flux','break_flux']:
            assert np.isclose(q[k],simpson(a[k],x=t),atol=1e-11,rtol=1e-11)
        assert np.isclose(q['stored'],a['n2'][0]-a['n2'][-1],atol=1e-12)
        residual=q['sink_flux']-q['I_hop_sink']-q['I_form_sink']-q['I_idle_sink']-q['stored']
        assert np.isclose(residual,q['residual'],atol=1e-12)
        assert np.isclose(q['inventory_change'],a['inventory'][-1]-a['inventory'][0],atol=1e-12)
        assert np.isclose(q['inventory_residual'],q['inventory_change']-q['pump_flux']+q['break_flux'],atol=1e-12)
        for k in a:
            if k=='time':continue
            st=r['recovery_statistics'][k]
            for label,value in [('min',min(a[k])),('max',max(a[k])),('mean',a[k].mean())]:assert np.isclose(st[label],value,atol=1e-12,rtol=1e-12)
    pp=refs['PP_none_fine']
    for cid,r in m['cases'].items():
        case=r['summary']['case'];base=case['model']+'_none_fine';ref=refs[base];a=arrays[cid];t=a['time'];rec=r['recovery']
        for obs,key,fraction in [('I_hop_sink','Lambda_hop',.05),('sink_flux','Lambda_total',.01)]:
            floor=max(1e-8,fraction*pp[obs]);value=None if ref[obs]<=floor else float(simpson(np.maximum(0,1-a[obs]/ref[obs]),x=t))
            assert (value is None and rec[key] is None) or (value is not None and rec[key] is not None and abs(value-rec[key])<1e-9)
        qf=rec['integrals']['sink_flux'];bq=m['cases'][base]['recovery']['integrals']['sink_flux'];floor=max(1e-8,.01*bq)
        assert np.isclose(floor,rec['QF_min'],atol=1e-12)
        if qf<=floor:assert rec['shares'] is None and rec['machine_share'] is None
        else:
            for k,v in rec['shares'].items():assert np.isclose(v,rec['integrals'][k]/qf,atol=1e-12)
            assert np.isclose(rec['machine_share'],(rec['integrals']['I_form_sink']+rec['integrals']['I_idle_sink'])/qf,atol=1e-12)
        bs=m['cases'][base]['recovery']['machine_share'];ms=rec['machine_share'];expected=None if bs is None or ms is None else ms<=bs+.20
        assert rec['guard_passed']==expected
    assert m['actual_steps']==sum(r['summary']['steps'] for r in m['cases'].values())==cfg['runtime_forecast']['main_steps']
    return {'passed':True,'cases':len(m['cases']),'steps':m['actual_steps']}

if __name__=='__main__':
    import sys
    from pathlib import Path
    root=Path(sys.argv[1])
    print(json.dumps(verify({'files/'+str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})))
