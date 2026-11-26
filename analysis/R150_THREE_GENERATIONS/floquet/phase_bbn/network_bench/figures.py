from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from bench import ROOT

R=ROOT/'results'
def make():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.edgecolor':'#8a9b9d','axes.labelcolor':'#243c43',
                         'xtick.color':'#35494d','ytick.color':'#35494d','legend.frameon':False})
    fig,ax=plt.subplots(figsize=(7.35,3.0),layout='constrained')
    for name,label,color in [('direct','Прямой контакт','#165b72'),('mediated','Посредник, 50 с','#d58131'),
                             ('coupled','С обратной связью','#962855'),('slow','Посредник, 500 с','#729792')]:
        a=np.genfromtxt(R/(name+'.csv'),names=True,delimiter=',')
        ax.plot(a['Tgamma_MeV']*1000,1000*a['deltaBD_MeV'],label=label,lw=2.2,color=color)
    ax.axvspan(68.56,76.26,color='#699e95',alpha=.14)
    ax.set(xlim=(115,40),ylim=(0,1.5),xlabel='Температура фотонов, кэВ (время идёт вправо)',ylabel='Сдвиг энергии дейтрона, кэВ')
    ax.grid(axis='y',alpha=.17);ax.legend(ncols=2,fontsize=9,loc='upper left')
    fig.savefig(R/'mediator_history.png',dpi=190);plt.close(fig)
    r=json.loads((R/'finite_model.json').read_text())
    fig,ax=plt.subplots(figsize=(7.35,2.8),layout='constrained')
    for gd,col in [(28,'#829597'),(106.75,'#ca8046'),(202,'#165b72')]:
        v=[s for s in r['screen'] if s['epsilon']==.4 and s['g_dec']==gd and s['g_X']==1 and s['graph_bath']=='photon']
        ax.plot([s['L'] for s in v],[s['rho_over_one_nu'] for s in v],'-o',color=col,label=f'g*ₛ = {gd:g}',lw=1.9)
    ax.axhline(.17,color='#962855',linestyle='--',label='Порог опыта 0,17')
    ax.set(yscale='log',xticks=[3,5,7,9,15],xlabel='Длина активного графа L',ylabel='ρₓ / ρ одного сорта ν')
    ax.grid(axis='y',alpha=.16);ax.legend(ncols=2,loc='best',fontsize=8)
    fig.savefig(R/'relic_screen.png',dpi=190);plt.close(fig)

if __name__=='__main__':make()
