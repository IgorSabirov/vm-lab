"""Per-galaxy held-out loss differences. Positive values favour MOND."""
from pathlib import Path
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
p=parser.parse_args().out
d=pd.read_csv(p/'galaxy_scores.csv').query('split=="test"')
wide=d.pivot(index='Galaxy',columns='mode',values='delta_per_point').sort_values('forward_sharp')
fig,axes=plt.subplots(1,2,sharey=True,figsize=(10.2,9.3),layout='constrained')
for ax,key,title in zip(axes,['inverse_common','forward_sharp'],['Обратная реконструкция','Прямой прогноз']):
    y=np.arange(len(wide))
    vals=wide[key].to_numpy()
    ax.hlines(y,np.minimum(vals,0),np.maximum(vals,0),color='0.78')
    ax.scatter(vals,y,c=np.where(vals>0,'#246779','#b55124'),s=18,zorder=3)
    ax.axvline(0,color='0.3',lw=1)
    ax.set_xscale('symlog',linthresh=1)
    ax.set_xlim(-60,900); ax.set_xticks([-10,-1,0,1,10,100,700],['−10','−1','0','1','10','100','700'])
    ax.grid(axis='x',alpha=.2); ax.set_axisbelow(True)
    ax.set_title(title); ax.set_xlabel('Разность χ² / число радиусов')
axes[0].set_yticks(np.arange(len(wide)),wide.index,fontsize=8)
fig.suptitle('35 отложенных галактик SPARC\nСлева от нуля точнее CCC, справа — MOND',fontsize=14)
fig.savefig(p/'holdout.png',dpi=150)
