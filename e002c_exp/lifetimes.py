"""Source-off absorption and accumulated isolation times from pinned NESS states."""
import time
import numpy as np
from scipy import sparse as sp
from scipy.integrate import simpson
from scipy.sparse.linalg import splu, expm_multiply
from e002_exp.model import build_liouvillian, maxabs
from .model import build, ONE, operators
from .export import digest

MASKS = (0,1,2,4)


def accumulated_integral(a,initial,observables,horizon):
    """Independent exponential action on an augmented ODE, without quadrature."""
    count=observables.shape[1]
    augmented=sp.bmat([[a,None],[sp.csr_matrix(observables.conj().T),sp.csr_matrix((count,count))]],format='csc')
    state=np.vstack([initial,np.zeros((count,initial.shape[1]),complex)])
    final=expm_multiply(augmented*horizon,state,traceA=a.diagonal().sum()*horizon)
    return final[:-count],final[-count:]


def absorption_generator(model):
    ix = (ONE[:,None]*27+np.arange(27)).ravel()
    h = model['H'][ix,:][:,ix]
    eye = sp.eye(81,format='csr')
    a = -1j*(sp.kron(eye,h)-sp.kron(h.T,eye))
    jumps = [(name,c) for name,c in model['jumps'] if name!='source_0']
    for name,c in jumps:
        # Keep loss to the vacuum even though the sink's restricted jump is zero.
        loss = (c.getH()@c)[ix,:][:,ix]
        reduced = c[ix,:][:,ix]
        a += sp.kron(reduced.conjugate(),reduced)-.5*(sp.kron(eye,loss)+sp.kron(loss.T,eye))
    a = a.tocsc()
    vi = (ix[:,None]+216*ix[None,:]).reshape(-1,order='F')
    full = build_liouvillian(model['H'],jumps)
    residual = maxabs(a-full[vi,:][:,vi])
    if residual > 1e-12:
        raise ValueError('Reduced absorption generator differs from full source-off generator')
    return a, ix, residual


def measure(full_source, source_files, output):
    result=[]
    for label in ('QS','RR_QS'):
        start=time.monotonic();cid=label+'_P05_dt005';meta=source_files[cid]
        path=full_source/meta['path']
        if path.stat().st_size!=meta['bytes'] or digest(path)!=meta['sha256']:
            raise ValueError('Full initial state differs from pinned GitHub manifest')
        with np.load(path,allow_pickle=False) as z:rho=z['rho']
        if rho.shape!=(216,216) or not np.isfinite(rho).all() or np.max(abs(rho-rho.conj().T))>1e-9 or abs(np.trace(rho)-1)>1e-9 or np.linalg.eigvalsh(rho)[0]<-1e-8:
            raise ValueError('Invalid source state')
        model=build(dict(model=label,phi_over_pi=0.,detuning=0.,dephasing=.05))
        a,ix,reduced_residual=absorption_generator(model)
        projectors=[]
        for mask in MASKS:
            p=sp.kron(model['dark'][mask]['isolated'],operators()['masks'][mask],format='csr')
            projectors.append(p[ix,:][:,ix].toarray())
        total_iso=sum(projectors);trace=np.eye(81).reshape(-1,order='F')
        obs=np.column_stack([trace,total_iso.reshape(-1,order='F')])
        lu=splu(a.getH().tocsc());dual=lu.solve(-obs.astype(complex))
        residual=float(np.max(abs(a.getH()@dual+obs)))
        tmat=dual[:,0].reshape(81,81,order='F');imat=dual[:,1].reshape(81,81,order='F')
        certificate=dict(reduced_generator_residual=reduced_residual,dual_residual=residual,
            dual_hermiticity=float(np.max(abs(tmat-tmat.conj().T))),
            min_total_time_eigenvalue=float(np.linalg.eigvalsh(tmat)[0]),
            max_total_time_eigenvalue=float(np.linalg.eigvalsh(tmat)[-1]),
            min_isolated_time_eigenvalue=float(np.linalg.eigvalsh(imat)[0]),
            min_transport_time_eigenvalue=float(np.linalg.eigvalsh(tmat-imat)[0]))
        if residual>1e-9 or certificate['dual_hermiticity']>1e-9 or min(certificate[k] for k in
            ('min_total_time_eigenvalue','min_isolated_time_eigenvalue','min_transport_time_eigenvalue')) < -1e-9:
            raise ValueError('Absorption time certificate failed')
        r=rho[np.ix_(ix,ix)];initial=[];weights=[]
        for p in projectors:
            block=p@r@p;weight=float(np.trace(block).real)
            if weight<=1e-6:raise ValueError('Undefined conditional isolated state')
            weights.append(weight);initial.append((block/weight).reshape(-1,order='F'))
        initial=np.column_stack(initial)
        exact=(dual.conj().T@initial).real
        grid=np.arange(0.,402.,2.)
        evolved=expm_multiply(a,initial,start=0.,stop=400.,num=len(grid),traceA=a.diagonal().sum())
        survival=np.einsum('i,tij->tj',trace,evolved).real
        isolated=np.einsum('i,tij->tj',obs[:,1],evolved).real
        tail=(dual.conj().T@evolved[-1]).real
        approx=np.stack([simpson(survival,x=grid,axis=0),simpson(isolated,x=grid,axis=0)])+tail
        integration_error=abs(approx-exact)
        monotonic=float(np.max(np.diff(survival,axis=0)))
        final_min=float(min(np.linalg.eigvalsh(evolved[-1,:,j].reshape(81,81,order='F'))[0] for j in range(4)))
        if np.max(abs(survival[0]-1))>1e-10 or monotonic>1e-10 or survival.min()<-1e-10 or final_min<-1e-9 or isolated.min()<-1e-10 or np.max(isolated-survival)>1e-10:
            raise ValueError('Survival physical check failed')
        # A step-two display grid can alias fast isolated-population oscillations.
        # Certify the integral with a separate augmented exponential, not a loose
        # quadrature tolerance. Preserve the old Simpson residual in the report.
        final_aug,integral_aug=accumulated_integral(a,initial,obs,400.)
        augmented_error=float(np.max(abs(integral_aug+dual.conj().T@final_aug-exact)))
        propagation_error=float(np.max(abs(final_aug-evolved[-1])))
        if augmented_error>1e-7 or propagation_error>1e-9:
            raise ValueError(f'Augmented integral mismatch: {augmented_error}; propagation {propagation_error}')
        certificate.update(augmented_integral_residual=augmented_error,augmented_propagation_residual=propagation_error,
            coarse_Simpson_error=integration_error.tolist(),original_Simpson_gate_pass=bool(np.max(integration_error)<=.02))
        rows=[dict(mask=mask,initial_weight=weights[j],mean_absorption_time=float(exact[0,j]),
            accumulated_isolated_time=float(exact[1,j]),accumulated_transport_time=float(exact[0,j]-exact[1,j]),
            survival_200=float(survival[100,j]),survival_400=float(survival[200,j]),
            remaining_mean_after_400=float(tail[0,j]),quadrature_error=float(integration_error[0,j])) for j,mask in enumerate(MASKS)]
        np.savez(output/(label+'_release.npz'),time=grid,masks=MASKS,survival=survival,isolated=isolated)
        result.append(dict(model=label,source=meta,rows=rows,certificate=certificate,
            maximum_survival_increase=monotonic,final_min_eigenvalue=final_min,
            elapsed_seconds=time.monotonic()-start,grid=dict(start=0.,stop=400.,step=2.,points=201)))
    return dict(models=result,source_states_read=2,initial_states=8,source_pump_rate=0.,original_source_pump_rate=.5,
        definition='tau=integral_0^infinity Tr(rho_one(t)) dt; source_0 removed, all other channels unchanged. '
            'Accumulated isolation time includes repeated entries; it is not first-exit time or original driven-NESS residence time.',
        estimator='Solve A^dagger T=-I on the 81-dimensional one-excitation Hilbert sector; no finite-horizon truncation.',
        survival_semantics='Probability the prepared single excitation has not yet reached sink_2; no new excitation is injected.')
