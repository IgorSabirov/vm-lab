"""Plot the measured speed pairs and stage-2 inversions without joining temperatures."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from inversion import HERE

def render():
    data=json.loads((HERE/'results.json').read_text())
    rows=data['records']
    t=np.array([r['measurement']['T_over_Tc'] for r in rows])
    dt=np.array([r['measurement']['err_T'] for r in rows])
    fig,(ax,az)=plt.subplots(1,2,figsize=(10,4.2),layout='constrained')
    for f,label,color in [('c1','Первый звук','#626782'),('c2','Второй звук','#007875')]:
        ax.errorbar(t,[r['measurement'][f] for r in rows],yerr=[r['measurement']['err_'+f] for r in rows],
                    xerr=dt,fmt='o',ms=4,capsize=2,alpha=.9,label=label,color=color,elinewidth=1.)
    ax.set(xlabel=r'$T/T_c$',ylabel=r'$c/c_B$',title='Опубликованные скорости')
    ds=np.array([r['nominal']['Ds'] for r in rows])
    bounds=np.array([r['nominal']['interval95'][0] for r in rows])
    az.errorbar(t,ds,yerr=np.array([ds-bounds[:,0],bounds[:,1]-ds]),fmt='o',ms=5,color='#007875',
                capsize=3,label='Номинальная шкала, 95% по скоростям')
    az.scatter(t,data['joint_fits']['baseline']['Ds'],s=35,marker='s',facecolors='none',edgecolors='#a7562c',
               label='Общая калибровка')
    az.scatter(t,[r['author_Ds'] for r in rows],s=30,marker='+',color='#3c4056',label='Авторский контроль')
    az.axhline(4,color='#8a8a8a',ls=':',lw=1)
    az.set(xlabel=r'Опубликованное $T/T_c$',ylabel=r'$D_s=n_s\lambda_T^2$',title='Зависимость от калибровки')
    for a in (ax,az):
        a.axvline(1,color='#999',ls='--',lw=.8)
        a.spines[['top','right']].set_visible(False)
        a.legend(loc='best',frameon=False,fontsize=8)
    fig.savefig(HERE/'density.png',dpi=155)
    plt.close(fig)

if __name__=='__main__': render()
