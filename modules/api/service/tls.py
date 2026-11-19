"""Fail-closed TLS material validation without opening a network listener."""
from pathlib import Path
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor

from database.settings import ConfigurationError


TLS_ERROR = ('Valid TLS certificate and matching unencrypted PEM key are required. '
             'Configure tls.certificate_file, tls.private_key_file and tls.server_name '
             'in modules/api/config.jsonc. Follow modules/api/API.md to prepare and trust the certificate.')


def validate(certificate, private_key, server_name):
    """Check key correspondence, certificate lifetime and SAN with pinned trust."""
    try:
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.minimum_version = ssl.TLSVersion.TLSv1_2
        # An explicit callback prevents an encrypted key from prompting on stdin.
        server.load_cert_chain(str(certificate), str(private_key), password=lambda: '')
        client = ssl.create_default_context(cafile=str(certificate))
        client.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        client.hostname_checks_common_name = False
        left, right = socket.socketpair()
        left.settimeout(5)
        right.settimeout(5)

        def accept():
            with left, server.wrap_socket(left, server_side=True) as connection:
                connection.sendall(b'1')

        with right, ThreadPoolExecutor(max_workers=1) as executor:
            handshake = executor.submit(accept)
            with client.wrap_socket(right, server_hostname=server_name) as connection:
                if connection.recv(1) != b'1':
                    raise ValueError('TLS validation handshake failed')
            handshake.result()
    except (OSError, ValueError, ssl.SSLError):
        raise ConfigurationError(TLS_ERROR) from None


def files(root, settings):
    paths = tuple((Path(root) / settings['tls'][field]).resolve()
                  for field in ('certificate_file', 'private_key_file'))
    validate(*paths, settings['tls']['server_name'])
    return paths


def origin(settings):
    return f"https://{settings['tls']['server_name']}:{settings['port']}"
