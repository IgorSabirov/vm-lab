"""Read pinned source files and evaluate closed-form identities; never run BBN."""
import hashlib, json, math, pathlib, sys
PIN = '6f7e5680614fb119d65a6c9c65a292240b27c61e'
root = pathlib.Path(sys.argv[1])
manifest_path = pathlib.Path(__file__).with_name('INPUT_MAP.json')
if not manifest_path.exists():
    raise SystemExit('Keep the published INPUT_MAP.json next to this script.')
manifest = json.loads(manifest_path.read_text())
assert manifest['pin'] == PIN, 'Manifest pin mismatch'
for path, expected in manifest['source_sha256'].items():
    actual = hashlib.sha256((root/path).read_bytes()).hexdigest()
    assert actual == expected, f'Source hash mismatch: {path}'
names = ['d_d__He3_n','d_d__t_p','d_p__He3_g','He3_t__a_d','He3_t__a_n_p']
paths = ['primat/config.py','primat/main.py','primat/network_data.py','primat/sensitivity.py','primat/data/nuclear/networks/large.txt','primat-c/src/mc.c','primat-c/src/network_data.c']
rows=[]
network=(root/paths[4]).read_text().splitlines()
for name in names:
    entry=next(line for line in network if line.startswith(name+','))
    filename=entry.split(',')[1].strip()
    path=f'primat/data/nuclear/tables/{name}/{filename}'
    paths.append(path)
    text=(root/path).read_text()
    a=[list(map(float,line.split())) for line in text.splitlines() if line and not line.startswith('#')]
    assert len(a)==1000 and all(row[2]>1 for row in a)
    near=min(a,key=lambda x:abs(x[0]-.8))
    rows.append(dict(reaction=name,path=path,source_header=text.splitlines()[0],rows=len(a),T9_range=[a[0][0],a[-1][0]],factor_range=[min(x[2] for x in a),max(x[2] for x in a)],nearest_T9=near[0],factor_near_T9_0_8=near[2]))
a=math.log(30)/math.log(10)
Q=.5*math.erfc(a/math.sqrt(2)); phi=math.exp(-a*a/2)/math.sqrt(2*math.pi)
out={'status':'STATIC_SOURCE_AND_ANALYTIC_AUDIT','pin':PIN,'BBN_executed':False,'MC_executed':False,'scientific_acceptance':False,'tables':rows,'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},'factor10_cap30':{'normal_threshold':a,'clipped_probability_per_channel':2*Q,'log_rate_variance_ratio_capped_to_uncapped':1-2*a*phi+2*(a*a-1)*Q},'sensitivity_denominator':{'relative_step':.01,'exact_log_interval':math.log1p(.01)-math.log1p(-.01),'code_denominator':2*math.log1p(.01),'reported_to_exact_secant_ratio':(math.log1p(.01)-math.log1p(-.01))/(2*math.log1p(.01))},'unresolved':['Cross-channel D+D covariance from shared experimental nuisance parameters','Posterior temperature covariance beyond single-amplitude compression','Probability interpretation of CF88 factor-10 placeholders','Output covariance and clamp impact on BBN abundances','Weak-rate theory covariance separate from neutron lifetime']}
assert 0<out['factor10_cap30']['clipped_probability_per_channel']<1
assert 0<out['factor10_cap30']['log_rate_variance_ratio_capped_to_uncapped']<1
print(json.dumps(out,ensure_ascii=False,indent=2))
