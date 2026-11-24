"""python holdout.py /path/to/Rotmod_LTG /path/to/SPARC_Lelli2016c.mrt"""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import lsq_linear, minimize_scalar

HERE = Path(__file__).resolve().parent
lock = json.loads((HERE/'HOLDOUT_LOCK.json').read_text())
raw = json.loads((HERE/'NUCLEAR_INPUT.json').read_text())
mass = raw['mass_excess_keV']
rows = {}
for z, sym in [(22,'ti'),(20,'ca')]:
    design, observed, labels = [], [], []
    for n in (2,4,6,8):
        a = z+20+n
        observed.append((mass[f'{z}/{a-2}'][0]+2*mass['0/1'][0]-mass[f'{z}/{a}'][0])/1000)
        design.append([-2,(12-2*n)/4*2])  # P(n)-P(n-2), P=n(10-n)/4
        labels.append(f'S2n {a}{sym}')
    for n in (2,4,6):
        a = z+20+n
        observed.append(float(raw['levels_keV'][f'{a}{sym}']['energy'])/1000)
        design.append([0,4])
        labels.append(f'E2 {a}{sym}')
    rows[z] = (np.asarray(design),np.asarray(observed),labels)
X,y,_ = rows[22]
params = lsq_linear(X,y,bounds=([-np.inf,0],[np.inf,np.inf])).x
base = [y[:4].mean()]*4+[y[4:].mean()]*3
X,y,labels = rows[20]
pred = X @ params
A = np.zeros((4,6))
for i in range(4):
    A[i,i:i+2]=[1,-1]
A[:,5]=2
sd = np.array([mass[f'20/{40+2*i}'][1] for i in range(5)]+[mass['0/1'][1]])/1000
cov = {}
for rho in (0,.5):
    R=np.eye(6)
    R[:5,:5]=(1-rho)*np.eye(5)+rho
    cov[rho]=(A@(R*np.outer(sd,sd))@A.T).tolist()
def scores(p):
    err=(y-p)**2
    return dict(joint=err.mean(),S2n=err[:4].mean(),E2=err[4:].mean())
nuclear=dict(parameters_MeV=params.tolist(),training=rows[22][2],training_rank=int(np.linalg.matrix_rank(rows[22][0])), delta2n_MeV=dict(observed=(-np.diff(y[:4])).tolist(),pairing=(-np.diff(pred[:4])).tolist(),baseline=(-np.diff(base[:4])).tolist()),
             predictions=[dict(name=l,observed=v,pairing=w,baseline=b) for l,v,w,b in zip(labels,y,pred,base)],
             mse_MeV2=dict(pairing=scores(pred),baseline=scores(base)),S2n_cov_scenarios_MeV2=cov)

catalog_path=Path(sys.argv[2])
names = {p.name.split('_rotmod')[0] for p in Path(sys.argv[1]).glob('*_rotmod.dat')}
catalog={l.split()[0]:l.split() for l in catalog_path.read_text().splitlines() if len(l.split())>=18 and l.split()[0] in names}
galaxies=[]
for i,path in enumerate(sorted(Path(sys.argv[1]).glob('*_rotmod.dat')),1):
    a=np.loadtxt(path,ndmin=2)
    r,v,_,gas,disk,bulge=a[:,:6].T
    signed=lambda x:x*abs(x)
    sq=signed(gas)+.5*signed(disk)+.7*signed(bulge)
    ok=(r>0)&(v>0)&(sq>0)
    if not ok.any():continue
    radius=r[ok]*3.0856775814913673e19
    gal=path.name.split('_rotmod')[0]
    galaxies.append((gal,i%5==0,sq[ok]*1e6/radius,v[ok]**2*1e6/radius, radius[-1],v[ok][-1]))
assert i==175
def residual(g,a0):
    bar,obs=g[2:4]
    return np.log10(bar/(-np.expm1(-np.sqrt(bar/a0))))-np.log10(obs)
def loss(loga,test):
    return np.mean([np.mean(residual(g,10**loga)**2) for g in galaxies if g[1]==test])
loga=minimize_scalar(lambda x:loss(x,False),bounds=(-12,-8),method='bounded').x
a0=10**loga
G=6.67430e-11
MS=1.98847e30
per=[]
for g in galaxies:
    if not g[1]:continue
    name,_,bar,obs,r,v=g
    item=dict(galaxy=name,n=len(bar),mse=np.mean(residual(g,a0)**2),
              btfr_enclosed_proxy_dex=np.log10((bar[-1]*r*r/G)/((v*1000)**4/(G*a0))))
    line=catalog[name]
    vf=float(line[15])
    if vf>0:
        m=(.5*float(line[7])+1.33*float(line[13]))*1e9
        item['catalog_btfr_dex']=np.log10(m*MS*G*a0/(vf*1000)**4)
    per.append(item)
rng=np.random.default_rng(142)
null=10**rng.uniform(-12,-8,10000)
cosmo={}
for h,err in [(67.4,.5),(73.04,1.04)]:
    scale=299792458*rng.normal(h,err,10000)/3.0856775814913673e19
    refs=scale[:,None]*np.array([1,1/(2*np.pi),np.sqrt(.6847)])
    distance=lambda x:np.min(abs(np.log(np.asarray(x)/refs)),axis=1)
    success=distance(null[:,None])<=distance(a0)
    cosmo[h]=dict(success=int(success.sum()),trials=len(success),fraction=success.mean())
bt=[p['catalog_btfr_dex'] for p in per if 'catalog_btfr_dex' in p]
mond=dict(a0=a0,train=len(galaxies)-len(per),test=len(per),train_mse=loss(loga,False),test_mse=loss(loga,True),
          catalog_btfr_count=len(bt),catalog_btfr_rms_dex=np.mean(np.square(bt))**.5,
          enclosed_proxy_rms_dex=np.mean([p['btfr_enclosed_proxy_dex']**2 for p in per])**.5,
          test_galaxies=per,null=cosmo,catalog_sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest())
(HERE/'HOLDOUT_RESULTS.json').write_text(json.dumps(dict(nuclear=nuclear,mond=mond),indent=2)+'\n')
