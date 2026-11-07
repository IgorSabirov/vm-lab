#!/usr/bin/env python3
"""Run INSIDE the existing vm-compute VM: sudo python3 -I reconnect_vm.py NEW_IP.

Uses the successful 2026-11-07 Certbot HTTP-01 sequence. No installation,
worker restart, credential rotation or data removal. See VM_CONNECTION_RUNBOOK.md.
"""
import argparse
import fcntl
import http.client
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import tempfile
import time

ROOT = Path('/etc/vm-compute')
CONFIG = ROOT / 'server.json'
CERTBOT = Path('/opt/vm-compute/certbot/bin/certbot')
HOOK = Path('/opt/vm-compute/deploy_cert.py')
TIMER = 'vm-compute-cert-renew.timer'
API = 'vm-compute-api.service'
WORKER = 'vm-compute-worker.service'


def run(*args, timeout=30, check=True, **kwargs):
    return subprocess.run(args, check=check, timeout=timeout, **kwargs)


def public_ip():
    connection = http.client.HTTPConnection('169.254.169.254', timeout=5)
    try:
        connection.request('GET', '/computeMetadata/v1/instance/network-interfaces/'
                           '0/access-configs/0/external-ip',
                           headers={'Metadata-Flavor': 'Google'})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError('Не удалось прочитать публичный IP из метаданных ВМ')
        return str(ipaddress.IPv4Address(response.read(128).decode().strip()))
    finally:
        connection.close()


def save_config(cfg):
    info = CONFIG.stat()
    fd, temporary = tempfile.mkstemp(prefix='.server-', dir=CONFIG.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            os.fchown(output.fileno(), info.st_uid, info.st_gid)
            os.fchmod(output.fileno(), info.st_mode & 0o777)
            json.dump(cfg, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, CONFIG)
    finally:
        Path(temporary).unlink(missing_ok=True)


def rpc(host, token, method, params=None):
    connection = http.client.HTTPSConnection(host, timeout=5)
    try:
        # Local socket avoids NAT hairpin; CA trust and new hostname ARE verified.
        connection.sock = ssl.create_default_context().wrap_socket(
            socket.create_connection(('127.0.0.1', 443), timeout=5),
            server_hostname=host)
        connection.request('POST', '/' + token + '/mcp',
                           json.dumps({'jsonrpc': '2.0', 'id': 1,
                                       'method': method, 'params': params or {}}),
                           {'Content-Type': 'application/json',
                            'Accept': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError('MCP HTTP ' + str(response.status))
        body = json.loads(response.read())
        if 'error' in body:
            raise RuntimeError('MCP вернул ошибку для ' + method)
        return body['result']
    finally:
        connection.close()


def verify(host, token):
    for attempt in range(15):
        try:
            names = {item['name'] for item in rpc(host, token, 'tools/list')['tools']}
            break
        except (ConnectionRefusedError, ConnectionResetError):
            if attempt == 14:
                raise
            time.sleep(1)
    if not {'write_work_file', 'start_python_job', 'job_status'} <= names:
        raise RuntimeError('Отсутствуют ожидаемые инструменты MCP')
    result = rpc(host, token, 'tools/call', {'name': 'work_status', 'arguments': {}})
    if result.get('isError') or not json.loads(result['content'][0]['text'])['worker']['responsive']:
        raise RuntimeError('Worker не отвечает; научный запуск не выполнялся')


def reconnect(ip):
    ip = str(ipaddress.IPv4Address(ip))
    if public_ip() != ip:
        raise RuntimeError('Указанный IP не совпадает с текущим адресом этой ВМ')
    for path in (CONFIG, CERTBOT, HOOK):
        if not path.is_file():
            raise RuntimeError('Нет установленного компонента: ' + str(path))
    cfg = json.loads(CONFIG.read_text())
    if not isinstance(cfg.get('token'), str) or not cfg['token']:
        raise RuntimeError('В конфигурации нет токена')
    if (cfg.get('bind') != '0.0.0.0' or cfg.get('port') != 443
            or cfg.get('tls_cert') != str(ROOT / 'fullchain.pem')
            or cfg.get('tls_key') != str(ROOT / 'privkey.pem')):
        raise RuntimeError('Это другая схема установки; настройки не изменены')
    host = 'vm-' + ip.replace('.', '-') + '.sslip.io'
    timer_was_active = run('systemctl', 'is-active', '--quiet', TIMER,
                           check=False).returncode == 0
    success = False
    try:
        run('systemctl', 'stop', TIMER)
        state = run('systemctl', 'show', 'vm-compute-cert-renew.service',
                    '--property=ActiveState', '--value', capture_output=True,
                    text=True).stdout.strip()
        if state not in ('inactive', 'failed'):
            raise RuntimeError('Уже выполняется продление сертификата; дождитесь его окончания')
        print('Одна попытка Certbot HTTP-01 для ' + host, flush=True)
        run(str(CERTBOT), 'certonly', '--non-interactive', '--agree-tos',
            '--register-unsafely-without-email', '--no-eff-email',
            '--standalone', '--http-01-address', '0.0.0.0',
            '--preferred-challenges', 'http', '--preferred-profile', 'shortlived',
            '--cert-name', 'vm-compute',
            '--force-renewal' if cfg.get('public_ip') != ip else '--keep-until-expiring',
            '--ip-address', ip, '-d', host,
            '--config-dir', str(ROOT / 'acme'),
            '--work-dir', '/var/lib/vm-compute/acme',
            '--logs-dir', '/var/log/vm-compute-acme',
            '--deploy-hook', '/usr/bin/python3 ' + str(HOOK), timeout=240)
        # Also deploy when Certbot retained an already-valid certificate.
        run('/usr/bin/python3', str(HOOK))
        cfg['public_ip'] = ip
        save_config(cfg)
        run('systemctl', 'restart', API)
        run('systemctl', 'start', WORKER)  # active worker and its job are not restarted
        verify(host, cfg['token'])
        run('systemctl', 'enable', API, WORKER, TIMER)
        success = True
    finally:
        if timer_was_active or success:
            run('systemctl', 'start', TIMER)
    print('ГОТОВО: HTTPS с проверкой имени, MCP и worker проверены локально.')
    print('URL ДЛЯ ПЛАГИНА: https://' + host + '/' + cfg['token'] + '/mcp')
    print('После обновления подключения ChatGPT проверить через него work_status.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ip', type=ipaddress.IPv4Address)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Запустите с sudo внутри ВМ.')
    os.umask(0o077)
    def interrupted(signum, _frame):
        raise RuntimeError('Прервано сигналом ' + str(signum))
    signal.signal(signal.SIGHUP, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    with open('/run/lock/vm-compute-reconnect.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            reconnect(str(args.ip))
        except Exception as error:
            print('ПЕРЕПОДКЛЮЧЕНИЕ НЕ ЗАВЕРШЕНО: ' + str(error), flush=True)
            print('Повторных запросов CA и переустановки нет. См. VM_CONNECTION_RUNBOOK.md.', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()
