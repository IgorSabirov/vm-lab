"""Joined SPARC experiment. See README for arguments, units and score definitions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import pandas as pd
import scipy
from scipy.optimize import minimize_scalar

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
for arg in ('donor', 'rotmod', 'data', 'out'):
    parser.add_argument('--' + arg, type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
os.environ['SPARC_DATA'] = str(args.data.resolve())
sys.path.insert(0, str(args.donor.resolve()))
import sparc_io as io
import ccc_core as cc
import compare_models as cm
import smooth_ccc as sm

COLUMNS = ['R', 'Vobs', 'e_Vobs', 'Vgas', 'Vdisk', 'Vbul']
CATALOG_SHA = '5aa0501f6b0d881fa579030e315e7b5b6ef561a5bd3a07472f9929c7e5728243'
MODELS_SHA = '9108994b12cc401b94a1768beca61c53ec354779385c9c9cc571049f3043244c'
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(name, data):
    (out / name).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')

def write_csv(name, frame):
    frame.to_csv(out / name, index=False, float_format='%.15g',
                 compression={'method':'gzip', 'mtime':0} if name.endswith('.gz') else None)

def revision(directory):
    return subprocess.check_output(['git','-C',str(directory),'rev-parse','HEAD'], text=True).strip()

source = dict(donor=revision(args.donor), rotmod=revision(args.rotmod),
              table1=sha(io.T1), table2=sha(io.T2))
assert source == dict(donor='0a1b208227def246b43c691569adb2ae88b44231',
                      rotmod='84b581a5a197975ee7b21314a82e843d1e748a07',
                      table1=CATALOG_SHA, table2=MODELS_SHA)
catalog, mass = io.load_table1(), io.load_table2()
parts, split, distances, provenance = [], {}, {}, {}
for n, p in enumerate(sorted(args.rotmod.glob('*_rotmod.dat')), 1):
    name = p.name.removesuffix('_rotmod.dat')
    split[name] = 'test' if n % 5 == 0 else 'train'
    with p.open() as f:
        distances[name] = float(f.readline().split()[3])
    provenance[name] = sha(p)
    part = pd.DataFrame(np.loadtxt(p, ndmin=2)[:, :6], columns=COLUMNS)
    part.insert(0, 'Galaxy', name)
    parts.append(part)
raw = pd.concat(parts, ignore_index=True)
joined = mass.merge(raw, on=['Galaxy','R'], suffixes=('', '_R142'),
                    how='outer', validate='one_to_one', indicator=True)
assert joined._merge.eq('both').all() and set(split) == set(catalog.index)
assert all(np.array_equal(joined[c], joined[c+'_R142']) for c in COLUMNS[1:])
joined['split'] = joined.Galaxy.map(split)
joined['in_CCC'] = joined.groupby('Galaxy').R.transform('size') >= 6
joined['D_R142'] = joined.Galaxy.map(distances)
joined['D_Table1'] = joined.Galaxy.map(catalog.D)
joined['Inc_deg'] = joined.Galaxy.map(catalog.Inc)
assert np.array_equal(joined.D, joined.D_R142) and np.array_equal(joined.D, joined.D_Table1)
points = joined.sort_values(['Galaxy','R'])
write_csv('radial_join.csv.gz', points)
samples = []
for g, d in points.groupby('Galaxy'):
    c = catalog.loc[g]
    samples.append(dict(Galaxy=g, split=split[g], sorted_file_rank=list(split).index(g)+1,
                        rotmod_sha256=provenance[g], n_rotmod=len(d), n_table2=len(d),
                        n_shared=len(d), R_min=d.R.min(), R_max=d.R.max(), D_rotmod=distances[g],
                        D_table1=c.D, D_table2=d.D.iloc[0], e_D=c.e_D, Inc=c.Inc, e_Inc=c.e_Inc,
                        Vflat=c.Vflat, Q=c.Q, in_CCC=len(d)>=6,
                        reason='included' if len(d)>=6 else 'fewer_than_6_radii'))
samples = pd.DataFrame(samples)
write_csv('samples.csv', samples)
assert len(samples)==175 and len(points)==3391 and samples.in_CCC.sum()==165

# Instantiate the exact inverse predictor in the donor, without invoking its fitting loop.
master = (args.donor/'regen_all.py').read_text()
native = {}
exec(compile(master.split('t1, t2 = io.load_table1()')[0], 'regen_all.py', 'exec'), native)

def baryons(d):
    return cc.sparc_vbar(d.Vgas.to_numpy(), d.Vdisk.to_numpy(), d.Vbul.to_numpy())

def forward_profile(r, vb):
    grid, rb, _ = cm.rho_from_v(r, vb, s=0.5*len(r))
    return grid, rb

def vforward(kind, r, vb, profile, p):
    if kind == 'mond':
        return cm.mond_v(vb, r, p)
    grid, rb = profile
    if kind == 'sharp':
        return cm.ccc_forward(grid, rb, r, p)[0]
    # Same baryonic profile, core and clipping as the upstream forward sharp operator.
    # Replace only the local density relation by the donor's smooth standard nu.
    rb = np.maximum(rb, 0)
    ro = np.divide(rb, -np.expm1(-np.sqrt(rb/p)), out=np.zeros_like(rb), where=rb>0)
    dm = 4*np.pi*grid**2*ro
    mass = np.r_[0., np.cumsum(np.diff(grid)*(dm[1:]+dm[:-1])*0.5)]
    return np.sqrt(cc.G*np.interp(r, grid, mass)/r)

def prepare(d):
    r, v, e = d[['R','Vobs','e_Vobs']].to_numpy().T
    vb = baryons(d)
    return dict(r=r, v=v, e=e, vb=vb, profile=forward_profile(r, vb),
                slope=cc.inner_slope_of(cc.smooth_vobs(r,v,e,0.1), r))

def vinverse(kind, x, v, p):
    if kind == 'mond':
        return native['vb_mond'](x['r'], v, x['e'], p)
    return sm.vbx_smooth(x['r'], v, x['e'], p, kind='standard', inner_slope=x['slope'])

# Before scoring any held-out outcomes, estimate all free parameters using train IDs alone.
train = {g:prepare(d) for g,d in points.groupby('Galaxy') if split[g]=='train' and len(d)>=6}
r142_train = []
for g,d in raw.groupby('Galaxy'):
    if split[g]!='train':
        continue
    r,v,_,gas,disk,bul = d[COLUMNS].to_numpy().T
    sq=gas*abs(gas) + 0.5*disk*abs(disk) + 0.7*bul*abs(bul)
    ok=(r>0)&(v>0)&(sq>0)
    radius=r[ok]*3.0856775814913673e19
    r142_train.append((sq[ok]*1e6/radius, v[ok]**2*1e6/radius))
def r142_loss(lg):
    return np.mean([np.mean((np.log10(b/(-np.expm1(-np.sqrt(b/(10**lg)))))-np.log10(o))**2)
                    for b,o in r142_train])
r142_fit=minimize_scalar(r142_loss,bounds=(-12,-8),method='bounded')
assert len(r142_train)==140 and len(train)==130
def train_loss(logp, direction, kind):
    scores = []
    for x in train.values():
        if direction == 'forward':
            pred=vforward(kind,x['r'],x['vb'],x['profile'],10**logp)
            target, error=x['v'], np.maximum(x['e'],1.)
        else:
            pred=vinverse(kind,x,x['v'],10**logp)
            target, error=x['vb'], np.hypot(0.05*x['vb'],1.)
        scores.append(np.mean(np.square((pred-target)/error)))
    return np.mean(scores)
params={'r142_a0':10**r142_fit.x}
for direction, kinds in [('inverse',('standard','mond')),('forward',('sharp','standard','mond'))]:
    for kind in kinds:
        lo,hi=(-12.,-8.) if kind=='mond' else (3.,12.)
        grid=np.linspace(lo,hi,61)
        f=lambda p:train_loss(p,direction,kind)
        losses=[f(p) for p in grid]
        i=int(np.argmin(losses))
        opt=minimize_scalar(f,method='bounded',bounds=(grid[max(i-1,0)],grid[min(i+1,len(grid)-1)]))
        lg=min((grid[i],opt.x), key=f)
        params[direction+'_'+kind]=float(10**lg)
dump('freeze.json',dict(source=source,python=platform.python_version(),numpy=np.__version__,
      scipy=scipy.__version__,pandas=pd.__version__,params=params,train_common=sorted(train),
      train_r142=sorted(g for g in split if split[g]=='train'),test=sorted(g for g in split if split[g]=='test'),
      r142_train_loss=r142_loss(r142_fit.x),mc_draws=100,bootstrap_draws=10000,seed=143))
print('Freeze written',params,flush=True)

# Forward functions have no Vobs or e_Vobs argument. Produce forward curves before scoring.
predrows, controls, diag = [], [], []
for idx,(g,d) in enumerate(points.groupby('Galaxy')):
    r=d.R.to_numpy(); vb=baryons(d)
    r142_pred=vforward('mond',r,vb,None,params['r142_a0'])
    if len(r)<6:
        continue
    pf=forward_profile(r,vb)
    fw={k:vforward(k,r,vb,pf,params['forward_'+k]) for k in ('sharp','standard','mond')}
    # Negative control: reverse the order of the measured baryonic components at fixed radii.
    rev=vb[::-1]; pf_rev=forward_profile(r,rev)
    rev_preds={k:vforward(k,r,rev,pf_rev,params['forward_'+k]) for k in fw}
    diag.append(dict(Galaxy=g,split=split[g],negative_grid=int((pf[1]<0).sum()),grid=len(pf[0]),
                     negative_grid_fraction=np.mean(pf[1]<0),baryon_zero=int((vb==0).sum())))
    x=prepare(d); v,e=x['v'],x['e']
    inverse={k:vinverse(k,x,v,params['inverse_'+k]) for k in ('standard','mond')}
    noise=np.random.default_rng(np.random.SeedSequence([143,idx])).normal(size=(100,len(r)))*e
    err={}
    for k in inverse:
        sims=np.array([vinverse(k,x,v+z,params['inverse_'+k]) for z in noise])
        assert np.isfinite(sims).all()
        q16,q84=np.percentile(sims,[16,84],axis=0)
        err[k]=(q84-q16)*0.5
    phot=1+(0.05*vb)**2
    common=np.sqrt(phot + 0.5*(err['standard']**2+err['mond']**2))
    ef=np.maximum(e,1.)
    def record(mode,target,preds,sig_c,sig_m):
        c,m=preds
        for i in range(len(r)):
            predrows.append((g,split[g],r[i],mode,target[i],c[i],m[i],sig_c[i],sig_m[i],
                             c[i]-target[i],m[i]-target[i],((c[i]-target[i])/sig_c[i])**2-
                             ((m[i]-target[i])/sig_m[i])**2))
    record('inverse_common',vb,(inverse['standard'],inverse['mond']),common,common)
    record('inverse_model_sigma',vb,(inverse['standard'],inverse['mond']),
           np.sqrt(phot+err['standard']**2),np.sqrt(phot+err['mond']**2))
    for k in ('sharp','standard'):
        record('forward_'+k,v,(fw[k],fw['mond']),ef,ef)
    record('forward_sharp_R142',v,(fw['sharp'],r142_pred),ef,ef)
    scores=lambda p:float(np.mean(((p-v)/ef)**2))
    controls.append(dict(Galaxy=g,split=split[g],newton=scores(vb),
            **{k:scores(y) for k,y in fw.items()}, **{'reversed_'+k:scores(y) for k,y in rev_preds.items()}))
cols=['Galaxy','split','R','mode','target','CCC','MOND','sigma_CCC','sigma_MOND',
      'resid_CCC','resid_MOND','delta_chi2']
pred=pd.DataFrame(predrows,columns=cols)
assert np.isfinite(pred.select_dtypes('number')).all().all()
write_csv('predictions.csv.gz',pred)
write_csv('controls.csv',pd.DataFrame(controls))
write_csv('forward_geometry.csv',pd.DataFrame(diag))
# Re-evaluate the original acceleration score using all 35 files and the same signed cuts.
test_loss=[]
for g,d in raw.groupby('Galaxy'):
    if split[g]!='test': continue
    r,v,_,gas,disk,bul=d[COLUMNS].to_numpy().T
    sq=gas*abs(gas)+0.5*disk*abs(disk)+0.7*bul*abs(bul)
    ok=(r>0)&(v>0)&(sq>0); radius=r[ok]*3.0856775814913673e19
    b=sq[ok]*1e6/radius; obs=v[ok]**2*1e6/radius
    loss=np.mean((np.log10(b/(-np.expm1(-np.sqrt(b/params['r142_a0']))))-np.log10(obs))**2)
    test_loss.append(dict(Galaxy=g,n=int(ok.sum()),mse_log_acceleration=loss))
write_csv('r142_test.csv',pd.DataFrame(test_loss))
prior_r142=json.loads((HERE.parent.parent/'R142_MAGIC_NUMBERS/HOLDOUT_RESULTS.json').read_text())['mond']
assert np.isclose(params['r142_a0']/prior_r142['a0'],1.,atol=1e-7,rtol=0)
reference={x['galaxy']:x for x in prior_r142['test_galaxies']}
assert len(reference)==len(test_loss)==35
for row in test_loss:
    expected=reference[row['Galaxy']]
    assert row['n']==expected['n']
    np.testing.assert_allclose(row['mse_log_acceleration'],expected['mse'],atol=1e-12,rtol=0)
assert np.isclose(np.mean([x['mse_log_acceleration'] for x in test_loss]),prior_r142['test_mse'])
print('Matched frozen predictions finished',flush=True)
