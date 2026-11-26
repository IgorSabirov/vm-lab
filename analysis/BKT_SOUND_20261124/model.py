"""Reduced frequencies and unit f-sum oscillator amplitudes for Fig. 2a."""
import ctypes
import subprocess
import tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
BOUND = np.sqrt(2)
LOW = np.array([.65, .03, .035, .04, 0.])
HIGH = np.array([3., .9999, 3., 18., 1.])
STARTS = np.array([[1.45, .50, .5, .56, .18], [1.45, .50, .5, 2.4, .18],
                   [1.15, .38, .35, 1., .35], [1.7, .60, .8, 1.8, .35],
                   [1.35, .72, .45, .5, .55]])
SEED = 1432411
_temp = tempfile.TemporaryDirectory()
_lib = None


def osc(t, w, g):
    return (1/np.pi)*g*t/((t*t-w*w)**2 + (g*t)**2)


def response(t, p):
    w1, s, g1, r, h = p
    return (1-h)*osc(t,w1,g1) + h*osc(t,w1*s,w1*s*r)


def physical(p):
    w1,s,g1,r,h = p
    w2=w1*s
    return np.array([w1,w2,g1,r*w2,(1-h)/(np.pi*w1**2),h/(np.pi*w2**2)])


def disc(p):
    return (p[...,0]*p[...,1])**2*(1-p[...,3]**2/2)


def batch(t, e, y, boundary=False, starts=STARTS):
    global _lib
    if _lib is None:
        so = Path(_temp.name)/'fit.so'
        subprocess.run(['c++','-std=c++17','-O3','-shared','-fPIC',str(ROOT/'lm.cpp'),'-o',str(so)],check=True)
        _lib = ctypes.CDLL(str(so))
        arr = np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')
        _lib.batch_fit.argtypes = 3*[ctypes.c_int] + 7*[arr]
        _lib.batch_fit.restype = None
    y=np.atleast_2d(y)
    lo,hi=LOW.copy(),HIGH.copy()
    if boundary: lo[3]=hi[3]=BOUND
    out=np.empty((len(y),6))
    args=[np.ascontiguousarray(a,dtype='d') for a in (t,e,y,starts,lo,hi)]
    _lib.batch_fit(len(y),len(t),len(starts),*args,out)
    return out


def statistics(t,e,ys,starts=STARTS):
    free=batch(t,e,ys,starts=starts)
    edge=batch(t,e,ys,True,starts=starts)
    # The boundary is part of the unrestricted space.
    on_edge=edge[:,0]<free[:,0]
    free[on_edge]=edge[on_edge]
    lr=np.maximum(0,edge[:,0]-free[:,0])
    return lr,disc(free[:,1:]),free,edge


def inputs(label):
    return np.loadtxt(ROOT/'data'/f'{label}.txt',skiprows=1).T


def write_json(path, obj):
    import json
    def convert(x):
        return x.tolist() if hasattr(x,'tolist') else float(x)
    path.write_text(json.dumps(obj,indent=2,default=convert,allow_nan=False)+'\n')
