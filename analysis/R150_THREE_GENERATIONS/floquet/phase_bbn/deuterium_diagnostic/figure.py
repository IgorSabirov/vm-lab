"""Render the diagram in README.md from the archived numerical reanalysis."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root=Path(__file__).resolve().parent
data=json.loads((root/'result.json').read_text())['engines']['linx']
early=np.array(data['early_percent'])
late=np.array(data['late_percent'])
matched=early[1]+data['eqY_gap_D_pp']
fig,(ax,bx)=plt.subplots(2,1,figsize=(6.4,6.8),layout='constrained')
blue,red='#27638c','#b34e34'
ax.plot([0,early[0]],[0,early[1]],'o-',color=blue,label='Раннее окно')
ax.plot([0,late[0]],[0,late[1]],'o-',color=red,label='Позднее окно')
ax.vlines(early[0],early[1],matched,colors='#59616a',linestyles='dotted')
ax.scatter(early[0],matched,facecolor='white',edgecolor=red,zorder=4,s=55)
ax.annotate('0,805 п. п. по D/H',xy=(early[0],(early[1]+matched)/2),
            xytext=(.072,.35),arrowprops={'arrowstyle':'-','color':'#656565'})
ax.legend(loc='upper left',frameon=False)
ax.set(xlim=(-.004,.152),ylim=(-.035,.99),xlabel='Изменение Yₚ, %',ylabel='Изменение D/H, %',
       title='Расширение в двух температурных окнах')
j=np.array(data['JDD'])*100
ys=np.arange(4)[::-1]
for i,(color,label) in enumerate([(blue,'d+d → ³He+n'),(red,'d+d → t+p')]):
    bx.barh(ys+(1-2*i)*.17,j[:,i],height=.29,color=color,label=label)
bx.set(yticks=ys,yticklabels=['Yₚ','D/H','³He/H','⁷Li/H'],
       xlabel='100 × ∂ln(выхода)/∂q',title='Изменение двух ядерных скоростей')
bx.axvline(0,color='#5f6570',lw=.8)
bx.legend(loc='upper right',frameon=False,fontsize=9)
for axis in [ax,bx]:
    axis.spines[['top','right']].set_visible(False)
    axis.grid(axis='x',color='#9ca3aa',alpha=.25)
fig.savefig(root/'windows_and_rates.png',dpi=170)
