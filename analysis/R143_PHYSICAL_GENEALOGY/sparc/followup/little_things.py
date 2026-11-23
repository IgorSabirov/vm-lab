"""External test on Oh et al. 2015. Axes calibrated from printed ticks alone."""
import argparse
from pathlib import Path
from io import StringIO
import json
import re
import sys
import tarfile

import fitz
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
import astropy.units as u

p=argparse.ArgumentParser()
p.add_argument('sources',type=Path)
p.add_argument('donor',type=Path)
args=p.parse_args()
sys.path.insert(0,str(args.donor.resolve()))
import ccc_core as cc
import compare_models as cm

out=Path(__file__).resolve().parent
freeze=json.loads((out.parent/'freeze.json').read_text())['params']
def table(file,key):
    s=(args.sources/file).read_text().split('#Table')[1:]
    sect=next(s0 for s0 in s if key in s0.splitlines()[0])
    lines=[l for l in sect.splitlines()[1:] if l and not l.startswith('#')]
    frame=pd.read_csv(StringIO('\n'.join([lines[0]]+lines[3:])),sep='\t')
    for c in frame.select_dtypes('object'):
        frame[c]=frame[c].str.strip()
    return frame
oh=table('ohviz','galaxies')
all_obs=table('ohviz','rotdmbar')
sp=table('sparcpos','table1')
assert len(sp)==175 and len(oh)==26
a=SkyCoord(oh.RAJ2000.to_list(),oh.DEJ2000.to_list(),unit=(u.hourangle,u.deg))
b=SkyCoord(sp._RA.to_numpy()*u.deg,sp._DE.to_numpy()*u.deg)
idx,sep,_=a.match_to_catalog_sky(b)
oh['nearest_SPARC']=sp.Name.iloc[idx].to_numpy()
oh['sep_arcmin']=sep.arcmin
assert not ((sep.arcmin>=2)&(sep.arcmin<15)).any()
# Major-tick intervals read from the plotted axis labels of the source PDFs.
# Each leftmost labelled x and lowest labelled y tick on this panel is zero.
y_step={'cvnidwa':10,'ddo101':20,'ddo126':20,'ddo133':20,'ddo154':20,'ddo168':20,
        'ddo210':5,'ddo216':10,'ddo43':10,'ddo46':20,'ddo47':20,'ddo50':20,'ddo52':20,
        'ddo53':10,'ddo70':20,'ddo87':20,'f564_v3':10,'haro29':20,'haro36':20,'ic10':10,
        'ic1613':10,'ngc1569':20,'ngc2366':20,'ngc3738':50,'ugc8508':20,'wlm':20}
names=lambda s:re.sub('[^a-z0-9]','',s.lower())
def components(page,gal):
    xt,yt=set(),set(); curves={}; markers=[]
    for d in page.get_drawings():
        box=d['rect']
        if (d['fill'] and abs(d['fill'][0]-.588)<.003 and 0.7<box.width<5.3 and
                80<box.x0<274 and 432<box.y0<573):
            markers.append(((box.x0+box.x1)/2,(box.y0+box.y1)/2))
        for path in d['items']:
            if path[0]!='l': continue
            a,b=path[1],path[2]
            if abs(a.x-b.x)<.02 and 79<a.x<274 and abs(max(a.y,b.y)-572.00)<.15 and 6.2<abs(a.y-b.y)<7.1:
                xt.add(round(a.x,2))
            if abs(a.y-b.y)<.02 and 435<=a.y<=572.2 and abs(min(a.x,b.x)-80.4)<.15 and 6.3<abs(a.x-b.x)<7.1:
                yt.add(round(a.y,2))
        dash=d['dashes'] or ''
        if dash.startswith('[ 1.439') and d['rect'].x1<274 and d['rect'].y0>=432 and d['rect'].y1<574 and len(d['items'])>1:
            k='star' if '7.680' in dash else 'gas'
            arr=np.array([(l[1].x,l[1].y) for l in d['items']]+[(d['items'][-1][2].x,d['items'][-1][2].y)])
            if np.all(np.diff(arr[:,0])>=0) and arr[-1,0]-arr[0,0]>18:
                curves[k]=arr
    xt=np.array(sorted(xt)); yt=np.array(sorted(yt,reverse=True))
    assert len(xt)>=2 and len(yt)>=2
    xtstep=.2 if gal in ['ic10','ddo210'] else 1
    xcoef=np.polyfit(xt,np.arange(len(xt))*xtstep,1)
    ycoef=np.polyfit(yt,np.arange(len(yt))*y_step[gal],1)
    for k,xy in curves.items():
        curves[k]=(np.polyval(xcoef,xy[:,0]),np.polyval(ycoef,xy[:,1]))
        # Plotted data symbols are an independent check of axis calibration. They never enter the predictors.
    markers=np.array(markers).reshape(-1,2)
    check=np.c_[np.polyval(xcoef,markers[:,0]),np.polyval(ycoef,markers[:,1])]
    return curves,abs(xcoef[0])*.5,abs(ycoef[0])*.5,check
scores=[];rows=[]
with tarfile.open(args.sources/'ohtex') as archive:
    for galaxy,dy in y_step.items():
        row=oh.loc[oh.Name.map(names)==names(galaxy)].iloc[0]
        g=row.Name
        rec=dict(Galaxy=g,nearest=row.nearest_SPARC,sep_arcmin=row.sep_arcmin,source='Oh2015')
        scores.append(rec)
        if row.sep_arcmin<2:
            rec['status']='overlap';continue
        pdf=archive.extractfile('rMD_DH_DM_profiles_'+galaxy+'.pdf').read()
        q,dr,dv,markers=components(fitz.open(stream=pdf,filetype='pdf')[0],galaxy)
        if set(q)!={'gas','star'}:
            rec['status']='missing_baryonic_curve';continue
        d=all_obs[(all_obs.Name==g)&(all_obs.Type=='Data')].sort_values('R')
        r=(d.R*d['R0.3']).to_numpy();v=(d.V*d['V0.3']).to_numpy();e=(d.e_V*d['V0.3']).to_numpy()
        keep=(r>=max(x[0] for x,y in q.values())-dr)&(r<=min(x[-1] for x,y in q.values())+dr)&(r>0)&(e>0)
        r,v,e=r[keep],v[keep],e[keep]
        if len(r)<6:
            rec.update(status='fewer_than_6',n=len(r));continue
        gas,star=[np.interp(r,*q[k]) for k in ['gas','star']]
        def evaluate(shift):
            gs,st=gas+shift,star+shift
            vb=np.sqrt(np.maximum(0,gs*abs(gs)+st*abs(st)))
            rg,rho,_=cm.rho_from_v(r,vb,s=.5*len(r))
            return cm.ccc_forward(rg,rho,r,freeze['forward_sharp'])[0],cm.mond_v(vb,r,freeze['forward_mond'])
        delta_loss=lambda c,m:np.mean(((c-v)/np.maximum(e,1))**2-((m-v)/np.maximum(e,1))**2)
        c,m=evaluate(0)
        assert len(markers),galaxy
        near=np.abs(r[:,None]-markers[None,:,0]).argmin(axis=1)
        paired=np.abs(r-markers[near,0])<=dr
        rec['axis_matches']=int(paired.sum())
        rec['axis_max_error_kms']=float(np.max(np.abs(v[paired]-markers[near[paired],1]))) if paired.any() else np.nan
        rec.update(status='tested',n=len(r),n_catalog=len(d),tick_half_point_kms=dv,delta=delta_loss(c,m),
                   delta_shift_minus=delta_loss(*evaluate(-dv)),delta_shift_plus=delta_loss(*evaluate(dv)))
        for i in range(len(r)):
            rows.append((g,r[i],v[i],e[i],gas[i],star[i],c[i],m[i]))
pd.DataFrame(scores).to_csv(out/'little_sample.csv',index=False)
pd.DataFrame(rows,columns=['Galaxy','R','Vobs','eV','Vgas','Vstar','CCC','MOND']).to_csv(out/'little_radial.csv',index=False)
print(pd.DataFrame(scores)[['Galaxy','status','nearest','sep_arcmin','n','delta']].to_string(index=False))
