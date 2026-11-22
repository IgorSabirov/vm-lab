"""Exact binary-ring audit. Standard library only. Run with --verify to exhaust all sizes 3..24."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import json
from math import comb, prod
from pathlib import Path


def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a+b
    return a


def partitions(limit):
    counts = [[0]*(limit+1) for _ in range(limit+1)]
    counts[0][0] = 1
    for w in range(1,limit+1):
        for r in range(1,w+1):
            counts[w][r] = counts[w-1][r-1] + counts[w-r][r]
    return counts


def necklaces(n):
    """One binary necklace and its minimal period (number of labelled rotations)."""
    word = [0]*(n+1)
    def visit(pos, period):
        if pos>n:
            if n%period==0:
                yield ''.join(map(str,word[1:])),period
            return
        bit = word[pos-period]
        word[pos] = bit
        yield from visit(pos+1,period)
        if bit==0:
            word[pos] = 1
            yield from visit(pos+1,pos)
    yield from visit(1,1)


def bareiss(matrix):
    """Fraction-free elimination on positive definite matrices, so all leading pivots exist."""
    a = [row.copy() for row in matrix]
    previous = 1
    for k in range(len(a)-1):
        pivot = a[k][k]
        assert pivot>0
        for i in range(k+1,len(a)):
            for j in range(k+1,len(a)):
                a[i][j], remainder = divmod(pivot*a[i][j]-a[i][k]*a[k][j],previous)
                assert remainder==0
        previous = pivot
    return a[-1][-1]


def original_matrix(word):
    w = list(map(int,word))
    n = len(w)
    b = [[w[i]*(int((i+1)%n==j)-int(i==j))*w[j] for j in range(n)] for i in range(n)]
    return [[int(i==j)+sum(x*y for x,y in zip(b[i],b[j])) for j in range(n)] for i in range(n)]


def class_metrics(n, counts):
    cells = {(w,r):counts[w][r] for w in range(1,n) for r in range(1,min(w,n-w)+1)}
    maximum = max(cells.values())
    multiple = [key for key,v in cells.items() if v>1]
    weights = {(w,r):n*comb(w-1,r-1)*comb(n-w-1,r-1)//r for w,r in cells}
    mixed = 2**n-2
    ambiguous = sum(weights[key] for key in multiple)
    assert sum(weights.values())==mixed
    assert len(cells)==n*n//4 and len(multiple)==(n-4)**2//4
    if n>=4:
        lucas = fibonacci(n-1)+fibonacci(n+1)
        assert mixed-ambiguous==lucas-1+n*fibonacci(n-2)+n*(n-3)
    assert maximum==max(counts[n-r][r] for r in range(1,n//2+1))
    return dict(classes=len(cells),ambiguous_classes=len(multiple),max_distinct=maximum,
                maximum_at_W_r=[list(k) for k,v in cells.items() if v==maximum],
                labelled_ambiguous=ambiguous,labelled_mixed=mixed)


def enumerate_ring(n, counts):
    # Integer leading minors from the two ends of the path block independently of Fibonacci.
    d = [1,2]
    for length in range(2,n):
        d.append(3*d[-1]-d[-2])
    by_class=defaultdict(set)
    weights=Counter()
    dense=0
    representatives=0
    for word,period in necklaces(n):
        if '0' not in word or '1' not in word:
            continue
        pivot=word.index('0')
        runs=[len(x) for x in (word[pivot:]+word[:pivot]).split('0') if x]
        key=(sum(runs),len(runs))
        det=prod(d[length] for length in runs)
        if n<=11 or representatives%100003==0 or word=='0'+'1'*(n-1):
            assert det==bareiss(original_matrix(word))
            dense+=1
        by_class[key].add(det)
        weights[key]+=period
        representatives+=1
    for (w,r),values in by_class.items():
        assert len(values)==counts[w][r]
        assert weights[w,r]*r==n*comb(w-1,r-1)*comb(n-w-1,r-1)
    assert sum(weights.values())==2**n-2
    assert len(by_class)==n*n//4
    assert all(d[l]==fibonacci(2*l+1) for l in range(n))
    assert bareiss(original_matrix('0'*n))==1
    assert bareiss(original_matrix('1'*n))==fibonacci(2*n-1)+fibonacci(2*n+1)-2
    return dict(necklaces=representatives,mixed_words=sum(weights.values()),dense_mixed=dense,
                w11_r3_products=sorted(by_class[11,3]) if n==14 else None)


def orders():
    words=['010111','011011']
    results={}
    for w in words:
        matrices=[original_matrix(w[i:]+w[:i]) for i in range(len(w))]
        n=len(w)
        total=[[sum(row[j] for row in rows) for j in range(n)] for rows in zip(*matrices)]
        results[w]={'average_det':str(Fraction(sum(map(bareiss,matrices)),n)),
                    'det_average':str(Fraction(bareiss(total),n**n))}
    assert results[words[0]]['det_average']==results[words[1]]['det_average']
    assert [results[w]['average_det'] for w in words]==['26','25']
    return results


def report():
    counts=partitions(256)
    return dict(order_of_averaging=orders(),sizes={str(n):class_metrics(n,counts)
               for n in [*range(3,25),32,48,64,128,256]})


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--verify',action='store_true')
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    result=report()
    if a.verify:
        ref=Path(__file__).with_name('fibonacci.json')
        assert json.loads(ref.read_text())==result
        counts=partitions(24)
        result['exhaustive']={n:enumerate_ring(n,counts) for n in range(3,25)}
    output=json.dumps(result,indent=2)+'\n'
    if a.out:
        a.out.write_text(output)
    else:
        print(output,end='')


if __name__=='__main__':
    main()
