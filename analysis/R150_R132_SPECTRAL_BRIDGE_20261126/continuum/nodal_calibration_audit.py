#!/usr/bin/env python3
"""Independent finite-node and metrological controls; no BBN or repo solver."""
import numpy as np
from scipy.linalg import eigvalsh
from scipy.optimize import brentq

def main():
    rng = np.random.default_rng(7)
    maxerr = maxres = 0.
    for N in [16,32,64,128]:
        for _ in range(6):
            u,g,h = rng.uniform(-8,8),rng.uniform(-6,6),rng.uniform(-5,5)
            S = np.eye(N,k=1); S[-1,0] = -1.
            K = np.zeros((N+1,N+1)); K[0,0] = -u
            K[1:,1:] = N*N*(2*np.eye(N)-S-S.T)
            K[1,1] -= g*N; K[0,1] = K[1,0] = h*np.sqrt(N)
            ev = eigvalsh(K)
            for m in [1,3]:
                v = np.r_[0,np.sin(m*np.pi*np.arange(N)/N)]
                v /= np.linalg.norm(v)
                t = 4*N*N*np.sin(m*np.pi/(2*N))**2
                maxerr = max(maxerr,np.min(abs(ev-t)))
                maxres = max(maxres,np.linalg.norm(K@v-t*v))
    assert maxerr < 1e-8 and maxres < 1e-8
    print('nodal 24 contact sets, 48 levels; max eig deviation=',maxerr,'max analytic-vector residual=',maxres)
    for N in (32,128,256):
        a,b = 4*N*N*np.sin(np.pi/(2*N))**2,4*N*N*np.sin(3*np.pi/(2*N))**2
        D = b-a
        assert np.isclose(D,4*N*N*np.sin(2*np.pi/N)*np.sin(np.pi/N),rtol=1e-13)
        E1,E3 = .137+.02*a,.137+.02*b
        assert abs((E3-E1)/D-.02) < 1e-14
        assert abs((b*E1-a*E3)/D-.137) < 1e-14
        print(N,'bias',100*(D/(8*np.pi*np.pi)-1),'sigma(E*)',np.sqrt(2)*1e-4/D,'sigma(Eref)',np.hypot(a,b)*1e-4/D,'cov',-(a+b)*1e-8/D**2)
    k = brentq(lambda k:2*k*np.tanh(k/2)-2,1e-9,10)
    print('slope',2/np.sqrt((1+1/k**2)/2))
    hc,me,mn = 197.3269804,.51099895,939.56542
    print('neutron MeV',hc**2/(2*mn))
    en = hc**2/(2*me*1e18)*1e15
    print('electron ring neV',en,'gap neV',8*np.pi**2*en,'GHz',8*np.pi**2*en*1e-9/4.135667696e-15/1e9)
    print('continuum covariance',-10/(64*np.pi**2)*1e-8)

if __name__ == '__main__':
    main()
