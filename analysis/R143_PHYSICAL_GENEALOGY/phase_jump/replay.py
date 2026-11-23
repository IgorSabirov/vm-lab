#!/usr/bin/env python3
"""Replay R143/U013 common-beta phase-jump comparison from published digitization."""
import argparse, csv, json
from pathlib import Path
import numpy as np

def interp(x, xp, fp):
    return float(np.interp(x, xp, fp))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fig15",type=Path,required=True)
    p.add_argument("--figures",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("COMMON_BETA.json"))
    a=p.parse_args()
    with a.fig15.open(newline="") as f: rows=list(csv.DictReader(f))
    fig=json.loads(a.figures.read_text())
    groups={}
    for r in rows:
        key=(int(r["Ns"]),int(r["LT"]),r["series"])
        groups.setdefault(key,[]).append({k:(v if k=="series" else float(v)) for k,v in r.items()})
    for v in groups.values(): v.sort(key=lambda q:q["T_over_Tc"])
    cal=np.asarray(fig["calibration_curve_Nt_beta"],float)
    def beta_of_x(x): return interp(8*x,cal[:,0],cal[:,1])
    def x_of_beta(beta): return interp(beta,cal[:,1],cal[:,0])/8
    def phase(n,lt,series,x):
        d=groups[(n,lt,series)]
        xx=np.array([q["T_over_Tc"] for q in d])
        yy=np.array([q["w_over_T4"] for q in d])
        return interp(x,xx,yy)
    specs=[(48,6),(64,8)]
    lo=max(groups[(n,lt,s)][0]["T_over_Tc"] for n,lt in specs for s in ("hot","cold"))
    hi=min(groups[(n,lt,s)][-1]["T_over_Tc"] for n,lt in specs for s in ("hot","cold"))
    def jump(n,lt,x): return phase(n,lt,"hot",x)-phase(n,lt,"cold",x)
    grid=np.linspace(lo,hi,2001)
    contrast=np.array([jump(48,6,x)-jump(64,8,x) for x in grid])
    roots=[]
    for i in range(1,len(grid)):
        if contrast[i-1]*contrast[i]<0:
            x=grid[i-1]+(grid[i]-grid[i-1])*(-contrast[i-1])/(contrast[i]-contrast[i-1])
            roots.append({"T_over_Tc":float(x),"beta":beta_of_x(float(x))})
    betas=[(6.0616,"beta_c_48"),(6.06247,"beta_c_64"),(6.06307,"beta_c_infinity_table"),(6.063172936,"F8_anchor")]
    points=[]
    for beta,label in betas:
        x=x_of_beta(beta)
        j48,j64=jump(48,6,x),jump(64,8,x)
        points.append({"beta":beta,"tag":label,"T_over_Tc":x,"deltaJ_48":j48,"deltaJ_64":j64,"volume_contrast":j48-j64})
    out={"id":"R143-U013-COMMON-BETA-v1","common_T_over_Tc":[lo,hi],"common_beta":[beta_of_x(lo),beta_of_x(hi)],"points":points,"crossings":roots,"covariance":"NOT_AVAILABLE; digitized marginal error bars are not joint covariance","status":"CENTRAL_CURVES_REPLAYED; scientific_acceptance=false; U013=OPEN"}
    a.out.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
