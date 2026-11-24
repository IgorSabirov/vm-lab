import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from model import ROOT, inputs, response, osc

def render():
    records=json.loads((ROOT/'results'/'BLIND.json').read_text())
    keys=json.loads((ROOT/'preregistration'/'reveal.json').read_text())['map']
    curves=json.loads((ROOT/'results'/'PROFILE.json').read_text())
    fig,axes=plt.subplots(2,2,figsize=(8.1,5.7),layout='constrained')
    for col,label in enumerate(sorted(keys,key=lambda k:keys[k]['T_over_Tc'])):
        a=records[label]; t,y,e=inputs(label)
        ax=axes[0,col]; w=np.linspace(0.001,2,800); p=a['p_internal']
        ax.errorbar(t,y,yerr=e,fmt='o',ms=4,color='#182332',elinewidth=1,capsize=2,label='Cambridge')
        ax.plot(w,response(w,p),color='#007875',lw=2,label='S4')
        w1,s,g,r,h=p
        ax.plot(w,h*osc(w,w1*s,w1*s*r),'--',color='#aa5124',label='Вторая мода')
        ax.set(title=f"{keys[label]['T_over_Tc']:.2f} $T_c$  ·  {len(t)} точек",
               xlabel=r'$\omega/\omega_B$',ylabel=r'$\widetilde{A}$',xlim=(0,2),ylim=(0,.65))
        if col==0: ax.legend(frameon=False,fontsize=8)
        ax=axes[1,col]; curve=np.array(curves[label]); bound=[-.4,.85] if a['verdict']=='positive' else [-5,.85]
        ax.plot(*curve.T,color='#007875',lw=2)
        ax.axhline(a['critical95'],color='#82492c',ls='--',lw=1.1,label='Порог 95%')
        ax.axvline(0,color='#555555',ls=':',lw=1.1)
        ax.plot(a['d'],0,'o',color='#007875',ms=4)
        ax.set(xlabel=r'$d=(\omega_2^2-\Gamma_2^2/2)/\omega_B^2$',ylabel=r'$\Delta\chi^2$',
               xlim=bound,ylim=(-.3,12))
        if col==0: ax.legend(frameon=False,fontsize=8)
    for ax in axes.flat:
        ax.spines[['right','top']].set_visible(False)
    fig.savefig(ROOT/'results'/'spectra.png',dpi=150)
    plt.close(fig)

if __name__=='__main__': render()
