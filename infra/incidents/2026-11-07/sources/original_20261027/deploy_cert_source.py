"""Root-owned Certbot deploy hook. Does not trust paths from job data."""
import grp
import os
from pathlib import Path
import pwd
import secrets
import ssl
import subprocess

source = Path("/etc/vm-lab/acme/live/vm-lab")
destination = Path("/etc/vm-lab")
cert = (source / "fullchain.pem").read_bytes()
key = (source / "privkey.pem").read_bytes()
check = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
check.load_cert_chain(str(source / "fullchain.pem"), str(source / "privkey.pem"))
uid = pwd.getpwnam("vm-lab-api").pw_uid
gid = grp.getgrnam("vm-lab").gr_gid
for name, data in (("fullchain.pem", cert), ("privkey.pem", key)):
    path = destination / name
    temp = destination / ("." + name + "-" + secrets.token_hex(6))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
        os.fchown(output.fileno(), uid, gid)
    os.replace(temp, path)
subprocess.run(["systemctl", "try-restart", "vm-lab-api.service"], check=True)

