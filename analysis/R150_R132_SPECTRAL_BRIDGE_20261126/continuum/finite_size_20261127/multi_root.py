"""Scalar fixed-mark ring+port: multiprecision multiple-root audit.
Run with python multi_root.py; requires mpmath. JSON stdout.
"""
import json
import mpmath as m
m.mp.dps=70
u,g,h=map(m.mpf,['2','1','.5'])
a=lambda E:g-h*h/(E+u)
def G(E):
    if E==0: return m.mpf(1)/4
    k=m.sqrt(E); return m.re(m.tan(k/2)/(2*k))
def GN(E,N):
    if E==0: return m.mpf(1)/4
    k=m.sqrt(E); return m.re(m.tan(N*m.asin(k/(2*N)))/(2*k*m.sqrt(1-E/(4*N*N))))
def C2(E):
    k=m.sqrt(E);return m.re(E/(96*m.cos(k/2)**2)+k*m.tan(k/2)/16)
def C4(E):
    k=m.sqrt(E);T=m.tan(k/2);S=1/m.cos(k/2)**2
    return m.re((m.mpf(3)/2560+m.mpf(1)/768)*k**4*S+k**5*T*S/4608+3*k**3*T/256)
def F(E): return 1-a(E)*G(E)
def D(E,N=None):
    k=m.sqrt(E)
    z=k/2 if N is None else N*m.asin(k/(2*N))
    q=2*k if N is None else 2*k*m.sqrt(1-E/(4*N*N))
    return m.re((E+u)*m.cos(z)-(g*(E+u)-h*h)*(m.sin(z)/q if E else m.mpf(1)/4))
def bisect(fn,l,r):
    l,r=m.mpf(l),m.mpf(r);fl,fr=fn(l),fn(r)
    assert fl*fr<0,(l,r,fl,fr)
    for _ in range(260):
        mid=(l+r)/2
        if mid==l or mid==r: break
        fm=fn(mid)
        if fm==0: return mid
        if fm*fl<0: r=mid
        else: l,fl=mid,fm
    return (l+r)/2
ns=[24,48,96,192,384,768,1536,3072]
def pole(j,N=None):
    k=(2*j+1)*m.pi
    return k*k if N is None else 4*N*N*m.sin(k/(2*N))**2
def root(j,N=None):
    l,r=(-4,-2) if j==0 else ((0 if j==1 else pole(j-2,N)),pole(j-1,N))
    e=bisect(lambda E:D(E,N),l,r)
    assert abs(D(e,N))<m.mpf('1e-60')
    assert abs(e+u)>m.mpf('1e-5') and abs(m.cos(m.sqrt(e)/2 if N is None else N*m.asin(m.sqrt(e)/(2*N))))>m.mpf('1e-6')
    assert abs(1-a(e)*(G(e) if N is None else GN(e,N)))<m.mpf('1e-60')
    return e
def st(x):return m.nstr(x,28)
rows=[]
for j in range(4):
    e=root(j); A=a(e)*C2(e)/m.diff(F,e)
    B=(a(e)*C4(e)+m.diff(lambda E:a(E)*C2(E),e)*A-m.diff(F,e,2)*A*A/2)/m.diff(F,e)
    rr={N:root(j,N) for N in ns}
    data=[]
    for N in ns[:-1]:
        x=rr[N]; y=rr[2*N];rich=(4*y-x)/3
        data.append({'N':N,'error':st(x-e),'N2_error':st(N*N*(x-e)),'N4_after_A':st(N**4*(x-e-A/N**2)),'richardson_error':st(rich-e),'N4_richardson_error':st(N**4*(rich-e))})
    assert abs(m.mpf(data[-1]['N2_error'])-A)<abs(A)*m.mpf('0.00001')
    assert abs(m.mpf(data[-1]['N4_richardson_error'])+B/4)<max(abs(B),m.mpf(1))*m.mpf('.0001')
    rows.append({'j':j,'E':st(e),'C2':st(C2(e)),'C4':st(C4(e)),'A':st(A),'B':st(B),'rows':data})
E=m.mpf('7.8'); N=24
s=sum(1/(pole(k,N)-E) for k in range(N))
assert abs(GN(E,N)-s)<m.mpf('1e-65')
node=[]
for j in (1,3,5):
    k=j*m.pi;N=384;en=4*N*N*m.sin(k/(2*N))**2;A=-k**4/12;B=k**6/360
    node.append({'m':j,'A':st(A),'B':st(B),'N384_N2_error':st(N*N*(en-k*k))})
print(json.dumps({'scope':'fixed-mark scalar K only; no physical calibration','precision_dps':m.mp.dps,'u_g_h':['2','1','0.5'],'green_check':{'N':24,'E':'7.8','closed':st(GN(E,24)),'sum':st(s),'abs_error':st(abs(GN(E,24)-s))},'branches':rows,'nodes':node,'scientific_acceptance':False},indent=2))
