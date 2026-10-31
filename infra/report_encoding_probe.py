"""Offline container-size stress probe, NOT an evolved trajectory or scientific data."""
import io,json,lzma,time,zipfile
from pathlib import Path
import numpy as np

def encode(arrays,method,fortran=False,shuffle=False,whole_xz=False):
    stream=io.BytesIO()
    if shuffle:
        info={k:dict(dtype=a.dtype.str,shape=list(a.shape)) for k,a in arrays.items()}
        arrays={k:np.ascontiguousarray(np.ascontiguousarray(a).view(np.uint8).reshape(-1,a.dtype.itemsize).T) for k,a in arrays.items()}
        arrays["__byte_shuffle__"]=np.array(json.dumps(info,separators=(",",":")))
    with zipfile.ZipFile(stream,"w",compression=method,allowZip64=True) as z:
        for key,a in arrays.items():
            s=io.BytesIO();np.save(s,np.asfortranarray(a) if fortran else a,allow_pickle=False);z.writestr(key+".npy",s.getvalue())
    return lzma.compress(stream.getvalue(),format=lzma.FORMAT_XZ,preset=6) if whole_xz else stream.getvalue()

def decoded(z):
    if "__byte_shuffle__" not in z:return {k:z[k] for k in z.files}
    info=json.loads(str(z["__byte_shuffle__"]))
    return {k:np.frombuffer(np.ascontiguousarray(z[k].T).tobytes(),dtype=np.dtype(v["dtype"])).reshape(v["shape"]) for k,v in info.items()}

def expanded(original,horizon,noise,rng):
    out={k:v.copy() for k,v in original.items()}
    scalar=np.r_[np.arange(51)*.2,np.arange(12,horizon+1,4.)]
    diagnostic=np.r_[np.arange(0,22,2.),np.arange(24,horizon+1,4.)]
    window=np.arange(190,202,2.) if horizon==200 else np.r_[np.arange(190,202,2.),np.arange(390,402,2.)]
    for key,times in (("series",scalar),("diagnostics",diagnostic),("window_blocks",window),
                      ("window_scalar",window),("window_diagnostics",window)):
        old=original[key];a=np.repeat(old[-1:],len(times),axis=0)
        finite=np.isfinite(a)&(a!=0)
        a[finite]*=1+noise*rng.standard_normal(np.count_nonzero(finite))
        if key in ("series","diagnostics"):
            a[:min(len(old),len(a))]=old[:min(len(old),len(a))]
        if key!="window_blocks":a[:,0]=times
        out[key]=a
    out["window_time"]=window
    for key in list(out):
        if key.startswith("e_") and not key.startswith("e_extreme"):
            old=original[key];out[key]=np.concatenate([old[:1],old[-1:],old[-1:]],axis=0)
    out["e_time"]=np.array([2.,20.,horizon])
    # Real producer exports identical values whenever sample/window/evidence overlap.
    # Independent per-array noise must not destroy these guaranteed redundancies.
    for window_key,series_key in (("window_scalar","series"),("window_diagnostics","diagnostics")):
        for i,t in enumerate(window):
            hits=np.flatnonzero(out[series_key][:,0]==t)
            if len(hits):out[window_key][i]=out[series_key][hits[0]]
    out["e_blocks"][-1]=out["window_blocks"][-1]
    return out

def main():
    start=time.monotonic();paths=sorted(Path("calibration_cache/files/cases").glob("*.npz"));rng=np.random.default_rng(777)
    # Twelve spread cases cover both models and a variety of phase/intervention conditions.
    paths=[paths[i] for i in np.linspace(0,len(paths)-1,12,dtype=int)];rows=[]
    for path in paths:
        with np.load(path,allow_pickle=False) as z:source={k:z[k] for k in z.files}
        for horizon in (200.,400.):
            for noise in (0.,1e-12,1e-6):
                arrays=expanded(source,horizon,noise,rng)
                for method,label,fortran in ((zipfile.ZIP_STORED,"whole_xz",False),(zipfile.ZIP_STORED,"whole_xz_F",True)):
                    t=time.monotonic();data=encode(arrays,method,fortran,False,True);elapsed=time.monotonic()-t
                    with np.load(io.BytesIO(lzma.decompress(data)),allow_pickle=False) as z:
                        decoded_arrays=decoded(z);assert set(decoded_arrays)==set(arrays)
                        for k,a in arrays.items():assert decoded_arrays[k].dtype==a.dtype and decoded_arrays[k].shape==a.shape and decoded_arrays[k].tobytes()==a.tobytes()
                    rows.append(dict(case=path.stem,horizon=horizon,relative_noise=noise,codec=label,bytes=len(data),seconds=elapsed))
    output=dict(kind="offline encoding stress; fabricated late samples, no scientific interpretation",forecast=dict(expected_seconds=60,lower_seconds=0,upper_seconds=180),actual_seconds=time.monotonic()-start,rows=rows)
    Path("encoding_whole_probe.json").write_text(json.dumps(output,indent=2)+"\n")
    for horizon in (200.,400.):
        for noise in (0.,1e-12,1e-6):
            for codec in ("whole_xz","whole_xz_F"):
                rs=[r for r in rows if r["horizon"]==horizon and r["relative_noise"]==noise and r["codec"]==codec]
                print(json.dumps(dict(horizon=horizon,noise=noise,codec=codec,max_case_bytes=max(r["bytes"] for r in rs),mean_case_bytes=np.mean([r["bytes"] for r in rs]),max_total_184_plus_10MiB=184*max(r["bytes"] for r in rs)+10*1024**2)))
    print("PROBE_SECONDS",output["actual_seconds"],flush=True)
if __name__=="__main__":main()
