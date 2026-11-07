import contextlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from cryptography import x509
from cryptography.x509.oid import ObjectIdentifier
from cryptography.hazmat.primitives.asymmetric import rsa
from acme import messages
import josepy

spec = importlib.util.spec_from_file_location('repair', Path(__file__).with_name('vm_repair_dns.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

HOST = 'vm-158-160-130-220.sslip.io'

class RepairTests(unittest.TestCase):
    def exercise(self, supported, fail=False):
        calls, observed, listeners = [], {}, []
        class CA:
            @staticmethod
            def get_directory(url, network):
                return {}
            def __init__(self, *args):
                pass
            def new_order(self, csr, **kwargs):
                observed['kwargs'] = kwargs
                names = x509.load_pem_x509_csr(csr).extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                selftest.assertEqual(names.get_values_for_type(x509.DNSName), [HOST])
                selftest.assertEqual(names.get_values_for_type(x509.IPAddress), [])
                raw = {'type': 'tls-alpn-01' if supported else 'http-01',
                    'token': josepy.encode_b64jose(b'1' * 32),
                    'url': 'https://acme.invalid/chall/1', 'status': 'pending'}
                auth = types.SimpleNamespace(body=messages.Authorization.from_json({
                    'identifier': {'type': 'dns', 'value': HOST}, 'status': 'pending',
                    'challenges': [raw, dict(raw, type='future-method-01')]}))
                return types.SimpleNamespace(authorizations=[auth])
            def answer_challenge(self, challenge, response):
                selftest.assertEqual(response.to_json(), {})
                selftest.assertTrue(response.verify(challenge.chall, account_key.public_key()))
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.set_alpn_protocols(['acme-tls/1'])
                with context.wrap_socket(socket.create_connection(listeners[-1].server_address, timeout=2),
                                         server_hostname=HOST) as stream:
                    selftest.assertEqual(stream.selected_alpn_protocol(), 'acme-tls/1')
                    cert = x509.load_der_x509_certificate(stream.getpeercert(binary_form=True))
                    ext = cert.extensions.get_extension_for_oid(ObjectIdentifier('1.3.6.1.5.5.7.1.31'))
                    selftest.assertTrue(ext.critical)
                    selftest.assertEqual(ext.value.value,
                        b'\x04\x20' + module.hashlib.sha256(response.key_authorization.encode()).digest())
                    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                    selftest.assertTrue(san.critical)
                    selftest.assertEqual(san.value.get_values_for_type(x509.DNSName), [HOST])
                with selftest.assertRaises(ssl.SSLError):
                    with context.wrap_socket(socket.create_connection(listeners[-1].server_address, timeout=2),
                                             server_hostname='wrong.example'):
                        pass
                observed['validated'] = True
            def poll_and_finalize(self, order, deadline):
                if fail:
                    raise RuntimeError('CA validation failed')
                return types.SimpleNamespace(fullchain_pem='issued chain')
        real_server = module.socketserver.ThreadingTCPServer
        class LocalServer(real_server):
            def __init__(self, address, handler):
                super().__init__(('127.0.0.1', 0), handler)
                listeners.append(self)
        selftest = self
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            account = root / 'acme/accounts/acme-v02.api.letsencrypt.org/directory/one'
            account.mkdir(parents=True)
            account_key = josepy.JWKRSA(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))
            (account / 'regr.json').write_text(messages.RegistrationResource(
                uri='https://acme.invalid/acct/1', body=messages.Registration()).json_dumps())
            (account / 'private_key.json').write_text(account_key.json_dumps())
            network = types.SimpleNamespace(ClientNetwork=lambda *a, **k: None, ClientV2=CA)
            with patch.object(module, 'ROOT', root), patch.object(module, 'client', network), \
                 patch.object(module, 'run', side_effect=lambda *a: calls.append(a)), \
                 patch.object(module.socketserver, 'ThreadingTCPServer', LocalServer), \
                 contextlib.redirect_stdout(io.StringIO()):
                if not supported:
                    with self.assertRaisesRegex(RuntimeError, 'CA не предложил'):
                        module.issue(HOST)
                    self.assertEqual(calls, [])
                elif fail:
                    with self.assertRaisesRegex(RuntimeError, 'CA validation failed'):
                        module.issue(HOST)
                else:
                    self.assertEqual(module.issue(HOST)[0], b'issued chain')
        self.assertEqual(observed['kwargs'], {})
        if supported:
            self.assertTrue(observed['validated'])
            self.assertEqual(calls, [('systemctl', 'stop', module.API), ('systemctl', 'start', module.API)])
            self.assertEqual(listeners[-1].socket.fileno(), -1)

    def test_dns_only_order_and_real_alpn_handshake(self):
        self.exercise(True)

    def test_no_alpn_does_not_stop_api(self):
        self.exercise(False)

    def test_failed_validation_restarts_api(self):
        self.exercise(True, fail=True)

    def test_mcp_failure_restores_config_cert_and_program(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = {'public_ip': '158.160.146.58', 'token': 'secret'}
            originals = {'server.json': json.dumps(cfg).encode(), 'fullchain.pem': b'old cert',
                         'privkey.pem': b'old key', 'renew_dns.py': b'old program', 'unit.service': b'old unit'}
            for name, data in originals.items():
                (root / name).write_bytes(data)
                (root / name).chmod(0o400)
            calls = []
            class Metadata:
                def open(self, *args, **kwargs):
                    return io.BytesIO(b'158.160.130.220')
            with patch.object(module, 'ROOT', root), patch.object(module, 'PROGRAM', root / 'renew_dns.py'), \
                 patch.object(module, 'UNIT', root / 'unit.service'), patch.object(module, 'INSTALL', True), \
                 patch.object(module, 'active', side_effect=lambda name: name == module.TIMER), \
                 patch.object(module, 'run', side_effect=lambda *a: calls.append(a)), \
                 patch.object(module, 'issue', return_value=(b'new cert', b'new key')), \
                 patch.object(module, 'verify', side_effect=RuntimeError('MCP rejected')), \
                 patch.object(module.urllib.request, 'build_opener', return_value=Metadata()), \
                 patch.object(module.signal, 'signal'), patch.object(module.signal, 'alarm'), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'MCP rejected'):
                    module.main()
            for name, data in originals.items():
                self.assertEqual((root / name).read_bytes(), data)
                self.assertEqual((root / name).stat().st_mode & 0o777, 0o400)
            self.assertEqual(calls[-1], ('systemctl', 'start', module.TIMER))
            self.assertFalse(any('vm-lab-worker.service' in c for c in calls))

if __name__ == '__main__':
    unittest.main()
