"""Block numbers for finite words. Positions start with F_2=1."""
from functools import lru_cache


@lru_cache(maxsize=4096)
def fib_pair(n):
    """(F_n,F_{n+1}) by doubling."""
    if n == 0:
        return 0, 1
    a, b = fib_pair(n // 2)
    c, d = a * (2*b-a), a*a+b*b
    return (d, c+d) if n % 2 else (c, d)


def encode(word, k):
    if k < 1:
        raise ValueError('empty alphabet')
    # Horner on the pair (sum F_e, sum F_{e+1}); one matrix jump per symbol.
    p, q = fib_pair(k+1)
    a = b = 0
    for c in reversed(word):
        if type(c) is not int or not 0 <= c < k:
            raise ValueError('out-of-alphabet symbol')
        f, g = fib_pair(2+c)
        a, b = (q-p)*a+p*b+f, p*a+q*b+g
    return a


@lru_cache(maxsize=4096)
def support(n):
    if type(n) is not int or n < 0:
        raise ValueError('not a natural number')
    if n == 0:
        return ()
    lo, hi = 2, 2*n.bit_length()+3
    while lo+1 < hi:
        mid = (lo+hi)//2
        if fib_pair(mid)[0] <= n:
            lo = mid
        else:
            hi = mid
    e = lo
    f, g = fib_pair(e)
    indices = []
    while n:
        if f <= n:
            indices.append(e)
            n -= f
        e, f, g = e-1, g-f, f
    return tuple(reversed(indices))


@lru_cache(maxsize=4096)
def decode(n, k):
    if k < 1:
        raise ValueError('empty alphabet')
    word = []
    for e in support(n):
        i, c = divmod(e-2, k+1)
        if i != len(word) or c == k:
            raise ValueError('missing/repeated block or guard index')
        word.append(c)
    return tuple(word)


def shift(n, s):
    if s < 0:
        raise ValueError('negative shift')
    return sum(fib_pair(e+s)[0] for e in support(n))


def concat(a, b, k):
    m = len(decode(a, k))
    decode(b, k)
    return a + shift(b, (k+1)*m)


def nat(n):
    if type(n) is not int or n < 0:
        raise ValueError('invalid identifier')
    return tuple(map(int, bin(n)[2:])) + (2,)


def read_nat(tokens, i):
    start = i
    value = 0
    while i < len(tokens) and tokens[i] in (0, 1):
        value = 2*value + tokens[i]
        i += 1
    if i == start or i == len(tokens) or tokens[i] != 2 or (i-start > 1 and tokens[start] == 0):
        raise ValueError('invalid terminated binary integer')
    return value, i+1
