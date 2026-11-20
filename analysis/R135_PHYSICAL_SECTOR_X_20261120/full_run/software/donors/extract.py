"""Read numeric inputs from specific source members and labelled tables."""
import re
import subprocess
import tarfile
import math

NUMBER = r'(-?\d+(?:\.\d+)?)'
WITH_ERROR = NUMBER + r'\s*\((\d+)\)'


def article(path, member, encoding='utf8'):
    with tarfile.open(path) as archive:
        info = archive.getmember(member)
        if not info.isfile() or info.size > 2_000_000:
            raise ValueError(f'Invalid article member {member}')
        return archive.extractfile(info).read().decode(encoding)


def one(pattern, text):
    values = re.findall(pattern, text, re.S)
    if len(values) != 1:
        raise ValueError(f'Expected one source match, found {len(values)} for {pattern}')
    return values[0]


def uncertainty(value, digits):
    return int(digits) / 10 ** len(value.partition('.')[2])


def measurement(match):
    value, digits = match
    return {'value': float(value), 'sigma': uncertainty(value, digits)}


def power(value):
    if value.startswith('10^'):
        return 10.0 ** int(value[3:].strip('{}'))
    return float(value)


def physics(files):
    fms = article(files['fms'], 'draft-final.tex')
    eos = article(files['eos'], 'paper.tex')
    short = article(files['giusti'], 'proceeding.tex')
    mp = article(files['mp'], 'spectrum.tex', 'latin1')
    scale = article(files['francis'], 'betac11.tex')
    caption = next(x for x in re.findall(r'\\begin\{figure\}.*?\\end\{figure\}', fms, re.S)
                   if r'\label{fig:fourgbxY}' in x)
    pairs = re.findall(r'(Top left|Top right|Bottom left|Bottom right):[^=]*= \(([^,]+),\\,([^)]*)\)', caption)
    if len(pairs) != 4 or len({p[0] for p in pairs}) != 4:
        raise ValueError('Incomplete FMS preparations')
    preparations = [{'point_id':'XB-FMS-'+panel.lower().replace(' ','-'),
                     'm0_GeV':power(mass), 'R_post':power(r)} for panel,mass,r in pairs]
    mass_table = next(x for x in re.findall(r'\\begin\{table\}.*?\\end\{table\}', fms, re.S)
                      if r'\label{tab:states}' in x)
    states = []
    for idx, label, ratio in re.findall(r'^([0-9]+)&([^&]+)&([0-9.]+)', mass_table, re.M):
        label = '0^{++}' if label == r'\zpp' else label
        states.append(dict(index=int(idx), JPC=label, spin=int(label[0]), m_over_m0=float(ratio)))
    if [s['index'] for s in states] != list(range(1,13)):
        raise ValueError('Incomplete mass table')
    m,stat,sys = one(r'\$0\^\{\+\+\}\$\s*&\s*&\s*\\bb\s*'+WITH_ERROR+r'\((\d+)\)', mp)
    phases = {name:measurement(one(r'\\frac\{s\(T_c\^'+symbol+r'\)\}\{T_c\^3\}\s*=\s*'+WITH_ERROR,eos))
              for name,symbol in [('cold','-'),('hot',r'\+')]}
    # Every five-column block ends in its own five continuum extrapolations.
    rows = []
    for block in eos.split(r'\specialrule{0.1em}{0em}{0em}'):
        temps = re.findall(r'\$T=\s*'+NUMBER+r'\\, T_c\$', block)
        entropies = re.findall(r'\$s\(T\)/T\^3=\s*'+WITH_ERROR, block)
        if temps or entropies:
            if len(temps) != len(entropies):
                raise ValueError('Incomplete continuum row')
            rows.extend({'T_over_Tc':float(t),**measurement(s)} for t,s in zip(temps,entropies))
    if len(rows) != 25 or sorted({r['T_over_Tc'] for r in rows}) != [r['T_over_Tc'] for r in rows]:
        raise ValueError('Unexpected Giusti Table 3 layout')
    def coefficients(prefix, indices, count):
        values = [re.findall(r'\$'+prefix+'_'+str(i)+'='+NUMBER+r'\$', eos) for i in indices]
        if any(len(v) != count for v in values):
            raise ValueError(f'Incomplete fit coefficients for {prefix}')
        return [[float(value) for value in group] for group in zip(*values)]

    fit = {'s_cold':coefficients('a', range(4), 1)[0],
           's_hot':coefficients('s', range(1,6), 2),
           'p_anchor_hot':float(one(r'for\s+\$T/T_c \\in \[1,1\.1\]\$ we have \$p_1='+NUMBER,eos))}
    return dict(entropy_fit=fit,preparations=preparations, states=states, continuum_s_over_T3=rows,
                phase_entropy=phases, latent_heat=measurement(one('combined result '+r'\$h='+WITH_ERROR,eos)),
                r0_Tc=measurement(one(r'\\rO \\Tc = '+WITH_ERROR+r'\s*\\;',scale)),
                r0_m0={'value':float(m),'sigma_stat':uncertainty(m,stat),'sigma_anisotropy':uncertainty(m,sys)},
                Tc_sqrt_t0=measurement(one(r'T_\{\\textrm\{c\}\} \\sqrt\{t_0\} = '+WITH_ERROR,short)),
                m0_over_sqrt_sigma=measurement(one('respectively '+WITH_ERROR,short)),
                Tc_over_sqrt_sigma=measurement(one(r'T_c/\\sqrt\{\\sigma\} = '+WITH_ERROR,short)))


def scalar_portal(files):
    """The sourced scalar matrix element and one partonic coefficient, not a total width."""
    source = article(files['fms-portals'], 'draft-v3.tex')
    scalar = measurement(one(r'4\\pi\\alpha_xF_\{\\zpp\}\^S = '+WITH_ERROR+r'\\,m_x\^3', source))
    a, b = one(r'\\frac\{\\alpha_3\^2\}\{16\\pi\}\\lrf\{(\d+)\}\{(\d+)\}\^2', source)
    coefficient = 8/(16*math.pi)*(int(a)/int(b)/(4*math.pi))**2
    return {'scalar_4pi_alpha_F_over_m0_cubed': scalar,
            'K_gg': coefficient*scalar['value']**2,
            'K_gg_one_sigma_input_range': [coefficient*(scalar['value']+sign*scalar['sigma'])**2
                                         for sign in (-1, 1)],
            'convention': 'Gamma(0++ -> gg) = K_gg alpha_3^2 chi_3^2 m0^9/M^8; partonic EFT',
            'physical_width_status': 'OPEN_INPUT',
            'missing': ['portal Wilson coefficients and mediator scale',
                        'EFT energy and temperature domain', 'hadronic matching and branching fractions',
                        'C-odd matrix elements and other populated species']}


def observations(files):
    pdg = subprocess.run(['pdftotext','-layout',str(files['pdg']),'-'], check=True,
                         capture_output=True, encoding='utf-8').stdout
    d = one(r'Weighted mean, with S = [\d.]+\s+'+NUMBER+r'\s*±\s*'+NUMBER, pdg)
    def paper_value(key, expression):
        text = article(files[key],'main.tex')
        if key == 'lbt':
            text = one(r'\\beq\s*(\\Yp\s*=.*?)\\label\{eq:Yp_avg\}', text.split('which yields,')[-1])
        if key == 'lbtv':
            text = one(r'\\label\{eq:Nnu-tout\}(.*?)\\end\{equation\}',text)
        if key == 'gold':
            text = one(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',text)
        matches = set(re.findall(expression + r'\s*=\s*'+NUMBER+r'\s*\\pm\s*'+NUMBER,text))
        if len(matches) != 1:
            raise ValueError(f'Ambiguous estimate in {key}: {matches}')
        return next(iter(matches))
    def row(value, units, role):
        return dict(value=float(value[0]),sigma=float(value[1]),units=units,role=role)
    return {'PDG2025':row(d,'1e6 D/H','alternative to Cooke'),
            'LBT_IV':row(paper_value('lbt',r'\\Yp'),'helium mass fraction','alternative to Aver'),
            'LBT_V':row(paper_value('lbtv',r'N_\\nu'),'N_nu','external joint-result check'),
            'Goldstein_Hill':row(paper_value('gold',r'N_\{\\rm eff\}'),'N_eff','external joint-result check')}


def baseline_observations(files):
    """Read the two primordial estimators used by the frozen P0 likelihood."""
    cooke = article(files['cooke'], 'ms.tex', 'latin1')
    aver = article(files['aver'], 'AOS4-8e.tex', 'latin1')
    cooke=one(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',cooke)
    aver=one(
        r'\n\\abstract\{(.*?)\n\}\s*\\keywords\{',aver)
    d = one(r'deduce that the primordial deuterium abundance is .*? = '+NUMBER+r'\\pm'+NUMBER,cooke)
    y = one(r'From a regression to zero metallicity, we determine Y\$_\{p\}\$ \$=\$ '+NUMBER+r' \$\\pm\$ '+NUMBER,aver)
    if not (-4.7 < float(d[0]) < -4.4 and 0. < float(d[1]) < .1
            and .22 < float(y[0]) < .27 and 0. < float(y[1]) < .03):
        raise ValueError('BBN estimator or uncertainty outside registered source sanity range')
    return {
        'Cooke-DH': dict(value=float(d[0]),sigma=float(d[1]),observable='log10_D_over_H',units='log10 number ratio'),
        'Aver-Yp': dict(value=float(y[0]),sigma=float(y[1]),observable='Y_p',units='mass fraction')
    }
