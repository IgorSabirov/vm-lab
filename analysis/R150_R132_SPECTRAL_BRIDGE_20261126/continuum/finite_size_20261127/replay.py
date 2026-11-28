"""Fixed-mark scalar spectral asymptotics; numpy, mpmath. Run python replay.py."""
import numpy as np
import mpmath as m
from math import pi,sin,tan,sqrt,asin
m.mp.dps=70
u,g,h=map(m.mpf,['2','1','.5'])
a=lambda E:g-h*h/(E+u)
G=lambda E:m.tan(m.sqrt(E)/2)/(2*m.sqrt(E))
Gn=lambda N,E:m.tan(N*m.asin(m.sqrt(E)/(2*N)))/(2*m.sqrt(E)*m.sqrt(1-E/(4*N*N)))
F=lambda E:1-a(E)*G(E)
def C2(E):
    k=m.sqrt(E)
    return k*k/(96*m.cos(k/2)**2)+k*m.tan(k/2)/16
def C4(E):
    k=m.sqrt(E)
    return (3*k**4/(2560*m.cos(k/2)**2)+k**5*m.tan(k/2)/(4608*m.cos(k/2)**2)+k**4/(768*m.cos(k/2)**2)+3*k**3*m.tan(k/2)/256)
e=m.findroot(F,(7,9))
A=a(e)*C2(e)/m.diff(F,e)
B=(a(e)*C4(e)+m.diff(lambda x:a(x)*C2(x),e)*A-m.diff(F,e,2)*A*A/2)/m.diff(F,e)
print('e,A,B',*[m.nstr(x,35) for x in (e,A,B)])
def root(N):
    en=m.findroot(lambda x:1-a(x)*Gn(N,x),(e-m.mpf('.1'),e))
    assert abs(1-a(en)*Gn(N,en))<m.mpf('1e-60')
    return en
for N in (12,24,48,96,192,384,768,1536,3072):
    en=root(N)
    print(N,*[m.nstr(x,18) for x in (en,N*N*(en-e),N**4*(en-e-A/N**2))])
    if N>=192:
        assert abs(N**4*(en-e-A/N**2)-B)<m.mpf('3e-6')
for N in (12,48,192):
    for E in (7.820855,50.,86.822538):
        k=np.arange(N);lam=4*N**2*np.sin((2*k+1)*pi/(2*N))**2
        s=np.sum(1/(lam-E));th=2*asin(sqrt(E)/(2*N));c=tan(N*th/2)/(2*N*sin(th))
        print('green',N,E,format(s,'.12f'),format(s-c,'.2e'))
        assert abs(s-c)<2e-11
for N in (12,48,192,384):
    H=np.zeros((N+1,N+1));H[0,0]=-2;H[0,1]=H[1,0]=.5*np.sqrt(N)
    H[1:,1:]=2*N*N*np.eye(N);i=np.arange(1,N)
    H[i,i+1]=H[i+1,i]=-N*N;H[1,N]=H[N,1]=N*N;H[1,1]-=N
    es=np.linalg.eigvalsh(H);err=abs(es[1]-float(root(N)))
    print('matrix',N,es[:3],err)
    assert err<2e-9
    assert abs(es[2]-4*N*N*sin(pi/(2*N))**2)<2e-9
print('PASS (fixed benchmark; no physical calibration)')
