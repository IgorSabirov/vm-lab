"""Scenario power, run before observation fits. Uses only the grid and its errors."""
import numpy as np
from scipy.stats import binomtest
from model import ROOT, BOUND, SEED, inputs, write_json, response, statistics

def run():
    rng=np.random.default_rng(SEED)
    output={}
    for label in ['S1','S2']:
        t,_,e=inputs(label)
        samples={}
        for name,r in [('edge',BOUND),('positive',.56),('negative',2.4)]:
            mean=response(t,[1.45,.73/1.45,.5,r,.18])
            ys=mean+rng.normal(size=(1000,len(t)))*e
            lr,d,*_=statistics(t,e,ys)
            samples[name]=(lr,d)
        cutoff=float(np.quantile(samples['edge'][0],.95,method='higher'))
        info={'n_sim_per_regime':1000,'boundary_chisq_increment_95':cutoff,'regimes':{}}
        for name,(lr,d) in samples.items():
            answers=np.where(lr>cutoff,np.sign(d),0)
            cells={}
            for key,code in [('positive',1),('negative',-1),('unresolved',0)]:
                k=int(np.sum(answers==code))
                ci=binomtest(k,len(d)).proportion_ci()
                cells[key]={'count':k,'fraction':k/len(d),'binomial95':[ci.low,ci.high]}
            info['regimes'][name]=cells
        output[label]=info
    write_json(ROOT/'results'/'POWER.json',output)

if __name__=='__main__': run()
