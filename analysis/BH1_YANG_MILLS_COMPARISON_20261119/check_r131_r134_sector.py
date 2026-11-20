"""Exact finite-ring controls and the energy budget of the published late-transfer case."""
from fractions import Fraction
from itertools import product
from math import factorial, pi

WORDS = ("111111221212222222112121", "111112111121222221222212")


def pattern(word, seq):
    return sum(all(word[(i+j) % len(word)] == label for j, label in enumerate(seq))
               for i in range(len(word)))


def lengths(word):
    n = len(word)
    x, y, z, v, w = [pattern(word, s) for s in ("12", "21", "212", "121", "2121")]
    return n, n-x, n-2*x+y+z+v-w


def moments(weights, order):
    """Trace powers from one row of the cyclic nearest-neighbour Laplacian at a time."""
    n = len(weights)
    traces = [0]*order
    for start in range(n):
        column = [int(i == start) for i in range(n)]
        for k in range(order):
            column = [(weights[i-1]+weights[i])*column[i] - weights[i-1]*column[i-1]
                      - weights[i]*column[(i+1) % n] for i in range(n)]
            traces[k] += column[start]
    return traces


def entropy_coefficient(n):
    # h(z) = log 2 + (1 - z d/dz) log cosh(z/2).
    c = [Fraction(1, 4**j * factorial(2*j)) for j in range(n+1)]
    a = [Fraction(0)]
    for k in range(1, n+1):
        a.append(c[k] - sum((j*a[j]*c[k-j] for j in range(1,k)), Fraction(0))/k)
    return (1-2*n)*a[n]


def main():
    assert [lengths(w) for w in WORDS] == [(24,19,23), (24,19,24)]
    # Equality at seven exact nodes proves the polynomial identity through degree six.
    for u in range(7):
        a, b = [moments([1 if t=="1" else u for t in w], 6) for w in WORDS]
        assert a[:5] == b[:5] and a[5]-b[5] == 6*(u-1)**4*(u+1)**2
        if u == 2:
            assert [a[5],b[5]] == [521066,521012]
    assert entropy_coefficient(6)>0
    print("Entropy difference coefficient at u=2, order 12:",108*entropy_coefficient(6))
    assert [lengths(w)[1] for w in ("120","102")] == [2,3]
    assert moments([2,3,5],6) == moments([2,5,3],6)
    triples = list(product(range(3),repeat=3))
    assert all((a[1],a[2],b[0]) in triples and (a[2],b[0],b[1]) in triples
               for a,b in product(triples, repeat=2))
    budget = .039999949024044065
    n_before_transfer_without_reservoir = 3.0447552200318295
    ratio = (7/8)*(4/11)**(4/3)*n_before_transfer_without_reservoir
    required = budget*(1+ratio)*pi**2/15
    print("Required radiation injection / T_gamma^4:", required)
    print("Fraction to photons:",1/(1+ratio))
    for h in (1.025,1.175):
        print("Latent heat / Tc^4, threshold T_X/T_gamma at efficiency 1:",h,(required/h)**.25)


if __name__ == "__main__":
    main()
