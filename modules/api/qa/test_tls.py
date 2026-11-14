"""TLS preflight regression checks using disposable local certificates."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from api.service import tls
from database.settings import ConfigurationError


def certificate(directory):
    openssl = shutil.which('openssl')
    if openssl is None:
        candidate = Path('C:/Program Files/Git/usr/bin/openssl.exe')
        if candidate.is_file():
            openssl = str(candidate)
    if openssl is None:
        raise RuntimeError('OpenSSL is required to generate disposable TLS test fixtures')
    cert = Path(directory) / 'certificate.pem'
    key = Path(directory) / 'private-key.pem'
    result = subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                             '-keyout', str(key), '-out', str(cert), '-days', '1',
                             '-subj', '/CN=localhost', '-addext',
                             'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                            capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Disposable TLS fixture creation failed')
    return cert, key


class TLSTests(unittest.TestCase):
    def test_trusted_certificate_and_both_names(self):
        with tempfile.TemporaryDirectory() as directory:
            cert, key = certificate(directory)
            for name in ('localhost', '127.0.0.1'):
                tls.validate(cert, key, name)

    def test_missing_invalid_key_and_wrong_hostname_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            cert, key = certificate(directory)
            for cert_path, key_path, name in ((cert, key, 'wrong.example'),
                                               (cert, Path(directory)/'missing', 'localhost'),
                                               (Path(directory)/'missing', key, 'localhost')):
                with self.assertRaisesRegex(ConfigurationError, 'Valid TLS certificate'):
                    tls.validate(cert_path, key_path, name)
            key.write_text('invalid private material', encoding='utf-8')
            with self.assertRaises(ConfigurationError):
                tls.validate(cert, key, 'localhost')

    def test_mismatched_private_key_fails(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            cert,_ = certificate(first)
            _,key = certificate(second)
            with self.assertRaises(ConfigurationError):
                tls.validate(cert, key, 'localhost')


if __name__ == '__main__':
    unittest.main()
