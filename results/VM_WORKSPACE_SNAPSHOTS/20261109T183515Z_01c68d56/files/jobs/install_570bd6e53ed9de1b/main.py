import json, os, pathlib, socket
import numpy as np, scipy, sympy, matplotlib
assert os.getuid() not in (0, 1000)
try:
    ssh_visible = pathlib.Path('/home/yc-user/.ssh').exists()
except PermissionError:
    ssh_visible = False
assert not ssh_visible
try:
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
except OSError:
    pass
else:
    sock.close()
    raise AssertionError('Network access unexpectedly allowed')
for p in ['/etc/vm-compute-test-denied','/opt/vm-compute/test-denied']:
    try:
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except OSError:
        pass
    else:
        os.close(fd)
        pathlib.Path(p).unlink()
        raise AssertionError('OS unexpectedly writable')
assert abs(np.linalg.det(np.array([[2.,1.],[1.,2.]]))-3.)<1e-10
pathlib.Path('selftest.json').write_text(json.dumps({'status':'PASS','numpy':np.__version__,'scipy':scipy.__version__,'uid':os.getuid()}))
print('SELFTEST PASS',flush=True)
