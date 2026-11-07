#!/usr/bin/env python3
"""Restore the existing VM Compute HTTPS bridge; never reinstall its worker.

Run with sudo on the VM. No arguments installs automatic maintenance.
--renew is used by the installed timer. Python standard library only.
"""
import argparse
import fcntl
import hashlib
import http.client
import http.server
import ipaddress
import io
import json
import os
import platform
from pathlib import Path
import re
import shutil
import signal
import socket
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request

CONFIG = Path('/etc/vm-lab/server.json')
ACME = Path('/etc/vm-lab/acme')
CERTBOT = '/opt/vm-lab/certbot/bin/certbot'
HOOK = '/opt/vm-lab/deploy_cert.py'
PROGRAM = Path('/opt/vm-lab/recover_vm_bridge.py')
SERVICE = Path('/etc/systemd/system/vm-lab-bridge-maintain.service')
TIMER = Path('/etc/systemd/system/vm-lab-bridge-maintain.timer')
OLD_TIMER = 'vm-lab-cert-renew.timer'
WEBROOT = Path('/var/lib/vm-lab/acme/bridge-webroot')
REPORT = Path('/var/lib/vm-lab/acme/bridge-recovery.log')
LEGO = Path('/opt/vm-lab/lego-5.6.0')
LEGO_STATE = Path('/etc/vm-lab/lego')
LEGO_SHA256 = {
    'x86_64': ('amd64', 'f02fc11b6f56b97e387fa7caa0268f86f5a336953b22458e6430e4651fea439a'),
    'aarch64': ('arm64', '34d87a6552d69390c4a4560237045c47713a8e148d899e16db0e97040894ed1f'),
}
SECRETS = []
EVENTS = []


def say(message):
    for secret in SECRETS:
        message = message.replace(secret, '[REDACTED]')
    EVENTS.append(message)
    print(message, flush=True)


def run(argv, timeout=30, check=True):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{Path(argv[0]).name}: {result.stdout[-4000:]}')
    return result


def trusted_directory(path):
    for parent in reversed((path, *path.parents)):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('Untrusted system directory: ' + str(parent))


def atomic_write(path, data, info=None, mode=0o600):
    trusted_directory(path.parent)
    if path.is_symlink():
        raise RuntimeError('Refusing to replace symlink: ' + str(path))
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), info.st_uid if info else 0, info.st_gid if info else 0)
            os.fchmod(handle.fileno(), stat.S_IMODE(info.st_mode) if info else mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Backup:
    def __init__(self):
        trusted_directory(Path('/var/backups'))
        self.directory = Path(tempfile.mkdtemp(prefix='vm-lab-bridge-', dir='/var/backups'))
        self.items = []

    def save(self, path):
        if any(p == path for p, _, _ in self.items):
            return
        trusted_directory(path.parent)
        if path.is_symlink():
            raise RuntimeError('Unexpected symlink: ' + str(path))
        if path.exists():
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError('Unexpected file type: ' + str(path))
            copy = self.directory / str(len(self.items))
            copy.write_bytes(path.read_bytes())
            self.items.append((path, info, copy))
        else:
            self.items.append((path, None, None))
        manifest = [{'path': str(p), 'backup': c.name if c else None,
                     'uid': s.st_uid if s else None, 'gid': s.st_gid if s else None,
                     'mode': stat.S_IMODE(s.st_mode) if s else None}
                    for p, s, c in self.items]
        (self.directory / 'manifest.json').write_text(json.dumps(manifest, indent=2))

    def restore(self):
        errors = []
        for path, info, copy in reversed(self.items):
            try:
                if copy:
                    atomic_write(path, copy.read_bytes(), info)
                elif path.exists():
                    path.unlink()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError('Rollback incomplete: ' + '; '.join(errors))


def current_ip():
    url = ('http://169.254.169.254/computeMetadata/v1/instance/'
           'network-interfaces/0/access-configs/0/external-ip')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={'Metadata-Flavor': 'Google'})
    with opener.open(request, timeout=5) as response:
        value = response.read(128).decode().strip()
    address = ipaddress.IPv4Address(value)
    if not address.is_global:
        raise RuntimeError('Metadata did not return a public IPv4 address')
    return str(address)


def token_from(config):
    # The existing installation uses /<hex token>/mcp. Never invent a new token.
    candidates = set()
    def walk(value):
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value):
            candidates.add(value)
    walk(config)
    if len(candidates) != 1:
        raise RuntimeError('Cannot unambiguously locate the existing MCP token in server.json')
    return candidates.pop()


def usable_certificate(host, cert=None):
    cert = cert or ACME / 'live/vm-lab/fullchain.pem'
    if not cert.exists():
        return False
    try:
        names = ssl._ssl._test_decode_cert(str(cert)).get('subjectAltName', ())
    except (OSError, ssl.SSLError):
        return False
    return (('DNS', host) in names and
            run(['openssl', 'x509', '-in', str(cert), '-noout', '-checkend', '172800'],
                check=False).returncode == 0)


def install_lego():
    trusted_directory(LEGO.parent)
    if LEGO.exists() or LEGO.is_symlink():
        info = LEGO.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('Untrusted lego executable')
    else:
        arch, expected = LEGO_SHA256[platform.machine()]
        url = 'https://github.com/go-acme/lego/releases/download/v5.6.0/lego_v5.6.0_linux_' + arch + '.tar.gz'
        say('Downloading pinned lego 5.6.0; checking SHA-256 before execution.')
        # Bound total download time as well as connection time, before stopping the API.
        with tempfile.TemporaryDirectory(prefix='vm-lego-download-') as directory:
            archive = Path(directory) / 'lego.tar.gz'
            run(['curl', '--fail', '--silent', '--show-error', '--location',
                 '--proto', '=https', '--proto-redir', '=https',
                 '--connect-timeout', '10', '--max-time', '90',
                 '--output', str(archive), url], timeout=100)
            data = archive.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('lego archive checksum mismatch')
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            entry = archive.getmember('lego')
            if not entry.isfile() or entry.size > 200 * 1024 * 1024:
                raise RuntimeError('Invalid lego archive entry')
            atomic_write(LEGO, archive.extractfile(entry).read(), mode=0o755)
    result = run([str(LEGO), '--version'])
    if '5.6.0' not in result.stdout:
        raise RuntimeError('Unexpected lego version')


def tls_certificate_paths(host):
    return (LEGO_STATE / 'certificates' / (host + '.crt'),
            LEGO_STATE / 'certificates' / (host + '.key'))


def issue_tls_certificate(ip, host):
    install_lego()
    LEGO_STATE.mkdir(mode=0o700, exist_ok=True)
    trusted_directory(LEGO_STATE)
    say('TLS-ALPN-01 on port 443: pausing API only; worker and SSH stay running.')
    run(['systemctl', 'stop', 'vm-lab-api.service'])
    try:
        result = run([str(LEGO), 'run', '--accept-tos',
                      '--account-id', 'vm-lab-bridge', '--path', str(LEGO_STATE),
                      '--server', 'https://acme-v02.api.letsencrypt.org/directory',
                      '--domains', host, '--domains', ip, '--cert.name', host,
                      '--profile', 'shortlived', '--tls', '--tls.address', '0.0.0.0:443',
                      '--ipv4only', '--http-timeout', '20', '--cert.timeout', '60',
                      '--no-random-sleep', '--renew-force', '--force-cert-domains'],
                     timeout=150, check=False)
        say(result.stdout[-8000:])
        if result.returncode:
            raise RuntimeError('TLS-ALPN-01 certificate issuance failed (port 443).')
    finally:
        # This also runs on timeout or interruption, before the outer rollback.
        run(['systemctl', 'start', 'vm-lab-api.service'])


def deploy_tls_certificate(cert, key):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    for source, name in ((cert, 'fullchain.pem'), (key, 'privkey.pem')):
        destination = CONFIG.parent / name
        atomic_write(destination, source.read_bytes(), destination.stat())
    run(['systemctl', 'restart', 'vm-lab-api.service'])


class ChallengeServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def challenge_handler(root):
    class Handler(http.server.BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def do_GET(self):
            match = re.fullmatch(r'/\.well-known/acme-challenge/([A-Za-z0-9_-]+)', self.path)
            path = root / '.well-known/acme-challenge' / match[1] if match else None
            if not path or not path.is_file() or path.is_symlink():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            say('ACME HTTP ' + self.client_address[0] + ' ' + (fmt % args))
    return Handler


def issue_certificate(ip, host):
    WEBROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    trusted_directory(WEBROOT)
    try:
        server = ChallengeServer(('0.0.0.0', 80), challenge_handler(WEBROOT))
    except OSError as exc:
        raise RuntimeError('Port 80 is occupied. Stop the previous HTTP probe with Ctrl+C, then rerun.') from exc
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        say('HTTP-01 responder ready. Requesting certificate (one attempt, at most 150 seconds).')
        result = run([CERTBOT, 'certonly', '--non-interactive', '--agree-tos',
                      '--webroot', '--webroot-path', str(WEBROOT),
                      '--preferred-challenges', 'http', '--preferred-profile', 'shortlived',
                      '--cert-name', 'vm-lab', '--force-renewal',
                      '--ip-address', ip, '-d', host,
                      '--config-dir', str(ACME), '--work-dir', '/var/lib/vm-lab/acme',
                      '--logs-dir', '/var/log/vm-lab-acme',
                      '--deploy-hook', '/bin/true'], timeout=150, check=False)
        say(result.stdout[-6000:])
        if result.returncode:
            raise RuntimeError('Certificate issuance failed; the HTTP request log above shows whether validation reached this VM.')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def parse_rpc(response, wanted_id):
    if response.getheader('Content-Type', '').startswith('text/event-stream'):
        total, parts = 0, []
        while total < 1024 * 1024:
            line = response.readline(65537)
            if not line:
                break
            total += len(line)
            if line.rstrip(b'\r\n') == b'':
                if parts:
                    value = json.loads(b'\n'.join(parts))
                    if value.get('id') == wanted_id:
                        return value
                parts = []
            elif line.startswith(b'data:'):
                parts.append(line[5:].lstrip().rstrip(b'\r\n'))
        raise RuntimeError('No matching MCP event received')
    data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise RuntimeError('MCP response exceeded limit')
    return json.loads(data)


def check_mcp(host, token):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    def request(payload):
        connection = http.client.HTTPSConnection(host, timeout=10, context=ssl.create_default_context())
        # Verify the public hostname and certificate through the local listener.
        connection._create_connection = lambda *_a, **_kw: socket.create_connection(('127.0.0.1', 443), timeout=10)
        try:
            connection.request('POST', '/' + token + '/mcp', json.dumps(payload), headers)
            response = connection.getresponse()
            if response.status not in (200, 202, 204):
                raise RuntimeError(f'MCP returned HTTP {response.status}')
            session = response.getheader('Mcp-Session-Id')
            if session:
                headers['Mcp-Session-Id'] = session
            if 'id' not in payload:
                return None
            value = parse_rpc(response, payload['id'])
            if value.get('id') != payload['id'] or 'result' not in value or 'error' in value:
                raise RuntimeError('MCP returned an invalid or error response')
            return value['result']
        finally:
            connection.close()
    result = request({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                      'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                 'clientInfo': {'name': 'vm-bridge-recovery', 'version': '1.0'}}})
    headers['MCP-Protocol-Version'] = result['protocolVersion']
    request({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    result = request({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
    names = {tool['name'] for tool in result.get('tools', [])}
    if not {'start_python_job', 'write_work_file', 'cancel_job'} <= names:
        raise RuntimeError('MCP tool list does not match VM Compute')
    say('Verified TLS hostname + MCP initialize + tools/list: ' + str(len(names)) + ' tools')


def install_maintenance(backup, tls=False):
    for path in (PROGRAM, SERVICE, TIMER):
        backup.save(path)
    atomic_write(PROGRAM, Path(__file__).read_bytes(), mode=0o644)
    service = '''[Unit]
Description=Maintain VM Compute HTTPS for the current public IP
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 -I /opt/vm-lab/recover_vm_bridge.py --renew
ExecStopPost=/usr/bin/systemctl start vm-lab-api.service
TimeoutStartSec=420
PrivateTmp=true
NoNewPrivileges=true
'''
    if tls:
        service = service.replace('recover_vm_bridge.py --renew', 'recover_vm_bridge.py --renew --tls')
    timer = '''[Unit]
Description=Check VM Compute HTTPS after boot and every 12 hours

[Timer]
OnActiveSec=2min
OnUnitActiveSec=12h
RandomizedDelaySec=60
Unit=vm-lab-bridge-maintain.service

[Install]
WantedBy=timers.target
'''
    atomic_write(SERVICE, service.encode(), mode=0o644)
    atomic_write(TIMER, timer.encode(), mode=0o644)
    run(['systemd-analyze', 'verify', str(SERVICE), str(TIMER)])
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', TIMER.name])
    run(['systemctl', 'disable', '--now', OLD_TIMER])


def diagnostics():
    for argv in (['date', '-u'], ['systemctl', 'is-active', 'vm-lab-api.service',
                                 'vm-lab-worker.service', OLD_TIMER, TIMER.name],
                 ['ss', '-ltnp', '( sport = :80 or sport = :443 )']):
        try:
            say(run(argv, check=False).stdout[-2000:])
        except Exception as exc:
            say(str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renew', action='store_true')
    parser.add_argument('--tls', action='store_true', help='Use TLS-ALPN-01 on port 443 instead of HTTP-01')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo on the VM.')
    os.umask(0o077)
    def interrupted(signum, _frame):
        raise RuntimeError('Interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    with open('/run/lock/vm-lab-bridge-recovery.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another recovery/renewal is already running.')
        execute(args)


def execute(args):
    backup = None
    old_active = old_enabled = False
    old_stopped = False
    maintenance_attempted = False
    new_active = new_enabled = False
    try:
        for path in ((CONFIG,) if args.tls else (CONFIG, Path(CERTBOT), Path(HOOK))):
            if not path.is_file():
                raise RuntimeError('Existing installation missing: ' + str(path))
        trusted_directory(CONFIG.parent)
        config = json.loads(CONFIG.read_bytes())
        if not isinstance(config.get('public_ip'), str):
            raise RuntimeError('server.json has an unexpected public_ip schema')
        token = token_from(config)
        SECRETS.append(token)
        ip = current_ip()
        host = 'vm-' + ip.replace('.', '-') + '.sslip.io'
        say('Current VM: ' + ip + '; hostname: ' + host)
        resolved = {item[4][0] for item in socket.getaddrinfo(host, 443, socket.AF_INET)}
        if ip not in resolved:
            raise RuntimeError('DNS does not resolve the hostname to the current VM')
        run(['systemctl', 'is-active', '--quiet', 'vm-lab-worker.service'])
        # Do not race the previous Certbot service or an interactive invocation.
        if run(['systemctl', 'is-active', '--quiet', 'vm-lab-cert-renew.service'], check=False).returncode == 0:
            raise RuntimeError('The previous certificate renewal is running; rerun after it finishes')
        old_active = run(['systemctl', 'is-active', '--quiet', OLD_TIMER], check=False).returncode == 0
        old_enabled = run(['systemctl', 'is-enabled', '--quiet', OLD_TIMER], check=False).returncode == 0
        new_active = run(['systemctl', 'is-active', '--quiet', TIMER.name], check=False).returncode == 0
        new_enabled = run(['systemctl', 'is-enabled', '--quiet', TIMER.name], check=False).returncode == 0
        backup = Backup()
        for path in (CONFIG, Path('/etc/vm-lab/fullchain.pem'), Path('/etc/vm-lab/privkey.pem'),
                     ACME / 'renewal/vm-lab.conf'):
            backup.save(path)
        say('Backup: ' + str(backup.directory))
        if old_active:
            run(['systemctl', 'stop', OLD_TIMER])
            old_stopped = True
        if run(['systemctl', 'is-active', '--quiet', 'vm-lab-cert-renew.service'], check=False).returncode == 0:
            raise RuntimeError('Previous renewal still running; no changes applied')
        cert, key = tls_certificate_paths(host) if args.tls else (
            ACME / 'live/vm-lab/fullchain.pem', ACME / 'live/vm-lab/privkey.pem')
        if not usable_certificate(host, cert):
            if args.tls:
                issue_tls_certificate(ip, host)
            else:
                issue_certificate(ip, host)
        if not usable_certificate(host, cert):
            raise RuntimeError('New certificate failed hostname or expiry verification')
        config['public_ip'] = ip
        atomic_write(CONFIG, (json.dumps(config, indent=2) + '\n').encode(), CONFIG.stat())
        if args.tls:
            deploy_tls_certificate(cert, key)
        else:
            run(['/usr/bin/python3', '-I', HOOK])
        run(['systemctl', 'start', 'vm-lab-api.service'])
        for attempt in range(6):
            try:
                check_mcp(host, token)
                break
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                if attempt == 5:
                    raise
                time.sleep(1)
        if not args.renew:
            maintenance_attempted = True
            install_maintenance(backup, tls=args.tls)
        run(['systemctl', 'is-active', '--quiet', 'vm-lab-api.service', 'vm-lab-worker.service'])
        say('BRIDGE_LOCAL_OK. External ChatGPT connectivity still requires a connection check.')
        say('Automatic HTTPS maintenance: ' + TIMER.name)
        # Only the owner terminal gets the secret URL; it is omitted from saved diagnostics.
        if not args.renew:
            print('\nMCP URL (keep private):\nhttps://' + host + '/' + token + '/mcp', flush=True)
    except BaseException as exc:
        say('RECOVERY_FAILED: ' + str(exc))
        if maintenance_attempted:
            run(['systemctl', 'disable', '--now', TIMER.name], check=False)
        if backup:
            try:
                backup.restore()
                run(['systemctl', 'daemon-reload'], check=False)
                run(['systemctl', 'try-restart', 'vm-lab-api.service'], check=False)
                say('Previous configuration and deployed certificate restored.')
            except Exception as rollback_error:
                say(str(rollback_error))
        if old_enabled:
            run(['systemctl', 'enable', OLD_TIMER], check=False)
        if old_stopped:
            run(['systemctl', 'start', OLD_TIMER], check=False)
        if maintenance_attempted and new_enabled:
            run(['systemctl', 'enable', TIMER.name], check=False)
        if maintenance_attempted and new_active:
            run(['systemctl', 'start', TIMER.name], check=False)
        diagnostics()
        raise SystemExit(1)
    finally:
        try:
            atomic_write(REPORT, ('\n'.join(EVENTS) + '\n').encode())
            print('Report: ' + str(REPORT), flush=True)
        except Exception as exc:
            print('Could not save report: ' + str(exc), flush=True)


if __name__ == '__main__':
    main()
