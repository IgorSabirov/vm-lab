"""Plot the two distinct comparisons from the stored summaries."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FixedFormatter
import numpy as np
import pandas as pd

p=Path(__file__).resolve().parent
disk=pd.read_csv(p/'disk_summary.csv')
est=json.loads((p/'residual_summary.json').read_text())['estimators']
f,axes=plt.subplots(1,2,figsize=(10,3.2),layout='constrained',gridspec_kw={'width_ratios':[1.15,1]})
plt.rcParams['svg.hashsalt']='R143-disk'
for ax in axes:
    ax.set_xscale('log')
    ax.axvline(1,ls='--',lw=.9,color='#52606d')
    ax.spines[['right','top','left']].set_visible(False)
    ax.tick_params(axis='y',length=0)
    ax.set_axisbelow(True)
    ax.grid(axis='x',alpha=.15)
ax=axes[0]
labels=[]
for i,(norm,cal) in enumerate([('mestel','canonical'),('mestel','R142'),('unit','canonical'),('unit','R142')]):
    a=disk.query("arm=='disk' and norm==@norm and cal==@cal").iloc[0]
    labels.append(('Канон' if cal=='canonical' else 'R142')+(' · 2πG' if norm=='mestel' else ' · G')+f'  (n={a.n})')
    ax.errorbar(a.q_disk,i,xerr=[[a.q_disk-a.disk_low],[a.disk_high-a.q_disk]],fmt='o',
                color='#006d77' if norm=='mestel' else '#975132',capsize=3)
ax.set(yticks=range(4),yticklabels=labels,ylim=(3.6,-.6),xlim=(.74,7.5),xlabel='Медиана aₜ / фиксированное a₀')
ax.set_title('Дисковый порог',loc='left',fontweight='bold')
ax.xaxis.set_major_locator(FixedLocator([.8,1,2,4,6]))
ax.xaxis.set_major_formatter(FixedFormatter(['0,8','1','2','4','6']))
ax=axes[1]
for i,(key,lab) in enumerate([('flat','Vflat'),('local','V(Rₜ), сплайн'),('linear','V(Rₜ), линейно')]):
    row=est[key]
    m=row['median_paired']
    lo,hi=row['paired95']
    ax.errorbar(m,i,xerr=[[m-lo],[hi-m]],fmt='o',color='#285587',capsize=3)
ax.axvline(1.42,ls=':',lw=1.4,color='#975132')
ax.set(yticks=range(3),yticklabels=['Vflat','V(Rₜ), сплайн','V(Rₜ), линейно'],ylim=(2.5,-.5),xlim=(.82,2.65),
       xlabel='Медиана индивидуальных aₜ / a₀')
ax.set_title('Сферические Rₜ · те же 91',loc='left',fontweight='bold')
ax.xaxis.set_major_locator(FixedLocator([1,1.42,2,2.5]))
ax.xaxis.set_major_formatter(FixedFormatter(['1','1,42','2','2,5']))
for ax in axes:
    ax.minorticks_off()
target=p/'scale_tests.svg'
f.savefig(target,metadata={'Date':None})
target.write_text('\n'.join(line.rstrip() for line in target.read_text().splitlines())+'\n')
