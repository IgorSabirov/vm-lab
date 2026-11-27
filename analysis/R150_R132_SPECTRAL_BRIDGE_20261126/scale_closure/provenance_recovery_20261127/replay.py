"""Reconstruct candidate log-grid point; no fit, no BBN. mpmath."""
import mpmath as m
m.mp.dps=60
hc=m.mpf('197.3269804'); T=m.mpf('.08')
def evalp(M,ell,N=8):
    e=hc/ell; J=e*e/(2*M)
    a=[4*m.sin(m.pi*k/N)**2 for k in range(N)]
    b=[4*m.sin(m.pi*(k+m.mpf('.5'))/N)**2 for k in range(N)]
    def stat(x,y):
        w=[m.exp(-t/y) for t in x];z=1+sum(w)
        return z,sum(t*v for t,v in zip(x,w))/z
    def F(y):
        z,u=stat(a,y);w,v=stat(b,y);return y*m.log(z/w)
    y=m.findroot(lambda y:m.diff(F,y),(m.mpf('.07'),m.mpf('.1')))
    def rel(n):
        z=lambda p:1+sum(m.exp(-(m.sqrt(M*M+4*e*e*m.sin(m.pi*(k+p)/n)**2)-M)/T) for k in range(n))
        return 1-z(m.mpf('.5'))/z(0)
    return [M,ell,e,J,y*J*1000,F(y)*J*1000,rel(6),rel(8)]
points=[(10**m.mpf('-1.8'),10**m.mpf('4.3')),(m.mpf('.01585'),m.mpf('19950')),(10**m.mpf('-2'),10**m.mpf('4.4')),(10**m.mpf('-1.6'),10**m.mpf('4.2'))]
rows=[evalp(*p) for p in points]
for row in rows:
    print(' '.join(m.nstr(x,22) for x in row))
# Original printed values are rounding checks, not independent observations.
assert [format(float(v),fmt) for v,fmt in zip(rows[0][:6],('.5f','.0f','.7f','.7f','.5f','.5f'))] == ['0.01585','19953','0.0098898','0.0030856','0.24704','0.10684']
assert format(float(rows[0][1]),'.4g')=='1.995e+04'
assert abs(rows[0][3]-rows[2][3])<m.mpf('1e-58')
assert abs(rows[0][3]-rows[3][3])<m.mpf('1e-58')
