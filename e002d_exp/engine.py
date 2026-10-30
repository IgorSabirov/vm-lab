"""Extend diagnostics while preserving the pinned RK4 integration."""
import numpy as np
from e002c_exp.engine import Trajectory as BaseTrajectory
from e002c_exp.model import operators
from .plan import TARGETS

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

