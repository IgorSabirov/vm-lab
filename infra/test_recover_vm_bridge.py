"""Offline integration checks; never contact a CA or modify host services."""
import importlib.util
import io
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import http.server

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('recover_vm_bridge.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def test_preserve_existing_token_and_reject_ambiguous_config(self):
        token = 'ab' * 32
        config = {'public_ip': '192.0.2.1', 'token': token, 'other': {'threads': 7}}
        self.assertEqual(recovery.token_from(config), token)
        self.assertEqual(config['other'], {'threads': 7})
        with self.assertRaises(RuntimeError):
            recovery.token_from({'a': token, 'b': 'cd' * 32})

    def test_http_challenge_is_served_and_private_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            challenge = root / '.well-known/acme-challenge'
            challenge.mkdir(parents=True)
            (challenge / 'check').write_text('expected.validation')
            (root / 'secret').write_text('PRIVATE')
            (challenge / 'link').symlink_to(root / 'secret')
            server = recovery.ChallengeServer(('127.0.0.1', 0), recovery.challenge_handler(root))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                base = f'http://127.0.0.1:{server.server_port}'
                with opener.open(base + '/.well-known/acme-challenge/check', timeout=3) as response:
                    self.assertEqual(response.read(), b'expected.validation')
                for path in ('/secret', '/.well-known/acme-challenge/../../secret',
                             '/.well-known/acme-challenge/link'):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(base + path, timeout=3)
                    self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_backup_rolls_back_replaced_and_created_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'server.json'
            created = root / 'new.service'
            original = b'{"token":"keep","public_ip":"old"}\n'
            config.write_bytes(original)
            original_mode = config.stat().st_mode
            # Only bypass production root-directory ownership checks in the test sandbox.
            with patch.object(recovery, 'trusted_directory'), patch.object(recovery.os, 'fchown'), \
                 patch.object(recovery.tempfile, 'mkdtemp', return_value=directory):
                backup = recovery.Backup()
                backup.save(config)
                backup.save(created)
                recovery.atomic_write(config, b'changed', config.stat())
                recovery.atomic_write(created, b'new')
                backup.restore()
            self.assertEqual(config.read_bytes(), original)
            self.assertEqual(config.stat().st_mode, original_mode)
            self.assertFalse(created.exists())

    def test_verified_tls_and_mcp_json_and_sse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cert = root / 'cert.pem'
            key = root / 'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-days', '4',
                            '-subj', '/CN=bridge.test', '-addext', 'subjectAltName=DNS:bridge.test'],
                           check=True, capture_output=True)
            lineage = root / 'live/vm-lab'
            lineage.mkdir(parents=True)
            (lineage / 'fullchain.pem').write_bytes(cert.read_bytes())
            with patch.object(recovery, 'ACME', root):
                self.assertTrue(recovery.usable_certificate('bridge.test'))
                self.assertFalse(recovery.usable_certificate('wrong.test'))
            real_connect = socket.create_connection
            real_context = ssl.create_default_context
            token = 'ab' * 32
            for sse in (False, True):
                calls = []
                class Handler(http.server.BaseHTTPRequestHandler):
                    def log_message(self, *_args):
                        pass
                    def do_POST(self):
                        if self.path != '/' + token + '/mcp':
                            self.send_error(403)
                            return
                        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        calls.append(payload['method'])
                        if 'id' not in payload:
                            self.send_response(202)
                            self.end_headers()
                            return
                        result = {'protocolVersion': '2025-03-26'} if payload['id'] == 1 else {
                            'tools': [{'name': n} for n in ('start_python_job', 'write_work_file', 'cancel_job')]}
                        body = json.dumps({'jsonrpc': '2.0', 'id': payload['id'], 'result': result}).encode()
                        if sse:
                            body = b'event: message\ndata: ' + body + b'\n\n'
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream' if sse else 'application/json')
                        self.send_header('Content-Length', str(len(body)))
                        self.send_header('Mcp-Session-Id', 'test-session')
                        self.end_headers()
                        self.wfile.write(body)
                server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(cert, key)
                server.socket = context.wrap_socket(server.socket, server_side=True)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    with patch.object(recovery.ssl, 'create_default_context',
                                      side_effect=lambda: real_context(cafile=str(cert))), \
                         patch.object(recovery.socket, 'create_connection',
                                      side_effect=lambda *_a, **_k: real_connect(('127.0.0.1', server.server_port), timeout=3)):
                        recovery.check_mcp('bridge.test', token)
                        with self.assertRaises(ssl.SSLCertVerificationError):
                            recovery.check_mcp('wrong.test', token)
                    self.assertEqual(calls, ['initialize', 'notifications/initialized', 'tools/list'])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


if __name__ == '__main__':
    unittest.main()
