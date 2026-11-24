"""Prepare measured combinations for the EOS stage, preserving unknown covariance."""
import csv
import io
import zipfile
import numpy as np
from model import ROOT

def read(archive,member):
    return np.loadtxt(io.BytesIO(archive.read(member)),skiprows=1)

def eos_inversion(c1,c2,c10_sq,gamma,thermal_speed_sq,D):
    """Inputs in identical speed units. Two estimates coincide for consistent EOS.
    thermal_speed_sq = T*s**2/(m*cV). Carry the shared inputs jointly when fitting.
    """
    via_sum=c1*c1+c2*c2-c10_sq
    via_product=gamma*(c1*c2)**2/c10_sq
    def density(v):
        return D*v/(v+thermal_speed_sq) if v>=0 else None
    return density(via_sum),density(via_product)

def rows():
    with zipfile.ZipFile(ROOT/'data'/'cambridge.zip') as z:
        c1=read(z,'Figure 3/Fig3a_firstSound_redData.txt')
        c2=read(z,'Figure 3/Fig3a_secondSound_blueData.txt')
        d=read(z,'Figure 3/Fig3b_superfluid_density.txt')
        f=read(z,'Figure 2/Fig2c_f2_BottomPanel.txt')
        total=read(z,'Figure 2/Fig2c_fsum_TopPanel.txt')
    if not all(np.array_equal(c1[:,0],a[:,0]) for a in [c2,f,total]):
        raise ValueError('Temperature keys differ')
    if not np.allclose(c1[:,0]*d[:,0],1,rtol=1e-7):
        raise ValueError('Density and temperature axes do not match')
    output=[]
    for i in np.argsort(c1[:,0]):
        T,dT,u,du=c1[i]; v,dv=c2[i,2:]
        row=dict(T_over_Tc=T,err_T=dT,c1=u,err_c1=du,c2=v,err_c2=dv,
                 author_f2=f[i,2],err_f2=f[i,3],author_fsum=total[i,2],err_fsum=total[i,3],
                 D_over_Dc=d[i,0],author_Ds=d[i,2],err_author_Ds=d[i,3])
        # Zero pairs from above Tc encode the authors' mode assignment.
        valid=v>0 and dv>0
        row['spectral_status']='two_sound_speeds' if valid else 'classified_normal'
        a,b=2*u*du,2*v*dv
        c,h=2*u*v*v*du,2*v*u*u*dv
        row.update(S=(u*u+v*v if valid else None),P=((u*v)**2 if valid else None),
                   sigma_S_min=(abs(a-b) if valid else None),sigma_S_max=(a+b if valid else None),
                   sigma_P_min=(abs(c-h) if valid else None),sigma_P_max=(c+h if valid else None))
        output.append(row)
    return output

if __name__=='__main__':
    result=rows()
    with (ROOT/'results'/'THERMO_INPUTS.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,result[0].keys(),lineterminator='\n')
        writer.writeheader(); writer.writerows(result)
