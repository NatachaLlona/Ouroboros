"""Use operator-selected QA ports only; never silently allocate alternatives."""
import os
import socket
import unittest


def approved_port(kind='database'):
    variable = {'database': 'OUROBOROS_QA_DB_PORT', 'api': 'OUROBOROS_QA_API_PORT',
                'derived': 'OUROBOROS_QA_DERIVED_DB_PORT'}[kind]
    value = os.environ.get(variable)
    if not value or not value.isdecimal() or not 1 <= int(value) <= 65535:
        raise unittest.SkipTest('Select an explicit disposable port through ' + variable)
    port = int(value)
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            raise RuntimeError('Selected QA port is occupied; no alternative was selected') from None
    return port
