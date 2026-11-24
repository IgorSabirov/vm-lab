"""External arithmetic syntax and replayable proof certificates for Robinson Q.

Bound variables use de Bruijn indices. D and P are reserved meta-template
symbols; the first-order Q proof checker rejects them.
"""
from itertools import product
from fibonacci import nat, read_nat, encode, decode

K = 16
# symbol: (tag, result sort, argument sorts); v carries a natural index instead.
SIG = {'z':(0,'t',''), 'v':(1,'t',''), 's':(2,'t','t'), '+':(3,'t','tt'),
       '*':(4,'t','tt'), '=':(5,'f','tt'), 'bot':(6,'f',''), '>':(7,'f','ff'),
       'all':(8,'f','f'), 'D':(9,'t','t'), 'P':(10,'f','tt')}
BY_TAG = {spec[0]:sym for sym,spec in SIG.items()}
Z, BOT = ('z',), ('bot',)


def var(i): return ('v',i)
def eq(a,b): return ('=',a,b)
def imp(a,b): return ('>',a,b)
def neg(x): return imp(x,BOT)
def all_(x): return ('all',x)
def succ(x): return ('s',x)


def tokens(x):
    sym = x[0]
    head = (SIG[sym][0],)
    if sym == 'v':
        return head + nat(x[1])
    return head + sum((tokens(a) for a in x[1:]), ())


def parse(w,i,sort,meta=False):
    if i >= len(w) or w[i] not in BY_TAG:
        raise ValueError('unknown symbol')
    sym = BY_TAG[w[i]]
    _, result, args = SIG[sym]
    if result != sort or (not meta and sym in ('D','P')):
        raise ValueError('wrong sort or undefined symbol')
    i += 1
    if sym == 'v':
        j,i = read_nat(w,i)
        return var(j),i
    items = [sym]
    for a in args:
        child,i = parse(w,i,a,meta)
        items.append(child)
    return tuple(items),i


def code(x): return encode(tokens(x),K)


def formula(n, meta=False):
    w = decode(n,K)
    f,i = parse(w,0,'f',meta)
    if i != len(w):
        raise ValueError('trailing symbols')
    return f


def lift(x, levels, cutoff=0):
    if x[0]=='v':
        return var(x[1]+levels) if x[1]>=cutoff else x
    deeper = cutoff+int(x[0]=='all')
    return (x[0],)+tuple(lift(a,levels,deeper) for a in x[1:])


def subst(x,t,depth=0):
    """Remove variable slot 0, substituting t and avoiding capture."""
    if x[0]=='v':
        i = x[1]
        if i == depth:
            return lift(t,depth)
        return var(i-1) if i>depth else x
    deeper = depth+int(x[0]=='all')
    return (x[0],)+tuple(subst(a,t,deeper) for a in x[1:])


def numeral(n):
    two = succ(succ(Z))
    t = Z
    for bit in bin(n)[2:]:
        t = ('*',two,t)
        if bit=='1':
            t = succ(t)
    return t


def diag(b,meta=False):
    return code(subst(formula(b,meta),numeral(b)))


def substitution_register(form,t,aux):
    return aux ^ code(subst(formula(form),t))


x,y = var(0),var(1)
AX = (
    all_(neg(eq(succ(x),Z))),
    all_(all_(imp(eq(succ(y),succ(x)),eq(y,x)))),
    all_(imp(neg(eq(x,Z)),neg(all_(neg(eq(y,succ(x))))))),
    all_(eq(('+',x,Z),x)),
    all_(all_(eq(('+',y,succ(x)),succ(('+',y,x))))),
    all_(eq(('*',x,Z),Z)),
    all_(all_(eq(('*',y,succ(x)),('+',('*',y,x),y)))),
)


def propositional(f):
    atoms = set()
    def collect(a):
        if a[0]=='>':
            collect(a[1])
            collect(a[2])
        elif a != BOT:
            atoms.add(a)
    collect(f)
    def value(a,env):
        if a == BOT: return False
        if a[0] == '>': return not value(a[1],env) or value(a[2],env)
        return env[a]
    return all(value(f,dict(zip(atoms,b))) for b in product((False,True),repeat=len(atoms)))


# Each record is a conclusion, a rule tag and the rule's typed witnesses.
RULES = ('Q','taut','refl','eqsub','inst','dist','mp','gen')
ARGS = ('','','','ftt','t','','ii','i')


def proof_code(lines):
    w = list(nat(len(lines)))
    for f,rule,args in lines:
        j = RULES.index(rule)
        if len(args) != len(ARGS[j]):
            raise ValueError('bad certificate arity')
        w.extend(tokens(f)+(j,))
        for sort,arg in zip(ARGS[j],args):
            w.extend(nat(arg) if sort=='i' else tokens(arg))
    return encode(w,K)


def proof(p,n):
    """Decidable Proof_Q(p,n). Prov_Q(n) is its unbounded existential closure."""
    try:
        w = decode(p,K)
        nlines,i = read_nat(w,0)
        prior = []
        for _ in range(nlines):
            f,i = parse(w,i,'f')
            j,i = w[i],i+1
            args = []
            for sort in ARGS[j]:
                a,i = read_nat(w,i) if sort=='i' else parse(w,i,sort)
                if sort=='i' and a>=len(prior): return False
                args.append(a)
            rule = RULES[j]
            if rule=='Q': ok = f in AX
            if rule=='taut': ok = propositional(f)
            if rule=='refl': ok = f[0]=='=' and f[1]==f[2]
            if rule=='eqsub':
                body,t,u = args
                ok = f==imp(eq(t,u),imp(subst(body,t),subst(body,u)))
            if rule=='inst':
                ok = f[0]=='>' and f[1][0]=='all' and f[2]==subst(f[1][1],args[0])
            if rule=='dist':
                ok = (f[0]=='>' and f[1][0]=='all' and f[2][0]=='>' and f[2][2][0]=='all'
                      and f[1][1]==imp(lift(f[2][1],1),f[2][2][1]))
            if rule=='mp': ok = prior[args[1]]==imp(prior[args[0]],f)
            if rule=='gen': ok = f==all_(prior[args[0]])
            if not ok: return False
            prior.append(f)
        return i==len(w) and bool(prior) and code(prior[-1])==n
    except (IndexError,ValueError):
        return False


def named_string(w):
    """A1-safe list of distinct atom occurrences, built by joins in the name algebra.
    Positions are encoded in the atom identifiers; the last token is a terminator.
    """
    import names as N
    tree = N.atom(32*len(w)+31)
    for i in reversed(range(len(w))):
        if not 0 <= w[i] < K:
            raise ValueError('invalid logical token')
        tree = N.join(N.atom(32*i+w[i]),tree)
    return tree


def read_named_string(tree):
    import names as N
    w = []
    while True:
        tag,args = N.children(tree)
        if tag == -1 and args[0] == 32*len(w)+31:
            return tuple(w)
        if tag != 5:
            raise ValueError('invalid syntax list')
        left,tree = args
        head, payload = N.children(left)
        if head != -1:
            raise ValueError('expected a token atom')
        pos, token = divmod(payload[0],32)
        if pos != len(w) or token >= K:
            raise ValueError('incorrect occurrence label')
        w.append(token)
