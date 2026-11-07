import json
from pathlib import Path
c=json.loads(Path('/etc/vm-compute/server.json').read_text())
print('https://vm-'+c['public_ip'].replace('.','-')+'.sslip.io/'+c['token']+'/mcp')
