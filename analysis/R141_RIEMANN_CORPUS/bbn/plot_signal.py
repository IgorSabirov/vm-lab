"""Plot the two independently varied controls from SIGNAL_CHECKS.json."""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

here = Path(__file__).resolve().parent
data = json.loads((here/'SIGNAL_CHECKS.json').read_text())['spectrum_tests']
colors = ['#075985', '#b34b12']
fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), layout='constrained')
left, right = axes
for key, label, color, symbol in zip(('GOE','GUE'), ('COE','CUE'), colors, ('o','s')):
    table = data['finite_circle_DH_obs_sd'][key]
    n = [int(k) for k in table]
    y = [table[str(k)][0] for k in n]
    left.plot(n, y, label=label, color=color, marker=symbol, markersize=4)
    left.axhline(data['marks'][key]['equal']['obs_sd'][0], color=color, lw=.8, ls='--')
left.set_xscale('log',base=2)
left.set_xticks([4,16,64,256,1024],['4','16','64','256','1024'])
left.set(xlabel='Уровней на окружности',ylabel='Разброс D/H, в наблюдательных σ',
         title='Конечное окно, равные силы', ylim=(0,.115))
left.legend(frameon=False)
labels=['Равные\nсилы','Общий закон\nсил','Одна\nширина','Два\nканала']
for i, (key, color) in enumerate(zip(('GOE','GUE'),colors)):
    fields=['equal','common_chi2_2','one_width','balanced_two_channels']
    y=[data['marks'][key][field]['obs_sd'][0] for field in fields]
    right.bar(np.arange(4)+(i-.5)*.36,y,width=.35,color=color,label=key)
right.set_xticks(range(4),labels)
right.set(title='Большой спектр, разные силы',ylabel='Разброс D/H, в наблюдательных σ',ylim=(0,1))
right.legend(frameon=False,loc='upper left',ncols=2)
for ax in axes:
    ax.grid(axis='y',alpha=.18)
    ax.set_axisbelow(True)
    ax.spines[['top','right']].set_visible(False)
fig.savefig(here/'signal.png',dpi=150)
