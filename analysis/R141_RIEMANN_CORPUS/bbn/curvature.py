"""Second-order abundance response from the archived trajectory and a temperature covariance."""
import numpy as np
from scipy.linalg import expm, svd

from replay import ensemble_covariance, thermal
from response import trajectory_grid


def quadratic_terms(network):
    """For quadratic mass-action fluxes, tabulate stoichiometry times its symmetry factor."""
    directions, pairs, columns = [], [], []
    for i in range(network.n_rx):
        change = np.zeros(network.n_sp)
        n = network.af_len[i]
        change[network.af_idx[i,:n]] = network.af_co[i,:n]
        for direction, (idx, powers, sizes, invsym) in enumerate((
                (network.ri_idx, network.ri_pow, network.ri_len, network.invsr),
                (network.pi_idx, network.pi_pow, network.pi_len, network.invsp))):
            n = sizes[i]
            indices = np.repeat(idx[i,:n], powers[i,:n])
            assert len(indices) <= 2
            if len(indices) == 2:
                directions.append(2*i+direction)
                pairs.append(indices)
                columns.append((1-2*direction)*invsym[i]*change)
    return np.array(directions), np.array(pairs).T, np.array(columns).T


def second_order(primat, folder, subdivisions, pad=32768):
    t9, ys, density, rates, steps, final, kernel, channels, _ = trajectory_grid(
        primat, folder, subdivisions, 2.)
    _, w = thermal(t9, np.arange(2.25, 2000, .5))
    u, s, vt = svd(w, full_matrices=False)
    keep = s > 1e-9 * s[0]
    basis = u[:,keep]*s[keep]
    ens = ('GOE','GUE','Poisson')
    loadings = []
    for law in ens:
        # Right singular vectors are orthonormal, so white covariance is spacing*dE*I.
        cov = 5*np.eye(keep.sum()) if law == 'Poisson' else ensemble_covariance(vt[keep], .5, 10., law, pad)
        eig, rot = np.linalg.eigh(cov)
        assert eig.min() > -1e-12
        loadings.append(basis @ (rot * np.sqrt(np.maximum(eig,0))))
    m = np.stack(loadings)
    n, rank = len(final), int(keep.sum())
    tangent = np.zeros((len(ens),n,rank))
    mean2 = np.zeros((len(ens),n))
    directions,(left,right),stoich = quadratic_terms(kernel._c)
    for k,dt in enumerate(steps):
        y,rho,r = ys[k],density[k],rates[k]
        if k in (0, len(steps)//2, len(steps)-1):
            direction = np.linspace(.2, .9, n)
            pair_flux = rho * r[directions] * direction[left] * direction[right]
            finite = (kernel.rhs(y+direction,rho,r) + kernel.rhs(y-direction,rho,r))/2 - kernel.rhs(y,rho,r)
            np.testing.assert_allclose(stoich @ pair_flux, finite, rtol=1e-9, atol=1e-9)
        jac = kernel.jacobian(y,rho,r)
        direct = np.zeros_like(r)
        col = 2+2*channels[0]
        direct[col:col+2] = r[col:col+2]
        force = kernel.rhs(y,rho,direct)
        jrate = kernel.jacobian(y,rho,direct)
        # exp on a half interval delivers both homogeneous propagation and the
        # integral of its propagator, even with singular Jacobians.
        block = np.zeros((2*n,2*n))
        block[:n,:n],block[:n,n:] = jac,np.eye(n)
        step = expm(block*(dt/2))
        prop,integ = step[:n,:n],step[:n,n:]
        fstep = (integ@force)[None,:,None]*m[:,k,None,:]
        mid = prop@tangent + fstep
        contracted = (mid[:,left,:]*mid[:,right,:]).sum(axis=-1)
        quad = ((rho*r[directions])*contracted) @ stoich.T
        mixed = (mid*m[:,k,None,:]).sum(axis=-1) @ jrate.T
        mean2 = mean2 @ (prop@prop).T + (quad+mixed) @ ((np.eye(n)+prop)@integ).T
        tangent = prop@mid + fstep
    rel_h,rel_d = tangent[:,1,:]/final[1],tangent[:,2,:]/final[2]
    fractional_mean = mean2[:,2]/final[2]-mean2[:,1]/final[1]+np.sum(rel_h*(rel_h-rel_d),axis=1)
    helium_mean = mean2[:,5]/final[5]
    sd = np.column_stack((np.linalg.norm(rel_d-rel_h,axis=1),np.linalg.norm(tangent[:,5,:]/final[5],axis=1)))
    return dict(retained_modes=rank, discarded_relative_energy=float((s[~keep]**2).sum()/(s*s).sum()),
                mean_fractional_coefficient={law:[fractional_mean[i],helium_mean[i]] for i,law in enumerate(ens)},
                sd_fractional_coefficient={law:sd[i].tolist() for i,law in enumerate(ens)})
