"""Report-only verification independent of the evolution and observable builders."""
import hashlib,json
from pathlib import Path
import numpy as np
from scipy.integrate import simpson

def verify(report):
    root=Path(report);manifest=json.loads((root/'data_manifest.json').read_text())
    for item in manifest['exported']:
        p=root/item['path'];data=p.read_bytes()
        if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('Export hash mismatch: '+item['path'])
    metrics=json.loads((root/'metrics.json').read_text());schema=json.loads((root/'schema.json').read_text())
    names=schema['series'];maxerr=0.;mineig=1.;windows=0
    for s in metrics['cases']:
        c=s['case'];cid=c['id']
        if c['phi_over_pi']!=0 or c['detuning']!=0:raise ValueError('Verifier only supports frozen zero-phase protocol')
        with np.load(root/'windows'/f'{cid}.npz',allow_pickle=False) as z:
            time=z['time'];blocks=z['blocks'];values=z['scalar']
        if blocks.shape!=(len(time),9,8,8) or not np.array_equal(time,values[:,0]):raise ValueError('Window shape/grid mismatch')
        if not np.isfinite(blocks).all() or np.max(abs(blocks-blocks.swapaxes(-1,-2).conj()))>1e-10:raise ValueError('Invalid reduced block')
        ev=np.linalg.eigvalsh(blocks);mineig=min(mineig,float(ev.min()))
        if ev.min() < -1e-8:raise ValueError('Nonpositive reduced block')
        err=float(np.max(abs(blocks[:,0]-blocks[:,1:].sum(axis=1))))
        if err>1e-10 or np.max(abs(np.trace(blocks[:,0],axis1=1,axis2=2)-1))>1e-10:raise ValueError('Block sum/trace failed')
        numbers=np.array([i.bit_count() for i in range(8)])
        hsum=np.zeros(len(time))
        for m in range(8):
            b=blocks[:,m+1]
            for n in range(4):
                weight=np.trace(b[:,numbers==n][:,:,numbers==n],axis1=1,axis2=2).real
                current=np.zeros(len(time))
                if n==1:
                    if m&2:current-=2*b[:,1,2].imag
                    if m&4:current-=2*b[:,1,4].imag
                elif n==2:
                    if m&2:current-=2*b[:,5,6].imag
                    if m&4:current-=2*b[:,3,6].imag
                for name,expected in [(f'p_m{m}_N{n}',weight),(f'h_m{m}_N{n}',current)]:
                    err=float(np.max(abs(values[:,names.index(name)]-expected)));maxerr=max(maxerr,err)
                    if err>1e-10:raise ValueError('Reconstruction failed: '+name)
                hsum+=current
            for key,mask,a,bb in [('A',2,5,6),('B',4,3,6),('N1_A',2,1,2),('N1_B',4,1,4)]:
                if mask!=m:continue
                for suffix,expected in [('re',b[:,a,bb].real),('im',b[:,a,bb].imag)]:
                    err=float(np.max(abs(values[:,names.index('C_'+key+'_'+suffix)]-expected)));maxerr=max(maxerr,err)
                    if err>1e-10:raise ValueError('Coherence reconstruction failed')
        err=float(np.max(abs(hsum-values[:,names.index('h')])));maxerr=max(maxerr,err)
        if err>1e-10:raise ValueError('Sector currents do not sum to h')
        if metrics['mode']=='production':
            end=s['horizon'];wanted=end-10+2*np.arange(6);take=np.isin(time,wanted)
            if not np.array_equal(time[take],wanted):raise ValueError('Incomplete final window')
            reference=simpson(values[take,1:],x=time[take],axis=0)/10
            expected=np.array([s['reference'][name] for name in names[1:]])
            err=float(np.max(abs(reference-expected)));maxerr=max(maxerr,err)
            if err>1e-10:raise ValueError('Reference mean mismatch')
        windows+=1
    if windows!=metrics['work']['actual']['trajectories']:raise ValueError('Missing case windows')
    return dict(status='PASS',case_windows=windows,reconstruction_max_error=maxerr,min_reduced_eigenvalue=mineig,
        limitations=['No independent full-state positivity or node-edge negativity verification from reduced blocks.'])
