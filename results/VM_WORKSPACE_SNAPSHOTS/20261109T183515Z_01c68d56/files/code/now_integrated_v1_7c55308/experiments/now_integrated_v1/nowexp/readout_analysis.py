"""Conditioning of a declared two-population reconstruction, not full tomography."""
import math
import numpy as np
from . import memory


def reconstruction(config,noise_bound=1e-4,allowed_population_error=.01,condition_limit=100.):
    columns=[]
    for bit in (0,1):
        data=memory.write(bit,config.memory,0,config.bath_modes,config.bath_coupling,config.detuning)
        column=np.zeros(3)
        for value,probability,_,_ in memory.outcomes(data,config.read_wait):
            column[2 if value is None else value]+=probability
        columns.append(column)
    jacobian=np.array(columns).T
    singular=np.linalg.svd(jacobian,compute_uv=False)
    floor=math.sqrt(3)*noise_bound/allowed_population_error
    minimum=float(singular[-1]);condition=float(singular[0]/minimum) if minimum>0 else None
    return dict(matrix=jacobian.tolist(),singular_values=singular.tolist(),sigma_min=minimum,
        sigma_floor=floor,condition=condition,condition_limit=condition_limit,
        noise_bound_per_observed_probability=noise_bound,allowed_population_error=allowed_population_error,
        robust=minimum>=floor and condition is not None and condition<=condition_limit,
        estimated_error_bound=None if minimum==0 else math.sqrt(3)*noise_bound/minimum,
        reconstructed_object='two classical input populations in the declared orthogonal record basis',
        arbitrary_quantum_coherences_reconstructed=False)
