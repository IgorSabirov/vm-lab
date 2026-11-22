"""Structured scientific records for the R142 replay."""
import json
import math
from pathlib import Path
from fractions import Fraction
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent


def cascade(mapping, first, second, critical):
    roots = [first, second]
    for level in range(2, 11):
        def residual(r):
            x = critical
            for _ in range(2**level):
                x = mapping(r, x)
            return x - critical
        step = (roots[-1] - roots[-2]) / 250
        left = roots[-1] + step / 2
        for i in range(1, 251):
            right = roots[-1] + i * step
            if residual(left) * residual(right) < 0:
                root = brentq(residual, left, right, xtol=1e-15)
                x = critical
                for _ in range(2**(level-1)):
                    x = mapping(root, x)
                assert abs(x-critical) > 1e-9
                roots.append(root)
                break
            left = right
        else:
            raise ValueError('missing successive doubling')
    return dict(roots=roots, ratios=[(b-a)/(c-b) for a,b,c in zip(roots,roots[1:],roots[2:])])


def export(g):
    claims = []
    def add(key, positions, tier, formula, inputs, test, status, units='1', tolerance=None, vintage='модель или точный счёт', **extra):
        for i, value in enumerate(positions):
            claims.append(dict(id=f'{key}.{i+1}', value=value, units=units, tier=tier,
                               formula=formula, inputs=inputs, vintage=vintage, tolerance=tolerance,
                               falsifier=test, status=status, **extra))

    for key, vals, tier, form, inp, test, status in [
        ('nuclear',g['groups'][0],'T1','sum(2j+1) across gap','ordered levels in origin_audit','fixed interaction: separation gaps and 2+','literature; ordering assumed'),
        ('local', [16,32,34],'T1','isotopic shell gap','O, K/Ca, Ca respectively','vary Z at fixed N; removal and mass data','donor observations'),
        ('osc3',g['osc'],'T0','(K+1)(K+2)(K+3)/3','K=0..6, spin 1/2','enumerate triples','computed'),
        ('noble',g['groups'][3],'T1','group 18 electron filling','neutral atoms; IUPAC','ionization energy vs neighbours; Og spectroscopy separate','tabulated'),
        ('sodium',[8,20,40,58,92],'T1','electronic shell closure','Knight 1984, N=4..100','change charge at fixed atom count','reported features'),
        ('sodium_low',[2],'T1','lowest shell capacity','jellium; outside Knight range','test small clusters','model only'),
        ('dot',g['dot'],'T0','(K+1)(K+2)','K=0..5 spin-degenerate 2D oscillator','enumerate pairs; device deformation for applicability','computed model'),
        ('atomic',g['atomic'],'T0','2n²','n=1..6','sum 2(2l+1)','computed'),
        ('string',[26,10],'T1','D-26=0; 3D/2-15=0 respectively','critical flat bosonic / RNS matter','vary worldsheet matter','conditional deduction'),
        ('anomaly',[496],'T1','dim(g)=496','10D chiral supergravity and vectors','full I12 factorization','necessary condition'),
        ('color',[8],'T0','3²-1','SU(3)','count generators','exact'),
        ('space',[230],'T0','3D space group classification','ordinary crystallographic equivalence','enumerate types','literature'),
        ('kissing',[12],'T0','3D kissing number','equal spheres','upper bound and construction','literature'),
    ]:
        add(key,vals,tier,form,inp,test,status)
    for v in (136,137,g['wyler']):
        add('alpha'+str(round(v,5)),[v],'T4 candidate; selection history separate','fixed inverse alpha','137.035999177','compare fixed prediction with measured inverse alpha','rejected',vintage='CODATA 2022',tolerance=2.1e-8,residual_u=(v-g['a22'])/g['u'])
    add('Koide',[2/3],'T3','Σm/(Σ√m)²',{'e':g['me_'],'mu':g['mmu'],'tau':1777.09},'remeasure tau with total uncertainty 0.0242 MeV at unchanged centre','compatible',vintage='Belle II 2023; reference masses in MeV',tolerance=g['sigK'],branches_MeV=list(g['roots']))
    add('phi',[(1+math.sqrt(5))/2],'T0','dominant eigenvalue','Fibonacci substitution','change substitution; check gap labels separately','exact')
    maps = {
        'logistic':cascade(lambda r,x:r*x*(1-x),2,1+math.sqrt(5),.5),
        'sine':cascade(lambda r,x:r*math.sin(math.pi*x),.5,brentq(lambda r:r*math.sin(math.pi*r)-.5,.7,.9),.5),
        'quartic':cascade(lambda r,x:1-r*x**4,0,1,0)}
    for name, ref in [('logistic',4.6692),('sine',4.6692),('quartic',7.2846)]:
        val=maps[name]['ratios'][-1]
        assert abs(val-ref)<0.001
        add(name,[val],'T1','successive interval ratio',name,'change maximum order','computed finite period',tolerance=.001)
    for key,val,tier,formula,inputs,test,status,unit in [
        ('angle',1.1,'T2 device / T1 conditional prediction','alpha=w/(hv k_theta)','w=.11 eV, hv=.596,.658 eV nm','measure geometry and bandwidth','donor; parameter dependent','deg'),
        ('Dirac',1e39,'T3','F_em/F_grav','electron and proton','LLR tests extra G proportional to 1/t','order only','1'),
        ('Lambda',g['Lam']*g['lp']**2,'T3','3 Omega_L H0² lp²/c²','67.4 km/s/Mpc; Omega_L=.6847','specify normalization; compare independent background','computed scale','1'),
        ('MOND',1/(2*math.pi),'T3','a0/(cH0)','a0=1.2e-10 m/s²; H0=67.4,73','held-out galaxies and alternative scales','open','1'),
        ('Efimov',math.exp(math.pi/1.00624),'T1','exp(pi/s0)','s0=1.00624; Huang 21.0(1.3)','next resonance length ratio','compatible','1'),
        ('BKT',2/math.pi,'T1','Υ/(kBT)','low-temperature side; Bishop–Reppy','measure stiffness near transition','literature','1'),
        ('Haldane',.41,'T1','gap/J','spin-1 nearest-neighbour isotropic chain','neutron data with independent J','numerical donor','1'),
        ('Hall','C','T1','sigma_xy=C e²/h','gapped integer phase','measure plateau; fractional charge separate','conditional','e²/h'),
        ('mixing',0,'T1','Ue3=0','exact tribimaximal matrix','Daya Bay theta13','rejected','1'),
        ('mass_ratio',1836.15,'T2 input','mp/me','reference low-energy masses','independent mass determination','measured input','1'),
        ('Omega',1678.6,'T1 approximate','2 M_Xi - M_Sigma','1531.8 and 1385 MeV','Omega mass','retrospective','MeV'),
        ('alpha_input',g['a22'],'T2','alpha(0)^-1','CODATA 2022','independent determination','measured input','1'),
        ('a0',1.2e-10,'T2','acceleration scale','galactic rotation curves','hold out galaxies','calibration','m/s²')]:
        add(key,[val],tier,formula,inputs,test,status,unit,vintage=str(inputs))
    for n in range(3,7):
        add(f'Balmer{n}',[1e9/(g['RH']*(.25-1/n**2))],'T1','1/(RH*(1/4-1/n²))',n,'vacuum hydrogen line','computed','nm')
    for planet,pred in g['pred'].items():
        add(planet,[pred],'T4 if indices selected post hoc','0.4+0.3*2^n',{'actual':g['act'][planet]},'next occupied orbit','retrospective','AU')
    data=dict(schema='R142-audit-v2', coverage={'original':len(g['seen']),'additional':3}, claims=claims, cascades=maps,
              calibration=json.loads((HERE/'CALIBRATION.json').read_text()),farey=g['farey_results'],
              efimov_residual=(21-math.exp(math.pi/1.00624))/1.3)
    data.update(
        koide=dict(mass_roots_MeV=list(g['roots']), Q_belle=g['Q'](1777.09),
                   sigma_Q=g['sigK'], derivative_per_MeV=g['dQ'],
                   stress_5sigma_MeV=(1777.09-max(g['roots']))/5),
        rydberg_per_m=dict(infinite_mass=g['Rinf'],hydrogen=g['RH']),
        nuclear_partial_sums=g['parts'], lambda_m_inv2=g['Lam'],
        rho_lambda_over_planck=g['Lam']*g['lp']**2/(8*math.pi),
        mond_ratio_by_H0={h:1.2e-10/(g['c']*h/3.0856775814913673e19/(2*math.pi)) for h in (67.4,73.)},
        graphene_deg_by_hv={hv:math.degrees(2*math.asin(.11/(.586*hv*2*g['kD']))) for hv in (.596,.658)},
        efimov_reference=math.exp(math.pi/1.00624),
        repeats={str(x):v for x,v in g['mult'].items() if v>1})
    assert len({row['id'] for row in claims})==len(claims)
    (HERE/'CHECKS.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    for name,series in maps.items():
        print(name, 'period 1024 ratio', series['ratios'][-1])
