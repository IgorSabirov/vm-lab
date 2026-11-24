"""Run from any directory. Emit a deterministic JSON record to stdout."""
import hashlib
from collections import Counter
from fractions import Fraction
from itertools import product, permutations
import json
from pathlib import Path
import sys

from fibonacci import encode, decode, concat, fib_pair, shift
import names as N
import logic as G
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
import r130_reference as ref

def check(condition):
    if not condition: raise AssertionError('audit failed')


def rejected(fn,*args):
    try: fn(*args)
    except ValueError: return True
    raise AssertionError('invalid input accepted')


def words(k,m):
    return [v for j in range(m+1) for v in product(range(k),repeat=j)]


def word_audit():
    rows = []
    for k in range(1,7):
        ws = words(k,5)
        pairs = words(k,3)
        for w in ws:
            a = encode(w,k)
            check(decode(a,k)==w)
        for u,v in product(pairs,repeat=2):
            a,b = encode(u,k),encode(v,k)
            s = (k+1)*len(u)
            f,g = fib_pair(s)
            check(concat(a,b,k)==encode(u+v,k)==a+(g-f)*b+f*shift(b,1))
        rows.append([k,len(ws),len(pairs)**2])
    rejected(decode,3,2)
    rejected(decode,fib_pair(5)[0],2)
    golden = [sum(all(not (a and b) for a,b in zip(w,w[1:]))
                  for w in product((0,1),repeat=n)) for n in range(15)]
    check(golden==[fib_pair(n+2)[0] for n in range(15)])
    return dict(alphabets_words_pairs=rows,golden_prefix_counts=golden)


def name_tokens(u):
    if u[0]=='atom': return decode(N.atom(u[1]),N.K)
    tag = {'l':3,'r':4,'v':5}[u[0]]
    return (tag,)+sum((name_tokens(a) for a in u[1:]),())


def from_ref(x,channels):
    return N.ring_code([(encode(name_tokens(u),N.K),s) for u,s in x],channels)


def local_steps():
    counts = {}
    for c,k,m,eps in [(1,4,4,(1,)),(2,16,3,(1,-1))]:
        count = 0
        for length in range(1,m+1):
            for w in product(range(k),repeat=length):
                x = ref.named(w)
                a = from_ref(x,c)
                b = N.step(a,c)
                d = N.step(a,c,True)
                check(b==from_ref(ref.forward(x,eps),c))
                check(d==from_ref(ref.backward(x,eps),c))
                check(N.step(b,c,True)==N.step(d,c)==a)
                count += 1
        counts['C'+str(c)] = count
    return counts


def graphs():
    a,b,c = (N.atom(i) for i in (0,17,100003))
    x,y = N.project(a,0),N.project(a,1)
    vs = [(x,17),(y,7),(N.join(b,c),100)]
    nd = vs[2][0]
    es = [((x,5),(x,8)),((x,2),(y,0)),((x,7),(y,1))]
    canon = N.graph_code(vs,es)
    check(N.graph_code(*N.read_graph(canon))==canon)
    check(N.read_graph(N.graph_code([],[]))==([],[]))
    variants = 0
    for order in permutations(vs):
        for edges in permutations(es):
            for flips in product((0,1),repeat=len(es)):
                e = [edge[::-1] if flip else edge for edge,flip in zip(edges,flips)]
                check(N.graph_code(order,e)==canon)
                variants += 1
    rejected(N.graph_code,vs+[(a,1)],es)
    rejected(N.graph_code,vs,es+[((x,2),(nd,1))])
    rejected(N.graph_code,vs,[((b,0),(nd,0))])
    duplicate_leaf = N.join(x,x)
    general = N.graph_code([(duplicate_leaf,0)],[])
    check(N.graph_code(*N.read_graph(general))==general)
    rejected(N.ring_code,[(duplicate_leaf,0)])
    rejected(N.graph_code,[(duplicate_leaf,0),(x,0)],[])

    check(N.join(x,y)==a and N.project(nd,0)==b and N.project(nd,1)==c)
    rejected(N.graph_to_ring,canon)
    separate=N.graph_code([(a,0),(b,1)],[((a,0),(a,1)),((b,0),(b,1))])
    rejected(N.graph_to_ring,separate)
    complete=0
    for ch,states in ((1,(1,2,3)),(2,(1,2,12))):
        f=N.ring_code(list(zip((a,b,c),states)),ch)
        for _ in range(4):
            h=N.ring_to_graph(f,ch)
            check(N.graph_to_ring(h,ch)==f)
            y=N.step(N.graph_to_ring(h,ch),ch)
            check(N.ring_to_graph(N.step(y,ch,True),ch)==h)
            f=y
            complete+=1
    return dict(order_and_endpoint_variants=variants,general_graph_ring_edges_checked=complete,
                nonring_topologies_rejected=2,invalid_graphs_rejected=4,internal_overlap_rejected_by_ring=True,
                cases=['empty','isolated vertex','loop','parallel edges','large atom and port ids'])


def rename(u, mapping):
    if u[0]=='atom': return mapping.get(u[1],u)
    if u[0]=='v': return ref.join(rename(u[1],mapping),rename(u[2],mapping))
    return (ref.left if u[0]=='l' else ref.right)(rename(u[1],mapping))


def active():
    eps = (1,-1)
    x = ref.named((1,2,12))
    seed = x
    def basis(ring):
        by_state={s:u for u,s in ring}
        return {i:by_state[s] for i,(_,s) in enumerate(seed)}
    mapping = basis(ref.forward(seed,eps))
    inverse = basis(ref.backward(seed,eps))
    for i in range(3):
        check(rename(mapping[i],inverse)==rename(inverse[i],mapping)==('atom',i))
    metrics = {}
    paths = {}
    def measure(u):
        if id(u) not in metrics:
            children = [] if u[0]=='atom' else [measure(v) for v in u[1:]]
            metrics[id(u)] = (u,1+sum(a for a,b in children),1+max((b for a,b in children),default=-1))
        return metrics[id(u)][1:]
    def address(u):
        if id(u) not in paths:
            if u[0]=='atom': a,p,d = u[1],0,0
            else:
                a,p,d = address(u[1])
                p,d = 2*p+int(u[0]=='r'),d+1
            paths[id(u)] = (u,a,p,d)
        return paths[id(u)][1:]
    def partition(ring):
        buckets = [[],[],[]]
        stack = [u for u,s in ring]
        while stack:
            u=stack.pop()
            if u[0]=='v': stack.extend(u[1:])
            else:
                a,p,d=address(u)
                buckets[a].append((p,d))
        for entries in buckets:
            h=max(d for _,d in entries)
            end=0
            for p,q in sorted((p<<(h-d),(p+1)<<(h-d)) for p,d in entries):
                check(p==end)
                end=q
            check(end==1<<h)
    samples, digits = [], []
    for t in range(501):
        sizes={s:measure(u)[0] for u,s in x}
        depth=max(measure(u)[1] for u,s in x)
        total=sum(sizes.values())+3
        expected=1+t*(t+7)//2
        check(sizes=={1:expected,2:expected,12:2*t+5 if t else 1})
        check(depth==(t+2 if t else 0) and total==(t*t+9*t+10 if t else 6))
        check(ref.cyclic(ref.word(x))==(1,2,12))
        partition(x)
        if t<=30:
            n=from_ref(x,2)
            digits.append(len(str(n)))
            check(N.ring_code(N.read_ring(n))==n)
            if t<30:
                y=ref.forward(x,eps)
                check(N.step(n)==from_ref(y,2) and N.step(from_ref(y,2),inverse=True)==n)
        if t<=10:
            y=ref.forward(x,eps)
            check(ref.equal(tuple((rename(u,mapping),s) for u,s in x),y))
        if t in (0,1,2,3,10,30,100,500):
            samples.append(dict(t=t,sizes_1_2_12=[sizes[s] for s in (1,2,12)],depth=depth,tokens=total))
        x=ref.forward(x,eps)
    check(digits[-1]==5671)
    return dict(samples=samples,digits_0_to_30=digits,A1_complete_partitions=501,
                exact_two_sided_code_edges=30,renaming_inverse_on_generators=True)


def closed_sector():
    # Atomic and half-step sheets. For C2 select only a1 and b2; I acts identically.
    length=5
    initial = {}
    for w in product((0,1,8,9),repeat=length):
        x=ref.named(w)
        y=ref.forward(x,(1,-1))
        for z in (x,y):
            key=ref.canonical(z)
            successor=ref.canonical(ref.forward(z,(1,-1)))
            check(key not in initial)
            initial[key]=successor
        actual={u[1]:s for u,s in ref.forward(y,(1,-1))}
        check(all(actual[i]==((w[(i+1)%length]&1)|(w[(i-1)%length]&8))
                  for i in range(length)))
    seen=set()
    cycles=Counter()
    for start in initial:
        if start in seen: continue
        p=0
        cursor=start
        while cursor not in seen:
            seen.add(cursor)
            cursor=initial[cursor]
            p+=1
        check(cursor==start)
        cycles[p]+=1
    check(cycles=={2:4,10:204})
    # One-head read-only machine on a finite unary tape, unit F^2.
    for i in range(length):
        w=tuple(int(j==i) for j in range(length))
        x=ref.named(w)
        def machine(delta):
            return ref.named(tuple(int(j==(i+delta)%length) for j in range(length)))
        for fun,delta in ((ref.forward,-1),(ref.backward,1)):
            check(ref.equal(fun(fun(x,(1,-1)),(1,-1)),machine(delta)))
    # Direct encoding of an additional write in b2 starting from a blank tape.
    x=ref.named((1,0,0,0,0))
    attempted=ref.named((8,0,0,0,1))
    check(not ref.equal(ref.forward(ref.forward(x,(1,-1)),(1,-1)),attempted))
    return dict(length=length,states=len(initial),primitive_cycles=dict(cycles),
                fixed_powers_1_to_10=[sum(p*c for p,c in cycles.items() if k%p==0) for k in range(1,11)],
                unary_head_inverse_checks=2*length,direct_bit_write_rejected=True)


def det(a):
    """Exact Gaussian elimination."""
    a=[list(map(Fraction,row)) for row in a]
    result=Fraction(1)
    for j in range(len(a)):
        pivot=next((i for i in range(j,len(a)) if a[i][j]),None)
        if pivot is None: return 0
        if pivot!=j:
            a[pivot],a[j]=a[j],a[pivot]
            result=-result
        d=a[j][j]
        result*=d
        for i in range(j+1,len(a)):
            scale=a[i][j]/d
            for k in range(j,len(a)):
                a[i][k]-=scale*a[j][k]
    return result


def observations():
    out={}
    matrices=[]
    for w in ('010111','011011'):
        n=len(w)
        avg=[[0]*n for _ in w]
        source_det=None
        for rotation in range(n):
            bits=list(map(int,w[rotation:]+w[:rotation]))
            b=[[bits[i]*bits[j]*(int(i==(j+1)%n)-int(i==j)) for j in range(n)] for i in range(n)]
            gram=[[sum(x*y for x,y in zip(row,col)) for col in b] for row in b]
            if rotation==0:
                source_det=det([[int(i==j)+gram[i][j] for j in range(n)] for i in range(n)])
            for i,j in product(range(n),repeat=2):
                avg[i][j]+=Fraction(gram[i][j],n)
        matrices.append(avg)
        check(source_det==(26 if w=='010111' else 25))
        x=ref.named(tuple(1+int(i) for i in w))
        trace=[]
        for t in range(5):
            trace.append(dict(length=len(x),cyclic_word=ref.cyclic(ref.word(x))))
            x=ref.forward(x)
        out[w]=trace
    check([out[w][-1]['length'] for w in out]==[9,10])
    check(matrices[0]==matrices[1])
    val=det([[int(i==j)+matrices[0][i][j] for j in range(n)] for i in range(n)])
    check(val==Fraction(39200,729))
    return dict(traces=out,mean_matrices_equal=True,det_after_mean=str(val))


def logic_audit():
    x,y,z=G.var(0),G.var(1),G.Z
    body=G.eq(x,x)
    f=G.all_(G.eq(x,y))
    check(G.subst(f,x)==f and G.subst(f,z)==G.all_(G.eq(x,z)))
    a=G.code(f)
    for m in (0,1,17,65537):
        check(G.substitution_register(a,z,G.substitution_register(a,z,m))==m)
    check(G.formula(G.diag(G.code(body)))==G.eq(G.numeral(G.code(body)),G.numeral(G.code(body))))
    # G_Q schema in a conservative arithmetic notation: P=Proof_Q; D=diag.
    template=G.all_(G.neg(('P',x,('D',y))))
    b=G.code(template)
    g=G.diag(b,True)
    check(G.formula(g,True)==G.all_(G.neg(('P',x,('D',G.numeral(b))))))
    rejected(G.formula,g)
    zero=G.eq(z,z)
    u=G.all_(body)
    instance=G.imp(u,zero)
    lines=[(body,'refl',()),(u,'gen',(0,)),(instance,'inst',(z,)),(zero,'mp',(1,2))]
    p=G.proof_code(lines)
    for number in (p,G.code(f),G.code(G.subst(f,z))):
        w=decode(number,G.K)
        tree=G.named_string(w)
        N.check_names([tree])
        check(G.read_named_string(tree)==w)
    check(G.proof(p,G.code(zero)))
    for ax in G.AX: check(G.proof(G.proof_code([(ax,'Q',())]),G.code(ax)))
    for form,rule,args in ((G.imp(zero,zero),'taut',()),
        (G.imp(G.eq(x,z),G.imp(body,zero)),'eqsub',(body,x,z)),
        (G.imp(G.all_(G.imp(G.lift(body,1),body)),G.imp(body,u)),'dist',())):
        check(G.proof(G.proof_code([(form,rule,args)]),G.code(form)))
    wrong=G.proof_code([*lines[:3],(zero,'mp',(2,1))])
    check(not G.proof(wrong,G.code(zero)) and not G.proof(p,G.code(G.BOT)) and not G.proof(0,G.code(zero)))
    return dict(theory='Robinson Q',axioms_checked=len(G.AX),rules_exercised=list(G.RULES),
                proof_lines=len(lines),named_syntax_roundtrips=3,proof_code_decimal=str(p),conclusion_code=G.code(zero),
                rejected_certificates=3,template_code=str(b),diagonal_code_bits=g.bit_length(),
                diagonal_code_sha256=hashlib.sha256(g.to_bytes((g.bit_length()+7)//8,'big')).hexdigest(),
                internal_ADD_diagonalization='open',expanded_base_language_fixed_point='not materialized')


def main():
    sys.setrecursionlimit(10000)
    if hasattr(sys,'set_int_max_str_digits'): sys.set_int_max_str_digits(0)
    return dict(word_arithmetic=word_audit(),graphs=graphs(),ring_conjugacy=local_steps(),
                active_C2=active(),closed_sector=closed_sector(),R141_preparation=observations(),
                external_syntax=logic_audit())


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False,indent=2))
