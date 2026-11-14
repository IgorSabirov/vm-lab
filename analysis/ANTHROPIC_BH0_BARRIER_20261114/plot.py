"""Render computed data; no additional physical inference or solver run."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
rows=json.loads((HERE/'results/ATLAS.json').read_text())['rows']
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','axes.spines.top':False,
                     'axes.spines.right':False,'font.size':11})
fig,axs=plt.subplots(1,2,figsize=(12,4.8))
r=rows[4];q=float(r['q']);a=float(r['a_coexist'])
u=np.linspace(0,.525,1400)
w=np.zeros_like(u);m=u>.5
w[m]=.25-.5*np.log(2*(1-u[m]))-u[m]**2
v=(w+a*u*u-q*u**4)/q
axs[0].plot(u,v,color='#184c78',lw=2.4)
axs[0].scatter([0,float(r['u_barrier']),float(r['u_coexist'])],
               [0,float(r['delta_phi'])/q,0],c=['#138a72','#e58c25','#138a72'],s=55,zorder=3)
axs[0].axvline(.5,color='#a9b2bc',lw=1,ls=':')
axs[0].set(xlabel='Polyakov-loop magnitude u',ylabel=r'$\phi(u)/|b|$',
           title=r'Coexistence landscape ($\lambda=1$)',ylim=(-.002,.026))
axs[0].annotate('barrier',xy=(float(r['u_barrier']),float(r['delta_phi'])/q),
                xytext=(.17,.021),arrowprops={'arrowstyle':'->','color':'#555555'})
ls=np.array([float(r['lambda_value']) for r in rows[:5]])
ns=np.array([float(r['N_at_action_height_1']) for r in rows[:5]])
axs[1].loglog(ls,ns,'o-',color='#184c78',lw=2,label=r'$N^2\Delta\phi=1$')
axs[1].loglog(ls,np.sqrt(10)*ns,'s-',color='#138a72',lw=2,label=r'$N^2\Delta\phi=10$')
axs[1].loglog(ls,207.850999/ls,':',color='#e58c25',label=r'leading $N\lambda=207.85$')
axs[1].set(xlabel=r"'t Hooft coupling $\lambda$",ylabel='N (action-height diagnostic)',
           title='A small coupling gives a small barrier')
axs[1].legend(frameon=False,fontsize=9)
for ax in axs:ax.grid(alpha=.18)
fig.suptitle('BH0 | A phase minimum is not a lifetime',fontsize=17,x=.05,ha='left')
fig.text(.05,.035,'Imported b. Reduced potential only. No finite-N measure, transition rate or BBN coupling.',fontsize=10,color='#555555')
fig.tight_layout(rect=[.02,.08,.99,.93])
fig.savefig(HERE/'results/ATLAS.svg',metadata={'Date':None})
parser=argparse.ArgumentParser();parser.add_argument('--preview',type=Path);args=parser.parse_args()
if args.preview:fig.savefig(args.preview,dpi=140)
