"""Repair the existing VM Compute HTTPS endpoint. Run inside its VM."""
import datetime as dt
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from acme import challenges, client, messages
import josepy
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ObjectIdentifier

ROOT = Path('/etc/vm-lab')
PROGRAM = Path('/opt/vm-lab/renew_dns.py')
UNIT = Path('/etc/systemd/system/vm-lab-cert-renew.service')
TIMER = 'vm-lab-cert-renew.timer'
API = 'vm-lab-api.service'
INSTALL = '--install' in sys.argv

# acme 5.8.0 otherwise decodes tls-alpn-01 as UnrecognizedChallenge.
if 'tls-alpn-01' not in challenges.Challenge.TYPES:
    @challenges.ChallengeResponse.register
    class TLSALPNResponse(challenges.KeyAuthorizationChallengeResponse):
        typ = 'tls-alpn-01'

    @challenges.Challenge.register
    class TLSALPN(challenges.KeyAuthorizationChallenge):
        typ = 'tls-alpn-01'
        response_cls = TLSALPNResponse

        def validation(self, account_key, **kwargs):
            return hashlib.sha256(self.key_authorization(account_key).encode('ascii')).digest()

def run(*args):
    subprocess.run(args, check=True, timeout=30)

def active(name):
    state = subprocess.check_output(
        ['systemctl', 'show', '-p', 'ActiveState', '--value', name], text=True).strip()
    return state in ('active', 'activating', 'deactivating', 'reloading')

def atomic(path, data, info=None):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            if info:
                os.fchown(out.fileno(), info.st_uid, info.st_gid)
                os.fchmod(out.fileno(), info.st_mode & 0o777)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def verify(host, cfg):
    conn = http.client.HTTPSConnection(host, timeout=8)
    try:
        conn.sock = ssl.create_default_context().wrap_socket(
            socket.create_connection(('127.0.0.1', 443), timeout=8), server_hostname=host)
        conn.request('POST', '/' + cfg['token'] + '/mcp',
            json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}}),
            {'Content-Type': 'application/json', 'Accept': 'application/json'})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError('MCP HTTP ' + str(response.status))
        names = {item['name'] for item in json.loads(response.read())['result']['tools']}
        if not {'write_work_file', 'start_python_job', 'job_status'} <= names:
            raise RuntimeError('MCP tools check failed')
    finally:
        conn.close()

def issue(host):
    accounts = sorted((ROOT / 'acme/accounts/acme-v02.api.letsencrypt.org/directory').glob('*/regr.json'))
    if not accounts:
        raise RuntimeError('Existing ACME account not found')
    account_key = josepy.JWK.json_loads((accounts[0].parent / 'private_key.json').read_text())
    registration = messages.RegistrationResource.json_loads(accounts[0].read_text())
    network = client.ClientNetwork(account_key, account=registration, timeout=20)
    directory = client.ClientV2.get_directory('https://acme-v02.api.letsencrypt.org/directory', network)
    acme = client.ClientV2(directory, network)
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([]))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), False)
        .sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM))
    print('Запрос сертификата только для ' + host, flush=True)
    order = acme.new_order(csr)
    pending = []
    for auth in order.authorizations:
        if auth.body.identifier.value != host:
            raise RuntimeError('Unexpected ACME identifier')
        if auth.body.status == messages.STATUS_VALID:
            continue
        offered = [str(c.chall.to_partial_json().get('type', 'unknown')) for c in auth.body.challenges]
        print('Доступные проверки: ' + ', '.join(offered), flush=True)
        challenge = next((c for c in auth.body.challenges if c.chall.typ == 'tls-alpn-01'), None)
        if challenge is None:
            raise RuntimeError('CA не предложил TLS-ALPN для имени. API не останавливался.')
        pending.append((challenge, challenge.chall.response(account_key)))
    if len(pending) > 1:
        raise RuntimeError('Unexpected duplicate authorizations')
    server = None
    stopped = False
    with tempfile.TemporaryDirectory(prefix='vm-dns-') as temporary:
        try:
            if pending:
                challenge, response = pending[0]
                now = dt.datetime.now(dt.timezone.utc)
                subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ACME validation')])
                cert = (x509.CertificateBuilder()
                    .subject_name(subject).issuer_name(subject)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - dt.timedelta(minutes=5))
                    .not_valid_after(now + dt.timedelta(hours=1))
                    .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), True)
                    .add_extension(x509.UnrecognizedExtension(ObjectIdentifier('1.3.6.1.5.5.7.1.31'),
                        b'\x04\x20' + hashlib.sha256(response.key_authorization.encode()).digest()), True)
                    .sign(key, hashes.SHA256()))
                certpath, keypath = Path(temporary) / 'cert.pem', Path(temporary) / 'key.pem'
                certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
                keypath.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(certpath, keypath)
                context.set_alpn_protocols(['acme-tls/1'])
                def sni(connection, name, initial):
                    if name != host:
                        return ssl.ALERT_DESCRIPTION_UNRECOGNIZED_NAME
                context.sni_callback = sni
                class Handler(socketserver.BaseRequestHandler):
                    def handle(self):
                        self.request.settimeout(8)
                        try:
                            with context.wrap_socket(self.request, server_side=True):
                                pass
                        except OSError:
                            pass
                class Server(socketserver.ThreadingTCPServer):
                    allow_reuse_address = True
                    daemon_threads = True
                print('Проверка через 443: API временно остановлен; worker продолжает работать.', flush=True)
                stopped = True
                run('systemctl', 'stop', API)
                server = Server(('0.0.0.0', 443), Handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                acme.answer_challenge(challenge, response)
            issued = acme.poll_and_finalize(order, deadline=dt.datetime.now() + dt.timedelta(seconds=110))
        finally:
            if server:
                server.shutdown()
                server.server_close()
            if stopped:
                run('systemctl', 'start', API)
    return issued.fullchain_pem.encode(), key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

def main():
    os.umask(0o077)
    lock = (ROOT / 'dns-renew.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def interrupted(*args):
        raise RuntimeError('Прервано; восстановление настроек')
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGALRM):
        signal.signal(sig, interrupted)
    signal.alarm(240)
    request = urllib.request.Request(
        'http://169.254.169.254/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip',
        headers={'Metadata-Flavor': 'Google'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
        ip = str(ipaddress.IPv4Address(response.read(128).decode().strip()))
    host = 'vm-' + ip.replace('.', '-') + '.sslip.io'
    cfgpath, certpath, keypath = (ROOT / name for name in ('server.json', 'fullchain.pem', 'privkey.pem'))
    cfg = json.loads(cfgpath.read_bytes())
    was_active = active(TIMER) if INSTALL else False
    saved = {}
    try:
        if INSTALL:
            run('systemctl', 'stop', TIMER)
            if active('vm-lab-cert-renew.service'):
                raise RuntimeError('Предыдущее продление ещё работает')
        current = False
        try:
            cert = x509.load_pem_x509_certificate(certpath.read_bytes())
            names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            now = dt.datetime.now(dt.timezone.utc)
            current = (host in names.get_values_for_type(x509.DNSName)
                and cert.not_valid_before_utc <= now
                and cert.not_valid_after_utc > now + dt.timedelta(days=7))
        except (OSError, ValueError, x509.ExtensionNotFound):
            pass
        certificate = None if current else issue(host)
        backup = Path(tempfile.mkdtemp(prefix='dns-backup-', dir=ROOT))
        paths = [cfgpath, certpath, keypath] + ([PROGRAM, UNIT] if INSTALL else [])
        for path in paths:
            if path.is_symlink():
                raise RuntimeError('Unexpected symlink: ' + str(path))
            saved[path] = (path.read_bytes(), path.stat()) if path.exists() else None
            if saved[path]:
                (backup / path.name).write_bytes(saved[path][0])
        print('Резервная копия: ' + str(backup), flush=True)
        if certificate:
            atomic(certpath, certificate[0], saved[certpath][1])
            atomic(keypath, certificate[1], saved[keypath][1])
        cfg.update(public_ip=ip, bind='0.0.0.0', port=443,
            tls_cert=str(certpath), tls_key=str(keypath))
        atomic(cfgpath, json.dumps(cfg).encode(), saved[cfgpath][1])
        run('systemctl', 'restart', API)
        for attempt in range(15):
            try:
                verify(host, cfg)
                break
            except OSError:
                if attempt == 14:
                    raise
                time.sleep(1)
        if INSTALL:
            atomic(PROGRAM, Path(__file__).read_bytes())
            atomic(UNIT, ("[Unit]\nDescription=VM Compute DNS certificate renewal\n"
                "After=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\n"
                "ExecStart=/opt/vm-lab/certbot/bin/python -I /opt/vm-lab/renew_dns.py\n"
                "ExecStopPost=/usr/bin/systemctl start vm-lab-api.service\n"
                "TimeoutStartSec=270\nUMask=0077\n").encode())
            UNIT.chmod(0o644)
            run('systemctl', 'daemon-reload')
            run('systemctl', 'enable', '--now', TIMER)
        print('ГОТОВО: HTTPS и MCP проверены локально на ВМ.', flush=True)
        if INSTALL:
            print('URL для плагина: https://' + host + '/' + cfg['token'] + '/mcp', flush=True)
    except BaseException:
        signal.alarm(0)
        for path, previous in saved.items():
            if previous:
                atomic(path, previous[0], previous[1])
            else:
                path.unlink(missing_ok=True)
        if saved:
            run('systemctl', 'daemon-reload')
            run('systemctl', 'restart', API)
        if INSTALL and was_active:
            run('systemctl', 'start', TIMER)
        print('Ремонт не завершён. Прежние настройки сохранены/восстановлены.', flush=True)
        raise
    finally:
        signal.alarm(0)
        lock.close()

if __name__ == '__main__':
    main()
