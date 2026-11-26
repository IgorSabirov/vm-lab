from dataclasses import replace
from functools import lru_cache

import numpy as np
from runner import BASE, History, RTOL, native, net

K=100


def manifest():
    jobs={'identity':('identity',0,True),'original':('original',0,False),
          'fourier_raw':('fourier',0,False),'iaaft_raw':('iaaft',0,False)}
    for method in ('fourier','iaaft'):
        for seed in range(K):
            jobs[f'{method}_{seed:03}']=(method,seed,True)
    return jobs


@lru_cache(maxsize=1)
def inputs():
    baseline=native('f1r1_off')
    x=np.log(baseline['Tgamma_MeV'][::-1])
    y=baseline['deltaBD_MeV'][::-1]
    grid=np.linspace(np.log(.060),np.log(.080),257)
    base=np.interp(grid,x,y)
    h=History()
    density=np.interp(grid,x,baseline['D'][::-1])*np.exp(np.interp(grid,h.logT[::-1],h.logrho[::-1]))
    return x,y,grid,base,density


def spectral_error(x, ref):
    return np.linalg.norm(abs(np.fft.rfft(x-x.mean()))-ref)/np.linalg.norm(ref)


def case(method,seed,smooth):
    x,y,grid,local,density=inputs()
    rng=np.random.default_rng(150+seed)
    ft=np.fft.rfft(local)
    spectrum=abs(np.fft.rfft(local-local.mean()))
    if method=='fourier':
        phases=rng.uniform(0,2*np.pi,len(ft)-1)
        raw=np.fft.irfft(np.r_[ft[0],ft[1:]*np.exp(1j*phases)],n=len(local))
    elif method=='iaaft':
        ordered=np.sort(local)
        raw=rng.permutation(local)
        for _ in range(1000):
            z=np.fft.rfft(raw)
            new=np.fft.irfft(abs(ft)*np.exp(1j*np.angle(z)),n=len(local))
            ranks=np.argsort(np.argsort(new))
            ranked=ordered[ranks]
            if np.array_equal(ranked,raw): break
            raw=ranked
        np.testing.assert_array_equal(np.sort(raw),ordered)
    else:
        raw=local.copy()
    # Raised cosine taper. The continuous window and its first derivative vanish at each endpoint.
    s=np.linspace(0,1,len(grid))
    u=np.minimum(1,np.minimum(s,1-s)/.1)
    w=.5*(1-np.cos(np.pi*u)) if smooth else np.ones_like(u)
    used=local+w*(raw-local)
    profile=np.c_[np.exp(np.r_[x[x<grid[0]],grid,x[x>grid[-1]]]),np.r_[y[x<grid[0]],used,y[x>grid[-1]]]]
    if method=='original':profile=np.c_[np.exp(x),y]
    ans=net(History(),replace(BASE,rtol=RTOL),profile=profile)
    ans.update(seed=seed,method=method,smooth=smooth,
               corr_nD=float(np.corrcoef(used,density)[0,1]),raw_spectrum_error=spectral_error(raw,spectrum),
               joined_spectrum_error=spectral_error(used,spectrum),
               raw_sorted_error_MeV=max(abs(np.sort(raw)-np.sort(local))),
               joined_sorted_error_MeV=max(abs(np.sort(used)-np.sort(local))),
               sign_crossings=int(np.count_nonzero(np.signbit(used)!=np.signbit(local))))
    return ans
