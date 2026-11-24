"""Selected s-wave 56Fe resonances. Statistical tests operate on separate experiments."""
from collections import Counter
from hashlib import sha256

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammainc
from scipy.stats import gamma, rankdata


def records(path, subentry, digest, nfields, nrows):
    raw = path.read_bytes()
    assert sha256(raw).hexdigest() == digest
    lines = raw.decode("ascii").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("SUBENT") and subentry in line)
    end = lines.index(next(line for line in lines[start:] if line.startswith("ENDSUBENT")), start)
    sub = lines[start:end]
    k = next(i for i, line in enumerate(sub) if line.startswith("DATA "))
    assert list(map(int, sub[k].split()[1:])) == [nfields, nrows]
    row_lines = (nfields+5)//6
    first = k+1+2*row_lines
    assert sub[first+row_lines*nrows].startswith("ENDDATA")
    for i in range(nrows):
        field = ''.join(x[:66].ljust(66) for x in sub[first+i*row_lines:first+(i+1)*row_lines])
        yield [float(v) if v.strip() else None for v in (field[j:j+11] for j in range(0,11*nfields,11))]


def selected(root):
    output = {}
    for key, path, digest, fields, count in [
        ('21803002','218/21803.x4','83f969f84a388900a197da0504d699f491a393a2acf8ba7e916a213222330b57',8,188),
        ('10172047','101/10172.x4','405c9572450e8336728f66e9ec5b5f98d6b973eb9549bb1c2efc1e3deeec53e4',7,9)]:
        rows, flow = [], Counter()
        for i, r in enumerate(records(root/'exforall'/path,key,digest,fields,count),1):
            energy = r[0]
            if key == '21803002':
                if r[7] is not None:
                    flow['assignment_flag'] += 1
                    continue
                if (r[5],r[6]) != (0,.5):
                    flow['other_sector'] += 1
                    continue
                width,err = r[3:5]  # Reich-Moore neutron width, eV.
            else:
                if energy <= 0:
                    flow['nonpositive_energy'] += 1
                    continue
                width,err = (1000*r[2],1000*r[3])  # raw keV -> eV; common L=0.
            assert energy > 0 and width > 0 and err > 0
            rows.append([i,energy,width,err,width/np.sqrt(1000*energy)])
        flow['retained'] = len(rows)
        assert sum(flow.values()) == count and np.all(np.diff(np.array(rows)[:,1])>0)
        output[key] = dict(input_sha256=digest,counts=dict(flow),columns=[
            'input_row','E_keV','neutron_width_eV','quoted_width_error_eV','reduced_width_eV'],rows=rows)
    return output


def log_density(x, a, scale, cut):
    return gamma.logpdf(x,a,scale=scale)-gamma.logsf(cut,a,scale=scale)


def fit_scale(x,a,cut):
    if cut == 0:
        return x.mean()/a
    center = np.log(x.mean()/a)
    fit = minimize_scalar(lambda z: -np.sum(log_density(x,a,np.exp(z),cut)),
                          bounds=(center-6,center+6),method='bounded')
    assert fit.success and abs(fit.x-center)<5.99
    return np.exp(fit.x)


def score(train,test,cut):
    train,test = train[train>=cut],test[test>=cut]
    scales = [fit_scale(train,a,cut) for a in (.5,1.)]
    diff = log_density(test,.5,scales[0],cut)-log_density(test,1.,scales[1],cut)
    return train.size,test.size,scales,diff


def ks_normalized(x):
    # PT, with mean estimated from the same sample, CDF of chi-square with 1 df.
    cdf = gammainc(.5, np.sort(x,axis=-1)/x.mean(axis=-1,keepdims=True)/2)
    i = np.arange(cdf.shape[-1])/cdf.shape[-1]
    return np.maximum((cdf-i).max(axis=-1),(i+1/len(i)-cdf).max(axis=-1))


def corr_test(gap,ranks,rng):
    # Compare next gap with mark of its left endpoint. Preserve local energy strata.
    a,b = rankdata(gap),rankdata(ranks)
    a,b = a-a.mean(),b-b.mean()
    norm = np.linalg.norm(a)*np.linalg.norm(b)
    value = float(a@b/norm)
    blocks = np.array_split(np.arange(len(a)),max(1,len(a)//5))
    permutations = np.tile(b,(3999,1))
    for idx in blocks:
        permutations[:,idx] = rng.permuted(permutations[:,idx],axis=1)
    null = permutations@a/norm
    p = (1+np.count_nonzero(abs(null)>=abs(value)-1e-14))/(1+len(null))
    return dict(rho=value,conditional_p=p,pairs=len(gap),block_sizes=list(map(len,blocks)))


def analyze(rows,seed):
    rng = np.random.default_rng(seed)
    _,e,w,err,x = np.array(rows).T
    n = len(e)
    split = 2*n//3
    tests = {}
    for q in (0.,.1,.25):
        cut = np.quantile(x[:split],q) if q else 0.
        ntrain,ntest,scales,diff = score(x[:split],x[split:],cut)
        # Circular block bootstrap on the held-out differences, conditional on training fit.
        length = min(2,ntest)
        starts = rng.integers(ntest,size=(3999,(ntest+length-1)//length))
        picks = ((starts[:,:,None]+np.arange(length))%ntest).reshape(len(starts),-1)[:,:ntest]
        tests[str(q)] = dict(cut_eV=cut,train=ntrain,test=ntest,scale_eV=scales,
                             mean_log_PT_minus_exp=diff.mean(),conditional_interval=np.quantile(
                                 diff[picks].mean(axis=1),[.025,.975]).tolist())
    ks = ks_normalized(x)
    simulated = ks_normalized(rng.chisquare(1,size=(9999,n)))
    # Scenario only: independent positive errors with the source's quoted relative SD.
    logsigma = np.sqrt(np.log1p((err/w)**2))
    samples = x*np.exp(rng.normal(size=(1500,n))*logsigma-.5*logsigma**2)
    train,test = samples[:,:split],samples[:,split:]
    gap = np.diff(e)
    uncertainty_score = (log_density(test,.5,2*train.mean(1)[:,None],0)-
                         log_density(test,1,train.mean(1)[:,None],0)).mean(1)
    return dict(split=split,energy_keV=[e[0],e[-1]],heldout_starts_keV=e[split],
                tests=tests,cv2_train=x[:split].var(ddof=1)/x[:split].mean()**2,
                pt_ks=ks,pt_parametric_bootstrap_p=(1+sum(simulated>=ks))/10000,
                gap_left_width=corr_test(gap,x[:-1],rng),
                injected_monotonic_control=corr_test(gap,gap,rng),
                error_scenario_uncut_score_interval=np.quantile(uncertainty_score,[.025,.975]).tolist())


def ideal_power(seed):
    rng = np.random.default_rng(seed)
    results = {}
    for n in (8,24,64,256):
        split = 2*n//3
        row = []
        for a in (.5,1.):
            x = rng.gamma(a,1/a,(10000,n))
            mean = x[:,:split].mean(1)[:,None]
            test = x[:,split:]
            choose_pt = (log_density(test,.5,2*mean,0)-log_density(test,1,mean,0)).mean(1)>0
            row.append(float(np.mean(choose_pt if a==.5 else ~choose_pt)))
        results[str(n)] = dict(correct_by_true_PT_exp=row,balanced_accuracy=np.mean(row),
                               mc_se=np.sqrt(sum(p*(1-p) for p in row)/40000))
    return results
