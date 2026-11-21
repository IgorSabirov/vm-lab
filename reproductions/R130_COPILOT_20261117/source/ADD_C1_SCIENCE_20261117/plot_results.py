"""New seeded illustrations of the declared C1 experiment, not original figures."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
fig,axs=plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
colors=['#136f63','#2c6fbb','#b35321','#7a4497']
for j,seed in enumerate([202611170,202611171,202611172,202611173]):
    for inverse in (False,True):
        direction='backward' if inverse else 'forward'
        a=np.array(json.loads((HERE/f'uniform_{seed}_{direction}_samples.json').read_text()),dtype=object)
        t=a[:,0].astype(float); length=a[:,1].astype(float)
        style='--' if inverse else '-'
        axs[0,0].plot(-t if inverse else t,length,color=colors[j],ls=style,lw=1)
        axs[0,1].plot(-t if inverse else t,a[:,8].astype(float),color=colors[j],ls=style,lw=1)
        label=f'seed {str(seed)[-1]} '+('inverse' if inverse else 'forward')
        axs[0,2].loglog(t[1:],length[1:],color=colors[j],ls=style,lw=1,label=label)
        axs[1,0].plot(t,a[:,11].astype(float),color=colors[j],ls=style,lw=1)
        axs[1,1].plot(t,a[:,12].astype(float),color=colors[j],ls=style,lw=1)
for key,color in [('approaching_L128','#2c6fbb'),('isolated_double_L128','#b35321')]:
    a=np.array(json.loads((HERE/f'{key}_extended_backward_samples.json').read_text()),dtype=object)
    axs[1,2].plot(a[:,0].astype(float),a[:,1].astype(float),color=color,label=key)
titles=['Size, both time directions','Global entropy, natural log','Finite trajectories; no exponent fit proof','Mean local entropy, radius 5','Sum of local entropy, radius 5','Sparse inverse transient and later growth']
ylabels=['Vertices','ln binomial(2L,p)','Vertices','Mean entropy','Sum entropy','Vertices']
for ax,title,ylabel in zip(axs.flat,titles,ylabels):
    ax.set_title(title,fontsize=11); ax.set_xlabel('Step'); ax.set_ylabel(ylabel); ax.grid(alpha=.2)
axs[0,2].legend(fontsize=7,ncol=2); axs[1,2].legend(fontsize=8)
fig.suptitle('ADD C1 — author-clarified A; new reproducible samples, 17 Nov 2026',fontsize=15)
fig.savefig(HERE/'FIGURES.png',dpi=150)
fig.savefig(HERE/'FIGURES.svg')
plt.close(fig)
