"""Population extrema at the actual initial (1,1,0)/sqrt(2); numerators are Gaussian integers."""
import math
import sympy as s
def gaussian_abs(x):
    return s.expand(x*s.conjugate(x))
def scan(k, stats, multiplicity, t):
    v=k[:,0]+k[:,1]
    char=[gaussian_abs(z) for z in v]
    total=sum(char)
    if not total:return
    stats['nonzero']+=multiplicity
    h0=gaussian_abs(sum(v));stats['p1_half']+=multiplicity*int(2*h0==3*total)
    # F v, omitting the common factor 1/sqrt(3).
    z=s.expand(sum(v[(j+1)%3]*s.conjugate(v[j]) for j in range(3)))
    center=total-s.re(z);delta=s.im(z)*s.sqrt(3)
    for label,pops in [('character',char),('holonomy',[h0,center-delta,center+delta])]:
        lo=min(pops,key=float);hi=max(pops,key=float)
        if lo==0:continue
        assert lo>0
        stats[label+'_positive']+=multiplicity
        middle=sum(pops)-hi-lo
        model_ratios=[float(middle/lo),float(hi/lo)]
        ratio=model_ratios[1]
        # External comparison comes after model construction; both coordinates are evaluated.
        data_ratios=[105.6583755/0.51099895069,1776.93/0.51099895069]
        if ratio>=data_ratios[1]:
            stats[label+'_at_least_PDG_span']=stats.get(label+'_at_least_PDG_span',0)+multiplicity
        mismatch=max(abs(math.log(a/b)) for a,b in zip(model_ratios,data_ratios))
        if mismatch < stats.get(label+'_best_log_error',math.inf)-1.e-12:
            stats[label+'_best_log_error']=mismatch
            stats[label+'_closest_ratios']=model_ratios
            stats[label+'_closest_ratios_exact']=list(map(str,[s.radsimp(middle/lo),s.radsimp(hi/lo)]))
        if ratio>stats[label+'_max_ratio']+1.e-10:
            stats[label+'_max_ratio']=ratio
            stats[label+'_max_ratio_exact']=str(s.radsimp(hi/lo))
            stats[label+'_extreme_normalized_triple']=[1.,*model_ratios]
            stats[label+'_extreme_endpoint_probability']=str(total/(2*4**t))
