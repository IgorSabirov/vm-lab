"""Four-dimensional joint carrier and explicit local measurement instruments.

The measured classical records enter the existing continuation engine. This
does not replace its finite memory by an entangled spin/proton material model.
"""
import numpy as np


def instrument_distribution(preparation):
    if preparation not in ('bell_x','dephased_x','bell_z','dephased_z'):
        raise ValueError('unknown joint preparation')
    bell=np.array([1,0,0,1],complex)/np.sqrt(2)
    rho=np.outer(bell,bell.conj())
    if preparation.startswith('dephased'):rho=np.diag(np.diag(rho))
    local=np.array([[1,1],[1,-1]],complex)/np.sqrt(2) if preparation.endswith('_x') else np.eye(2)
    u=np.kron(local,local)
    rotated=u@rho@u.conj().T
    probabilities=np.diag(rotated).real
    if min(probabilities)<-1e-12 or abs(sum(probabilities)-1)>1e-12:raise ArithmeticError('invalid joint instrument')
    probabilities=np.maximum(probabilities,0);probabilities/=sum(probabilities)
    outcomes=[]
    for i,p in enumerate(probabilities):
        if p==0:continue
        ket=u.conj().T[:,i]
        post=np.outer(ket,ket.conj())
        outcomes.append(dict(bits=[i//2,i%2],probability=float(p),
            post_real=post.real.tolist(),post_imag=post.imag.tolist()))
    reduced_a=np.trace(rho.reshape(2,2,2,2),axis1=1,axis2=3)
    reduced_b=np.trace(rho.reshape(2,2,2,2),axis1=0,axis2=2)
    return dict(preparation=preparation,outcomes=outcomes,
        marginal_a=reduced_a.real.tolist(),marginal_b=reduced_b.real.tolist(),
        rho_real=rho.real.tolist(),rho_imag=rho.imag.tolist(),
        classical_record_created_by='local_projective_measurements',
        unknown_quantum_state_copied=False)
