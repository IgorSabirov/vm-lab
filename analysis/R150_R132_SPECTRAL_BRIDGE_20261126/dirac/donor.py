"""Recover contact matrix units from words; test the corpus Floquet coin."""
import json
from pathlib import Path
import numpy as np


def position_word(n,t,u):
    sites = [0]*n
    for mask,pos in [(1,0),(2,t),(4,u),(8,(t+u-1)%n)]:
        sites[pos] |= mask
    return sites


def update(w):
    n = len(w)
    joins = {(1,2):3,(8,4):12}
    splits = {3:(1,2),12:(8,4)}
    out=[]
    hit=False
    for i,c in enumerate(w):
        if (w[i-1],c) in joins:
            continue
        pair = (c,w[(i+1)%n])
        if pair in joins:
            out.append(joins[pair])
            hit=True
        elif c in splits:
            out.extend(splits[c])
            hit=True
        else:
            out.append(c)
    return out,hit


def coords(w):
    pos = [next(i for i,s in enumerate(w) if s&bit) for bit in [1,2,4,8]]
    return ((pos[1]-pos[0])%len(w),(pos[2]-pos[0])%len(w),
            (pos[3]-pos[1])%len(w))


def main():
    tested=0
    layers=0
    for L in range(3,32,2):
        for u in range(2,L):
            I=np.zeros((L,L),int)
            F=np.zeros_like(I)
            C=np.zeros_like(I)
            for t in range(L):
                w=position_word(L,t,u)
                mid,hit=update(w)
                end=[(mid[i]&10)|(mid[(i+1)%len(mid)]&5) for i in range(len(mid))]
                assert len(end)==L and coords(mid)[1:]==(u,u-1)==coords(end)[1:]
                I[coords(mid)[0],t]=1
                F[coords(end)[0],t]=1
                C[t,t]=hit
                tested+=1
            p=C@F@C
            v=C-p
            pp=np.zeros_like(F); pp[1,1]=1
            vv=np.zeros_like(F); vv[0,0]=1
            B=np.zeros_like(F); B[0,1]=B[1,0]=1
            assert np.array_equal(p,pp) and np.array_equal(v,vv)
            assert np.array_equal(C@I@C,B)
            assert np.array_equal(B@B,C)
            assert np.array_equal(I-np.eye(L,dtype=int)+C,B)
            assert np.array_equal(p@I@v,(pp@B@vv))
            assert np.array_equal(p@F,F@p)
            layers+=1
    coin=[]
    for n in [8,16,32,64,128,256]:
        L=n+1
        Q=np.roll(np.eye(L),1,axis=0)
        I=np.eye(L); I[[0,1]]=I[[1,0]]
        F=Q@I
        Id=np.eye(L)
        e=np.eye(L)[:,1]
        cycle=(np.ones(L)-e)/np.sqrt(n)
        for exponent in [1.,.75]:
            delta=n**(-exponent)
            z=-np.exp(1j*delta)
            W=Q@((Id+I)/2+z*(Id-I)/2)
            dk=-n**2*((W-F)+(W-F).conj().T)
            dpp=float(np.vdot(e,dk@e).real)
            hg=np.vdot(e,dk@cycle)
            assert abs(dpp-2*n*n*np.sin(delta/2)**2)<3.e-10
            assert abs(hg+dpp/np.sqrt(n))<2.e-12
            coin.append({"N":n,"exponent":exponent,"port_shift":dpp,
                         "constant_mode_coupling":float(hg.real)})
    ans={"words":tested,"active_layers":layers,"lengths":list(range(3,32,2)),
         "word_identity_errors":0,"coin":coin}
    Path(__file__).with_name("donor.json").write_text(json.dumps(ans,indent=2)+"\n")
    print(json.dumps(ans,indent=2))


if __name__=='__main__':
    main()
