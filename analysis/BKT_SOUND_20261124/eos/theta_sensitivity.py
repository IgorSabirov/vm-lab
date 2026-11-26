"""Model-side sensitivity to marginal table errors (independence is assumed)."""
import json
import numpy as np
from inversion import HERE, EquationOfState, DomainError, evaluate
from run import measured_rows

def simulate(count=512):
    X,theta,se=np.loadtxt(HERE/'theta.csv',delimiter=',',skiprows=1).T
    rng=np.random.default_rng(1432202)
    rows=[r for r in measured_rows() if r['c2']>0]
    runs=[]; nonmonotone=0; invalid=np.zeros(len(rows),dtype=int)
    for _ in range(count):
        perturbed=theta+rng.normal(size=len(theta))*se
        if np.any(np.diff(X+perturbed)<=0):
            nonmonotone+=1
            continue
        eos=EquationOfState(theta=perturbed)
        values=[]
        for i,row in enumerate(rows):
            try: values.append(evaluate(row,eos=eos))
            except DomainError:
                invalid[i]+=1
                values.append(np.nan)
        runs.append(values)
    result=np.array(runs)
    return dict(seed=1432202,count=count,nonmonotone=nonmonotone,
                complete=int(np.isfinite(result).all(axis=1).sum()),invalid_by_row=invalid.tolist(),
                T_over_Tc=[r['T_over_Tc'] for r in rows],
                percentiles_2_5_50_97_5=np.nanpercentile(result,[2.5,50,97.5],axis=0).T.tolist(),
                assumption='Independent normal errors on theta knots; exact X; only monotone draws, valid EOS rows.')

if __name__=='__main__':
    (HERE/'theta_sensitivity.json').write_text(json.dumps(simulate(),indent=2,allow_nan=False)+'\n')
