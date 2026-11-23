"""Extract independent photometry/HI for the locked LT14 galaxies. No target velocities."""
import argparse
import csv
import hashlib
import json
import re
import tarfile
from pathlib import Path

import fitz
import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
URL = 'https://vizier.cfa.harvard.edu/viz-bin/asu-tsv?-source='
SOURCES = {'herr': 'J/AJ/146/104', 'hunter': 'J/AJ/144/134'}


def rows(source, key):
    # VizieR metadata contain request date and server host. Preserve scientific rows separately.
    part = source.read_text().split('#Table\t')
    block, = [t for t in part if t.startswith(key + ':')]
    lines = [x for x in block.splitlines() if x.startswith('recno\t') or re.match(r'^\s*\d+\t', x)]
    return [{k: v.strip() for k, v in row.items()} for row in csv.DictReader(lines, delimiter='\t')]


def name(s):
    return re.sub('[^a-z0-9]', '', s.lower())


def haro_profile(source):
    with tarfile.open(source) as archive:
        pdf = archive.extractfile('rMD_DH_DM_profiles_haro36.pdf').read()
    page = fitz.open(stream=pdf, filetype='pdf')[0]
    # Major tick labels read from panels (a), (b), (c): page coordinates in points.
    # (c) R=0,1,2,3; mass surface density=0,10,20.
    x_to_r = np.polyfit([328.32, 351.60, 374.64, 397.68], [0, 1, 2, 3], 1)
    y_to_mass = np.polyfit([238.40, 212.24, 186.08], [0, 10, 20], 1)
    y_to_magnitude = np.polyfit([186.08, 203.60, 220.88, 238.40], [20, 22, 24, 26], 1)
    y_to_ml = np.polyfit([241.76, 222.08, 202.40, 182.72], [.2, .3, .4, .5], 1)
    points, slopes, ratios = [], [], []
    for d in page.get_drawings():
        b = d['rect']
        if d['fill'] and abs(d['fill'][0] - .588) < .002 and 330 < b.x0 < 411 and 180 < b.y0 < 239 and 2 < b.width < 3:
            points.append(((b.x0+b.x1)/2, (b.y0+b.y1)/2))
        if 90 < b.x0 < 94 and 190 < b.y0 < 196 and 70 < b.width < 76 and len(d['items']) == 10:
            slopes.append(y_to_magnitude[0]*(b.height/b.width)/x_to_r[0])
        if 206 < b.x0 < 207 and b.width > 80 and b.height < .01 and 210 < b.y0 < 215:
            ratios.append(np.polyval(y_to_ml, b.y0))
    assert len(points) == 11 and len(slopes) == len(ratios) == 1
    r = np.polyval(x_to_r, np.array(sorted(points))[:, 0])
    intensity = np.polyval(y_to_mass, np.array(sorted(points))[:, 1]) / ratios[0]
    assert np.all(intensity > 0)
    h = (2.5/np.log(10))/slopes[0]
    def profile(x):
        if x > r[-1]:
            return intensity[-1]*np.exp(-(x-r[-1])/h)
        return np.interp(x,r,intensity)
    knots = sorted([0., *r])
    def enclosed(x):
        interior = [b for b in knots if 0 < b < x]
        return sum(quad(lambda z: z*profile(z), l, u)[0] for l, u in zip([0]+interior,interior+[x]))
    total = enclosed(r[-1])+intensity[-1]*h*(r[-1]+h)
    reff = brentq(lambda x: enclosed(x)-total/2, 0, r[-1]+30*h)
    pd.DataFrame(dict(R_kpc=r, L36_per_pc2=intensity)).to_csv(HERE/'haro_profile.csv',index=False)
    return reff,2*np.pi*1e6*total,h,ratios[0]


def broken(row, axis_ratio):
    hi,ho,rb,mu_i,mu_o = (float(row[k]) for k in ('hi','ho','RBr','mu0i','mu0o'))
    lum_i,lum_o = (10**(.4*(3.24+21.572-mu)) for mu in (mu_i,mu_o))
    # Integral of r*I(r) for each exponential, radius in kpc and I in Lsun/pc^2.
    def inside(r):
        return lum_i*hi**2*(1-(1+r/hi)*np.exp(-r/hi))
    def outside(r):
        return lum_o*ho*(ho+r)*np.exp(-r/ho)
    total=inside(rb)+outside(rb)
    def enclosed(r):
        return inside(r) if r<=rb else total-outside(r)
    reff=brentq(lambda r: enclosed(r)-total/2,0,rb+50*ho)
    return reff,2*np.pi*axis_ratio*1e6*total


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sources',type=Path)
    p.add_argument('--download',action='store_true')
    args=p.parse_args()
    if args.download:
        from urllib.request import urlopen
        args.sources.mkdir(exist_ok=True,parents=True)
        for key,cat in SOURCES.items():
            (args.sources/key).write_bytes(urlopen(URL+cat+'&-out.all&-out.max=unlimited',timeout=60).read())
        (args.sources/'ohtex').write_bytes(urlopen('https://arxiv.org/src/1502.01281',timeout=90).read())
    assert hashlib.sha256((args.sources/'ohtex').read_bytes()).hexdigest()=='71af16551af8316b17a8904de06917b4a2a9faa387d24155903f5b075df9a9d6'
    ids=json.loads((HERE/'LOCK.json').read_text())['ids']
    hi={name(r['Name']):r for r in rows(args.sources/'hunter','J_AJ_144_134_galaxies')}
    phot={name(r['Name']):r for r in rows(args.sources/'herr','J_AJ_146_104_table4') if r['Band']=='3.6um'}
    dist={name(r['Name']):float(r['Dist']) for r in rows(args.sources/'herr','J_AJ_146_104_table1')}
    raw=[]
    for gal in ids:
        k=name(gal)
        h=hi[k]
        q=float(h['b/a'])
        distance=dist[k]
        props={}
        if k in phot:
            m=phot[k]
            reff,lum=broken(m,q)
            props={j:m[j] for j in ('Type','hi','ho','RBr','mu0i','mu0o','n_Ne')}
            props.update(source='Herrmann2013 Table4 3.6um',phot_recno=m['recno'])
        else:
            assert k=='haro36'
            distance=9.3
            reff,lum,scale,ml=haro_profile(args.sources/'ohtex')
            props.update(source='Oh2015 Appendix C Haro36 panels a/b/c',tail_h_kpc=scale,ML_source=ml)
        mhi=10**float(h['MHI'])*(distance/float(h['Dist']))**2
        raw.append(dict(Galaxy=gal,Re_kpc=reff,L36_Lsun=lum,MHI_Msun=mhi,
                        logMHI_source=h['MHI'],D_HI_Mpc=h['Dist'],D_phot_Mpc=distance,
                        q=q,HI_recno=h['recno'],**props))
    pd.DataFrame(raw).to_csv(HERE/'photometry.csv',index=False)
