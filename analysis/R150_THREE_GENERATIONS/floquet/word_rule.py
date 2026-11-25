"""Port-word update transcribed from the supplied code; the verifier tags keys with length."""
def interact_word(x, eps=(1,-1)):
    split={3 << (2*c): ((1 << (2*c), 2 << (2*c)) if e==1 else (2 << (2*c),1 << (2*c))) for c,e in enumerate(eps)}
    merge={v:k for k,v in split.items()}
    n=len(x)
    starts={i for i in range(n) if n>1 and (x[i],x[(i+1)%n]) in merge}
    ends={(i+1)%n for i in starts}
    start=next(i for i in range(n) if i not in ends)
    out=[]; k=0
    while k<n:
        i=(start+k)%n; s=x[i]
        if i in starts:
            out.append(merge[(s,x[(i+1)%n])]); k+=2
        elif s in split:
            out.extend(split[s]); k+=1
        else:
            out.append(s); k+=1
    return tuple(out)

def transport_word(x, channels=2):
    a_mask=sum(1 << (2*c) for c in range(channels)); b_mask=2*a_mask
    return tuple((s & b_mask) | (x[(i+1)%len(x)] & a_mask) for i,s in enumerate(x))

def F_word(x): return transport_word(interact_word(x))
def I_word(x): return interact_word(x)
def R2_word(x): return tuple(((s&1)<<3)|((s&2)<<1)|((s&4)>>1)|((s&8)>>3) for s in x)
def transport_inverse_word(x, channels=2):
    a_mask=sum(1 << (2*c) for c in range(channels)); b_mask=2*a_mask
    return tuple((s & a_mask) | (x[(i+1)%len(x)] & b_mask) for i,s in enumerate(x))
def backward_word(x): return interact_word(transport_inverse_word(x))
def T_word(x): return interact_word(R2_word(x))

def state_to_word(key,L):
    x2,x3,x4=key; masks=[0]*L
    for pos,bit in [(0,1),(x2,2),(x3,4),(x4,8)]: masks[pos]|=bit
    return tuple(masks)
def word_to_state(word):
    L=len(word); positions={}
    for bit in (1,2,4,8):
        pos=[i for i,s in enumerate(word) if s&bit]
        if len(pos)!=1: return None
        positions[bit]=pos[0]
    p1=positions[1]
    return tuple((positions[b]-p1)%L for b in (2,4,8))
def canon_cycle(w): return min(tuple(w[i:]+w[:i]) for i in range(len(w)))
