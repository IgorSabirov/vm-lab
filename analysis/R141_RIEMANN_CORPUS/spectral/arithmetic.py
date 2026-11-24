"""Numerical donor controls. python-flint 0.9.0 (Arb), SymPy for the prime list."""
import json
from flint import acb, arb, ctx
from sympy import primerange


def gaussian(a, gammas):
    """Guinand–Weil with h(t)=exp(-a t²), both signs, angular Fourier variable."""
    pi = arb.pi()
    log_pi = pi.log()
    pole = 2 * (a / 4).exp()
    zero_sum = 2 * sum((-a * g**2).exp() for g in gammas[:100])
    prime_sum = arb(0)
    for p in primerange(2, 20001):
        log_p = arb(int(p)).log()
        for m in range(1, 15):
            u = m * log_p
            prime_sum += log_p * (-u/2 - u**2/(4*a)).exp()
    prime_sum /= (pi*a).sqrt()

    # Re is applied after integration so that Arb integrates a meromorphic function.
    T = int((arb(160)/a).sqrt().upper().ceil().unique_fmpz()) + 1
    def integrand(t, analytic):
        return (-a*t*t).exp() * ((arb(1)/4 + acb(0, 1)*t/2).digamma() - log_pi)
    arch = acb.integral(integrand, 0, T).real / pi
    decay = (-a*T*T).exp()
    i0 = decay/(2*a*T)
    i2 = (T*decay+i0)/(2*a)
    arch_tail = (6*i0 + 17*i2)/pi
    arch += arb(0, arch_tail.upper())

    # Every omitted prime power exceeds 20000. Integral test on all integers.
    L = arb(20000).log()
    slope = L/(2*a) - arb(1)/2
    prime_tail = (L/2 - L**2/(4*a)).exp() * (L/slope + 1/slope**2)/(pi*a).sqrt()
    g = gammas[99]
    C = 1 + (arb.const_euler() - (4*pi).log())/2
    zero_tail = 2*C*(g**2 + arb(1)/4)*(-a*g**2).exp()
    residual = zero_sum - (pole + arch - prime_sum)
    assert residual.abs_upper() < prime_tail + zero_tail + arb('1e-40')
    if a < 1:
        assert residual.abs_upper() < arb('1e-30') and prime_tail + zero_tail < arb('1e-30')
    else:
        assert residual < 0
    return {k: v.str(11) for k, v in dict(zero_sum=zero_sum, poles=pole, arch=arch,
            prime_powers=prime_sum, signed_residual=residual, prime_tail_bound=prime_tail,
            zero_tail_bound=zero_tail, arch_tail_bound=arch_tail).items()}


def xi(s):
    return s*(s-1)/2 * (-s*arb.pi().log()/2).exp() * (s/2).gamma() * s.zeta()


def product_check(gammas):
    half = arb(1)/2
    ratio = xi(acb(half, 1)) / xi(acb(half))
    assert ratio.imag.contains(0)
    target = ratio.real
    partial = arb(1)
    rows, crossings = {}, {}
    for n, g in enumerate(gammas, 1):
        partial *= 1 - 1/g**2
        absolute = partial-target
        relative = absolute/target
        for name, err in [('absolute', absolute), ('relative', relative)]:
            if name not in crossings:
                if err < arb('0.001'):
                    crossings[name] = n
                else:
                    assert err > arb('0.001')
        errors = [absolute.str(13), relative.str(13)]
        if n in (10, 30, 100, 650) or n in crossings.values():
            rows[n] = errors
        if n in crossings.values():
            rows[n-1] = previous
        previous = errors
    assert len(crossings)==2
    return dict(z=1, target=target.str(20), threshold="0.001", first_below=crossings,
                error_columns=["absolute","relative"], errors=rows)


def main():
    # High precision for cancellation in the explicit formula; 96 bits suffice for the product.
    ctx.prec = 192
    zeros = [z.imag for z in acb.zeta_zeros(1, 100)]
    gaussian_checks = {s: gaussian(arb(s), zeros) for s in ['0.01','0.1','1']}
    ctx.prec = 96
    g = zeros + [z.imag for z in acb.zeta_zeros(101, 550)]
    print(json.dumps(dict(gaussian=gaussian_checks, product=product_check(g)), indent=2))


if __name__ == '__main__':
    main()
