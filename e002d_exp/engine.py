"""Extend diagnostics while preserving the pinned RK4 integration."""
import numpy as np
import re
from e002c_exp.engine import Trajectory as BaseTrajectory
from e002c_exp.engine import compare_pair as base_compare_pair
from e002c_exp.model import operators
from .plan import TARGETS

def compare_pair(a,b):
    """Undefined conditional values are the only permitted nonfinite diagnostics."""
    for key in ("series","diagnostics"):
        x,y=a[key],b[key]
        if x.shape!=y.shape or not np.array_equal(x[:,0],y[:,0]):
            return dict(pass_gate=False,reason="grid_mismatch",errors={})
        if np.isinf(x).any() or np.isinf(y).any():
            return dict(pass_gate=False,reason="infinite_value",errors={})
        if not np.array_equal(np.isnan(x),np.isnan(y)):
            return dict(pass_gate=False,reason="conditional_validity_mismatch",errors={})
        for obj in (a,b):
            values=obj[key];names=["time"]+obj["names" if key=="series" else "dnames"]
            for j in np.flatnonzero(np.isnan(values).any(axis=0)):
                name=names[j];bad=np.isnan(values[:,j]);allowed=np.zeros(len(values),bool)
                m=re.fullmatch(r"(?:N_s([0-8])_cut[0-2]|W_s([0-8]))",name) if key=="diagnostics" else None
                c=re.fullmatch(r"c01_m([67])_(?:re|im)",name) if key=="diagnostics" else None
                if m:allowed=values[:,names.index("valid_s"+(m[1] or m[2]))]==0
                if c:
                    indices=np.searchsorted(obj["series"][:,0],values[:,0])
                    if np.any(indices>=len(obj["series"])) or not np.array_equal(obj["series"][indices,0],values[:,0]):
                        return dict(pass_gate=False,reason="conditional_support_grid",errors={})
                    allowed=obj["series"][indices,1+obj["names"].index("p_m"+c[1])]<=1e-6
                if np.any(bad&~allowed):return dict(pass_gate=False,reason="unexpected_nan",errors={})
    return base_compare_pair(a,b)

class Trajectory(BaseTrajectory):
    def sample(self,step):
        super().sample(step)
        if step%round(2/self.case["dt"])==0:
            rho=self.v.reshape(216,216,order="F");values=[];names=[]
            for key,(mask,a,b) in TARGETS.items():
                edge=np.flatnonzero(operators()["mask_id"]==mask)
                block=rho[np.ix_(a*27+edge,b*27+edge)]
                names.append("full_target_norm_"+key);values.append(float(np.linalg.norm(block)))
            self.dnames+=names;self.diags[-1]=np.r_[self.diags[-1],values]

    def release_kernel(self):
        # State/window/history remain for the declared continuation. Never retain 184 Liouvillians.
        self.model={k:self.model[k] for k in ("names","alpha","dark","checks")}

    def rebuild_kernel(self,builder):
        before=self.model["names"];model=builder(self.case)
        if model["names"]!=before:raise ValueError("Kernel schema changed across continuation")
        self.model=model

