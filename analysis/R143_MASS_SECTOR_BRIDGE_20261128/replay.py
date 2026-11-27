#!/usr/bin/env python3
"""Finite-dimensional replay for R143–R150–R132. Python 3 + NumPy.
Dimensionless model only; no physical calibration is implied.
"""
import json
from pathlib import Path
import numpy as np

def Q6p1(phi, t=1.0, g=1.0):
    # A=(0,2,4), B=(1,3,5,p); R149 seam convention.
    return np.array([[t, 0, t*np.exp(-1j*phi), g],
                     [t, t, 0, 0],
                     [0, t, t, 0]], dtype=complex)

def main():
    t, g, M, v = 1.0, 1.0, 2.4, 1.7
    phases = [k*np.pi/4 for k in range(9)]
    rows, edge_rows = [], []
    errs = dict(chiral=0.0, D2=0.0, Fkernel=0.0, Qnull=0.0, spectrum=0.0)
    for phi in phases:
        q = Q6p1(phi,t,g); na,nb=q.shape
        h=np.block([[np.zeros((na,na),complex),q],
                    [q.conj().T,np.zeros((nb,nb),complex)]])
        gamma=np.diag(np.r_[np.ones(na),-np.ones(nb)])
        b=np.array([1,-1,1,-(t/g)*(1+np.exp(-1j*phi))],complex)
        b/=np.linalg.norm(b)
        psi=np.r_[np.zeros(na,complex),b]
        errs["Qnull"]=max(errs["Qnull"],float(np.max(np.abs(q@b))))
        errs["chiral"]=max(errs["chiral"],float(np.max(np.abs(gamma@h+h@gamma))))
        d=v*h-M*gamma; ev=np.linalg.eigvalsh(d)
        errs["D2"]=max(errs["D2"],float(np.max(np.abs(d@d-(M*M*np.eye(na+nb)+v*v*h@h)))))
        nplus=int(np.sum(np.abs(ev-M)<2e-10)); nminus=int(np.sum(np.abs(ev+M)<2e-10))
        edge_rows.append({"phi_over_pi":float(phi/np.pi),"n_plus_M":nplus,
                          "n_minus_M":nminus,"index":nb-na})
        x=q.conj().T@q; lam,u=np.linalg.eigh(x)
        f=(u*(np.sqrt(M*M+v*v*lam)-M))@u.conj().T
        errs["Fkernel"]=max(errs["Fkernel"],float(np.max(np.abs(f@b))))
        s=np.linalg.svd(q,compute_uv=False)
        expected=np.sort(np.r_[-np.sqrt(M*M+v*v*s*s),np.sqrt(M*M+v*v*s*s)])
        actual=np.sort(np.delete(ev,np.argmin(np.abs(ev-M))))
        errs["spectrum"]=max(errs["spectrum"],float(np.max(np.abs(expected-actual))))
        p=4*t*t*np.cos(phi/2)**2/(3*g*g+4*t*t*np.cos(phi/2)**2)
        rows.append({"phi_over_pi":float(phi/np.pi),"P_formula":float(p),
                     "P_vector":float(abs(b[-1])**2),"rank_Q":int(np.linalg.matrix_rank(q))})
    rng=np.random.default_rng(14320261128); generic=[]
    for na,nb in [(2,3),(3,4),(4,6),(5,3)]:
        q=rng.normal(size=(na,nb))+1j*rng.normal(size=(na,nb))
        h=np.block([[np.zeros((na,na),complex),q],[q.conj().T,np.zeros((nb,nb),complex)]])
        gamma=np.diag(np.r_[np.ones(na),-np.ones(nb)])
        ev=np.linalg.eigvalsh(v*h-M*gamma); rank=int(np.linalg.matrix_rank(q))
        np_=int(np.sum(np.abs(ev-M)<5e-9)); nm=int(np.sum(np.abs(ev+M)<5e-9))
        generic.append({"N_A":na,"N_B":nb,"rank_Q":rank,"index":nb-na,
                       "n_plus_M":np_,"n_minus_M":nm,"edge_difference":np_-nm})
    out={"schema":"R143_MASS_SECTOR_BRIDGE_v1","status":"MODEL_REPLAY_ONLY_NOT_PHYSICAL_CALIBRATION",
         "parameters_dimensionless":{"t":t,"g":g,"M":M,"v":v},"phase_sweep":rows,
         "mass_edge_tests":edge_rows,"generic_rectangular_tests":generic,"max_residuals":errs,
         "checks":{"all_rank_3":all(x["rank_Q"]==3 for x in rows),
                   "P_matches":all(abs(x["P_formula"]-x["P_vector"])<2e-14 for x in rows),
                   "mass_index":all(x["n_plus_M"]-x["n_minus_M"]==1 for x in edge_rows),
                   "generic_index":all(x["edge_difference"]==x["index"] for x in generic)}}
    assert all(out["checks"].values()) and max(errs.values())<1e-12
    Path(__file__).with_name("RESULTS.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out["checks"],indent=2)); print(json.dumps(errs,indent=2))

if __name__=="__main__": main()
