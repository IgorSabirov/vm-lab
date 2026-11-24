"""Continuous profile, parametric bootstrap and sensitivity checks on anonymous panels."""
import time
import numpy as np
from scipy.optimize import least_squares, brentq
from scipy.stats import chi2
from model import (ROOT, BOUND, LOW, HIGH, STARTS, SEED, disc, inputs, osc,
                   physical, response, statistics, write_json)

def solve(fun, starts, lo, hi):
    results=[]
    for start in starts:
        point=np.clip(start,lo,hi)
        fit=least_squares(fun,point,bounds=(lo,hi),ftol=2e-10,xtol=2e-10,gtol=2e-10,max_nfev=450)
        results.append((float(2*fit.cost),fit.x))
    return min(results,key=lambda item:item[0])

def s4(t,y,e,starts,lo=LOW,hi=HIGH):
    return solve(lambda p:(response(t,p)-y)/e,starts,lo,hi)

def at_boundary(t,y,e,starts):
    indices=[0,1,2,4]
    def full(p): return np.insert(p,3,BOUND)
    v,p=solve(lambda p:(response(t,full(p))-y)/e,starts[:,indices],LOW[indices],HIGH[indices])
    return v,full(p)

def profile(t,y,e,best,edge,cutoff,cost):
    # At fixed d the width is determined by w2. Map a unit interval
    # to all w2 satisfying both the ratio and damping bounds.
    maxfactor=1-LOW[3]**2/2; minfactor=1-HIGH[3]**2/2
    left=minfactor*(HIGH[0]*HIGH[1])**2
    right=maxfactor*(HIGH[0]*HIGH[1])**2
    cache={}
    seeds=np.vstack([best,edge,STARTS])
    def value(d):
        d=float(d)
        if d in cache: return cache[d]
        minw=np.sqrt(d/(maxfactor if d>=0 else minfactor))
        minw1=max(LOW[0], minw/HIGH[1])
        if minw1>=HIGH[0]-1e-13: return 1e12
        lo=[minw1,0,LOW[2],0]; hi=[HIGH[0],1,HIGH[2],1]
        def unpack(p):
            w1,u,g1,h=p
            a=max(minw,w1*LOW[1]); w2=a+(w1*HIGH[1]-a)*u
            return [w1,w2/w1,g1,np.sqrt(max(0,2*(1-d/w2**2))),h]
        initial=[]
        for w1,s,g1,_,h in seeds:
            w1=np.clip(w1,minw1+1e-10,HIGH[0])
            a=max(minw,w1*LOW[1]); b=w1*HIGH[1]
            initial.append([w1,(w1*s-a)/max(1e-14,b-a),g1,h])
        v,_=solve(lambda p:(response(t,unpack(p))-y)/e,initial,lo,hi)
        cache[d]=v-cost
        return cache[d]
    grid=np.unique(np.r_[left+1e-8,-np.geomspace(.015,abs(left)*.999,37),
                         np.linspace(-.5,1.1,51),np.geomspace(1.15,right*.999,13),
                         right-1e-8,0.,disc(best)])
    flags=[value(v)<=cutoff for v in grid]
    endpoints=[]
    if flags[0]: endpoints.append(grid[0])
    for a,b,aa,bb in zip(grid[:-1],grid[1:],flags[:-1],flags[1:]):
        if aa!=bb: endpoints.append(brentq(lambda x:value(x)-cutoff,a,b,xtol=2e-5))
    if flags[-1]: endpoints.append(grid[-1])
    intervals=np.array(endpoints).reshape(-1,2).tolist()
    return intervals,[[k,cache[k]] for k in sorted(cache)]

def covariances(t,e,p):
    # Jacobian by complex step. Coordinates are [w1,s,g1,r,f2];
    # physical output is [w1,w2,g1,g2,x1,x2].
    offsets=1j*1e-20*np.eye(5)
    jac=np.stack([response(t,p+off).imag/1e-20/e for off in offsets],axis=1)
    trans=np.stack([physical(p+off).imag/1e-20 for off in offsets],axis=1)
    cov=np.linalg.pinv(jac.T@jac, rcond=1e-13)
    return trans@cov@trans.T, float(np.linalg.cond(jac))

def controls(t,y,e,start,starts):
    def free(p): return p[5]*response(t,p[:5])
    init=np.column_stack([starts,np.ones(len(starts))]); lo=np.r_[LOW,.05];hi=np.r_[HIGH,5.]
    v,p=solve(lambda p:(free(p)-y)/e,init,lo,hi)
    i=[0,1,2,4,5]
    def put(q): return np.insert(q,3,BOUND)
    bv,_=solve(lambda q:(free(put(q))-y)/e,init[:,i],lo[i],hi[i])
    # S5 is a finite-band cross-check, with its own amplitude and no f-sum constraint.
    def diff(p):
        w,g,f,a,rate=p
        return f*osc(t,w,g)+a*rate*t/(t*t+rate*rate)
    sv,sp=solve(lambda p:(diff(p)-y)/e,
                [[1.25,.55,.65,.25,k] for k in [.08,.3,.8,2.]], [.05,.01,0.,0.,.005],[4.,5.,3.,12.,10.])
    wide_lo=[.25,.008,.008,.008,0.]
    wide_hi=[5.,.9999999,8.,80.,1.]
    wide,wp=s4(t,y,e,starts,wide_lo,wide_hi)
    order=np.argsort(t)
    return {'free_total':{'chi2':v,'d':disc(p[:5]),'total':p[5],'p':p,'edge_LR':bv-v,
                          'dof':len(t)-6,'weights':[p[5]*(1-p[4]),p[5]*p[4]]},
            'S4_plus_S5':{'chi2':sv,'dof':len(t)-5,'w1_G1_f1_xT_GT':sp,
                          'full_fsum':None,'window':'observed positive frequencies only'},
            'expanded_box':{'chi2':wide,'d':disc(wp),'p':wp,'lo':wide_lo,'hi':wide_hi},
            'observed_band_two_sided_trapezoid':2*np.trapezoid((t*y)[order],t[order])}

def analyse(name,rng):
    t,y,e=inputs(name)
    init=np.vstack([STARTS, rng.uniform(LOW,HIGH,size=(28,5))])
    cost,p=s4(t,y,e,init)
    edgecost,ep=at_boundary(t,y,e,init)
    init=np.vstack([p,ep,init])
    starts=np.vstack([p,ep,STARTS])
    ys=response(t,ep)+rng.normal(size=(999,len(t)))*e
    lr0,_,_,_=statistics(t,e,ys,starts)
    lr=edgecost-cost
    cutoff=np.quantile(lr0,.95,method='higher')
    pval=(1+int(np.sum(lr0>=lr))) / 1000
    intervals,curve=profile(t,y,e,p,ep,cutoff,cost)
    # Statistical parameter uncertainty from the fitted signal itself.
    draws=response(t,p)+rng.normal(size=(999,len(t)))*e
    _,_,samples,_=statistics(t,e,draws,starts)
    physical_samples=np.stack([physical(a) for a in samples[:,1:]])
    cov,condition=covariances(t,e,p)
    loo=[]
    for i in range(len(t)):
        keep=np.arange(len(t))!=i
        tc,yc,ec=t[keep],y[keep],e[keep]
        lc,lp=s4(tc,yc,ec,starts)
        bc,_=at_boundary(tc,yc,ec,starts)
        loo.append({'row_zero_based':i,'removed_w':t[i],'d':disc(lp),'LR':bc-lc,
                    'passes_full_grid_cutoff':bool(bc-lc>cutoff)})
    rc,dc,_,_=statistics(t,e,y,STARTS)
    mc,md,_,_=statistics(t,e,y,starts)
    controls_result=controls(t,y,e,p,init)
    stable_profile=(all(a>0 for a,b in intervals) or all(b<0 for a,b in intervals)) and bool(intervals)
    sign='positive' if disc(p)>0 else 'negative'
    result={'n':len(t),'dof':len(t)-5,'chi2':cost,'chi2_reference_p':chi2.sf(cost,len(t)-5),
       'p_internal':p,'physical_order':['w1','w2','Gamma1','Gamma2','x1','x2'],
       'physical':physical(p),'physical_boot_percentiles_2_5_97_5':np.quantile(physical_samples,[.025,.975],axis=0),
       'physical_boot_cov':np.cov(physical_samples.T),'physical_local_cov':cov,'jacobian_cond':condition,
       'f1':1-p[4],'f2component':p[4],'fsum_imposed':1,'d':disc(p),'peak_over_wB':np.sqrt(max(0,disc(p))),
       'edge_chi2':edgecost,'edge_params':ep,'LR':lr,'p_boot':pval,'bootstrap_N':999,
       'critical95':cutoff,'profile95':intervals,'verdict':sign if pval<=.05 and stable_profile else 'unresolved',
       'bootstrap_above_observed':int(np.sum(lr0>=lr)),
       'loo':loo,'loo_cutoff':'full-grid boundary calibration; diagnostic only',
       'controls':controls_result,'multistart_LR':{'bank':rc,'seeded_bank':mc,'independent_scipy':lr},
       'rows_w_A_sigma_fit_weighted_residual':np.column_stack((t,y,e,response(t,p),(y-response(t,p))/e))}
    return result,curve

def main():
    if not (ROOT/'results'/'POWER.json').is_file(): raise RuntimeError('run power.py first')
    rng=np.random.default_rng(SEED+1)
    results={}; curves={}
    for name in ['S1','S2']:
        results[name],curves[name]=analyse(name,rng)
        print(name,results[name]['d'],results[name]['profile95'],results[name]['p_boot'],flush=True)
    write_json(ROOT/'results'/'BLIND.json',results)
    write_json(ROOT/'results'/'PROFILE.json',curves)

if __name__=='__main__': main()
