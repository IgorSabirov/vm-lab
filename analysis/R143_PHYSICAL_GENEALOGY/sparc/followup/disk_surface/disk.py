"""Nonlocal thin-disk inversion and matched surface-density controls for R143."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.special import ellipkm1, ellipe
from numpy.polynomial.legendre import leggauss

HERE = Path(__file__).resolve().parent
SPARC = HERE.parent.parent
PC = 3.085677581491367e16
MSUN = 1.98847e30
GSI = 6.67430e-11
G = GSI * MSUN / (1000 * PC * 1e6)  # kpc (km/s)^2 per solar mass
ACC = 1e6 / (1000 * PC)


def mesh(r, subdivisions):
    return np.r_[np.geomspace(r[:-1], r[1:], subdivisions, endpoint=False, axis=1).ravel(), r[-1]]


def quadrature(edges, order):
    x, w = leggauss(order)
    u = (x + 1) / 2
    t = (1 - np.cos(np.pi * u)) / 2
    wt = w * np.pi * np.sin(np.pi * u) / 4
    widths = np.diff(edges)[:, None]
    return (edges[:-1,None] + widths * t).ravel(), (widths * wt).ravel()


def kepler_term(r, outer, v2):
    # Integral from the last measured radius to infinity for V^2 proportional to 1/r.
    m = (r / outer)**2
    comp = 1-m
    term = np.zeros_like(m)
    np.multiply(comp, ellipkm1(comp), out=term, where=comp>0)
    factor = (ellipe(m) - term)/m
    return -v2/outer * factor/(np.pi**2 * G * 1e6)


def invert(r, grid, functions, order=12):
    """Each column is d(V^2)/dr; kernel K uses scipy's parameter k^2."""
    q, weights = quadrature(np.r_[0., grid], order)
    cols=[]
    for value, deriv in functions:
        d=deriv(np.maximum(r[0],q))
        center=q<r[0]
        d[center]=2*value(r[0])*q[center]/r[0]**2
        cols.append(d*weights)
    cols=np.array(cols).T
    out=[]
    for R in np.array_split(grid,max(1,int(np.ceil(len(grid)/32)))):
        big=np.maximum(R[:,None],q)
        small=np.minimum(R[:,None],q)
        complement=(big-small)*(big+small)/big**2
        kernel=ellipkm1(complement)/big
        out.append(kernel@cols)
    return np.vstack(out)/(np.pi**2*G*1e6)


def sphere_projected(r, grid, value, deriv):
    # Abel projection of rho=(V^2+r*dV^2/dr)/(4 pi G r^2).
    # Split theta quadrature at every original radius including the flat continuation.
    x,w=leggauss(12)
    values=[]
    for R in grid:
        edges=np.r_[0.,np.arccos(R/r[r>R])]
        lo,hi=edges[:-1,None],edges[1:,None]
        theta=(lo+hi)/2+(hi-lo)*x/2
        radii=R/np.cos(theta)
        measured=np.sum((hi-lo)*w/2*(value(radii)+radii*deriv(radii))) if radii.size else 0.
        tail=(np.pi/2-edges[-1])*value(r[-1])
        values.append((measured+tail)/(2*np.pi*G*R*1e6))
    return np.array(values)


def crossing(r, surface, threshold):
    assert np.all(np.isfinite(surface))
    down=np.where((surface[:-1]>threshold)&(surface[1:]<=threshold))[0]
    up=np.where((surface[:-1]<=threshold)&(surface[1:]>threshold))[0]
    rt=np.nan
    if surface[0] <= threshold:
        status='inner_below_then_above' if len(up) else 'all_below'
    elif len(down):
        i=down[0]
        rt=r[i]+(r[i+1]-r[i])*(surface[i]-threshold)/(surface[i]-surface[i+1])
        status='resolved'
    else:
        status='all_above'
    return status,rt,len(down),len(up)


def validate():
    r=np.geomspace(.001,1000,220)
    use=(r>.12)&(r<8)
    a=1.
    # M*G=1 for the Kuzmin disk; asymptotic V^2=1 for the cored Mestel disk.
    vals=[(lambda x:x**2/(x**2+a*a)**1.5,
           lambda x:x*(2*a*a-x*x)/(x*x+a*a)**2.5),
          (lambda x:1-a/np.sqrt(x*x+a*a),lambda x:a*x/(x*x+a*a)**1.5)]
    sigma=invert(r,r,vals,order=20)
    expected_k=a/(2*np.pi*G*(r*r+a*a)**1.5*1e6)
    expected_m=1/(2*np.pi*G*np.sqrt(r*r+a*a)*1e6)
    recovered=sigma[:,0]+kepler_term(r,r[-1],vals[0][0](r[-1]))
    err_k=np.max(abs(recovered[use]/expected_k[use]-1))
    err_m=np.max(abs(sigma[use,1]/expected_m[use]-1))
    # Flat spherical law, Sigma=V^2/(4GR), exact at every measured radius.
    proj=sphere_projected(r,r,lambda x: np.ones_like(x),lambda x:np.zeros_like(x))
    err_s=np.max(abs(proj*4*G*r*1e6-1))
    assert max(err_k,err_m)<1e-3 and err_s<1e-10,(err_k,err_m,err_s)
    return dict(Kuzmin_max_relative=err_k,cored_Mestel_max_relative=err_m,
                flat_Abel_max_relative=err_s,analytic_Mestel_q_a0_over_G=2*np.pi)


def run(donor, data, subdivisions=8, order=12, output=HERE):
    lock=json.loads((HERE/'LOCK.json').read_text())
    for name,digest in lock['input_hashes'].items():
        assert hashlib.sha256((SPARC/name).read_bytes()).hexdigest()==digest,name
    sys.path.insert(0,str(donor.resolve()))
    os.environ['SPARC_DATA']=str(data.resolve())
    import ccc_core as cc
    import sparc_io as io
    for name,p in [('table1',io.T1),('table2',io.T2)]:
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==lock['SPARC'][name]
    t1=io.load_table1()
    t2=io.load_table2()
    prior=pd.read_csv(HERE.parent/'external14/scale_by_galaxy.csv').set_index('Galaxy')
    samples=pd.read_csv(SPARC/'samples.csv').set_index('Galaxy')
    a0s=lock['thresholds']
    controls=validate()
    rows,profiles=[],[]
    for gal,p in prior.iterrows():
        obs=t2[t2.Galaxy==gal].sort_values('R')
        r=obs.R.to_numpy()
        rg=mesh(r,subdivisions)
        v=obs.Vobs.to_numpy()
        sp=cc.smooth_vobs(r,v,obs.e_Vobs.to_numpy(),s_factor=.1)
        squared=lambda x:sp(x)**2
        dsquared=lambda x:2*sp(x)*sp.derivative()(x)
        signed=PchipInterpolator(r,v*abs(v))
        gas=PchipInterpolator(r,obs.Vgas*abs(obs.Vgas))
        densities=invert(r,rg,[(squared,dsquared),(signed,signed.derivative()),(gas,gas.derivative())],order)
        thin=densities[:,0]
        gas_surface=densities[:,2]+kepler_term(rg,r[-1],gas(r[-1]))
        star_surface=.5*np.interp(rg,r,obs.SBdisk)
        surfaces={'disk':thin,'disk_kepler':thin+kepler_term(rg,r[-1],squared(r[-1])),
                  'disk_pchip':densities[:,1], 'sphere_abel':sphere_projected(r,rg,squared,dsquared),
                  'baryonic_disk':star_surface+gas_surface}
        profiles.append(pd.DataFrame(dict(Galaxy=gal,R_kpc=r,**{k:s[::subdivisions] for k,s in surfaces.items()},
                                              stars=star_surface[::subdivisions],gas=gas_surface[::subdivisions])))
        for key,s in surfaces.items():
            for norm in ('mestel','unit'):
                for cal,a0 in a0s.items():
                    threshold=a0/GSI*(PC**2/MSUN)/(2*np.pi if norm=='mestel' else 1.)
                    status,rt,ndown,nup=crossing(rg,s,threshold)
                    vf=t1.at[gal,'Vflat']
                    at=vf**2*ACC/rt if vf>0 and np.isfinite(rt) else np.nan
                    rows.append(dict(Galaxy=gal,split=samples.at[gal,'split'],arm=key,norm=norm,cal=cal,
                        a0=a0,threshold_Msun_pc2=threshold,N=len(r),Rmin=r[0],Rmax=r[-1],Vflat=vf,
                        historical91=p.extended_resolved,historical_Rt=p.extended_Rt_kpc,historical_at=p.extended_at_m_s2,
                        crossing=status,Rt_kpc=rt,at_m_s2=at,q=at/a0,
                        q_local=(float(sp(rt))**2*ACC/(rt*a0) if np.isfinite(rt) else np.nan),
                        n_down=ndown,n_up=nup,
                        negative_fraction=float(np.mean(s<0)),Sigma_start=s[0],Sigma_end=s[-1]))
    output.mkdir(exist_ok=True,parents=True)
    pd.DataFrame(rows).to_csv(output/'crossings.csv',index=False)
    pd.concat(profiles).to_csv(output/'profiles.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    (output/'numeric_controls.json').write_text(json.dumps(controls,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('donor',type=Path)
    parser.add_argument('data',type=Path)
    parser.add_argument('--subdivisions',type=int,default=8)
    parser.add_argument('--order',type=int,default=12)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    run(args.donor,args.data,args.subdivisions,args.order,args.output)
