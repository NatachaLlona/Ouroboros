"""Interactive SQL administrator replacement, independent of SaaS identities."""
import json
import os
from pathlib import Path
import sys
import tempfile

import psycopg
from psycopg import sql

from database.model import render
from database.provision import BASELINE_VERSION, baseline_checksum
from database.secrets import protect, read_password, prompt_password
from database.settings import ConfigurationError, identifier, structural_identity

IDENTITY = '.secrets/database_master_identity.json'
JOURNAL = '.secrets/database_master_transition.json'
PENDING = '.secrets/database_sql_password.pending'
LOCK = 719230821
RESERVED = {'ouroboros_owner', 'ouroboros_runtime', 'ouroboros_api_login'}


def role_name(value):
    identifier(value)
    if value in RESERVED:
        raise ConfigurationError('PostgreSQL Master Username conflicts with a protected SQL role')
    return value


def read_state(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise ConfigurationError('Administrator state must not be a symbolic link')
    if not path.exists():
        return None
    protect(path)
    try:
        if path.stat().st_size > 4096:
            raise ValueError
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)
        if type(data) is not dict or type(data.get('version')) is not int or data.get('version') != 1:
            raise ValueError
        return data
    except (ValueError, OSError):
        raise ConfigurationError('Invalid administrator transition state; preserve the protected recovery files') from None


def atomic_write(path, value):
    """Protect temporary contents before writing, then replace on the same volume."""
    if path.is_symlink() or path.parent.is_symlink():
        raise ConfigurationError('Administrator files must not be symbolic links')
    path.parent.mkdir(mode=0o700, exist_ok=True)
    protect(path.parent, True)
    temporary = None
    try:
        descriptor, filename = tempfile.mkstemp(prefix='.master-', dir=path.parent)
        temporary = Path(filename)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as output:
            protect(temporary)
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def state_write(path, data):
    atomic_write(path, json.dumps({'version': 1, **data}, sort_keys=True))


def remember(root, name):
    role_name(name)
    current = read_state(root / IDENTITY)
    if current is not None and current != {'version': 1, 'master_user': name}:
        raise ConfigurationError('Administrator identity changed; complete the interactive transition first')
    if current is None:
        state_write(root / IDENTITY, {'master_user': name})


def previous_master(root, resources, desired):
    current = read_state(root / IDENTITY)
    if current is not None:
        if set(current) != {'version', 'master_user'}:
            raise ConfigurationError('Invalid PostgreSQL administrator identity state')
        return role_name(current['master_user'])
    names = set()
    for resource in resources:
        env = dict(item.split('=', 1) for item in resource['Config']['Env'] if '=' in item)
        if env.get('POSTGRES_USER'):
            names.add(role_name(env['POSTGRES_USER']))
    if len(names) > 1:
        raise ConfigurationError('Conflicting PostgreSQL administrator metadata')
    return next(iter(names)) if names else desired


def connection(document, operational, name, password):
    return psycopg.connect(host=operational['published_address'], port=operational['published_port'],
                          dbname=document['database_name'], user=name, password=password,
                          connect_timeout=10, autocommit=True,
                          options='-c timezone=UTC -c search_path=pg_catalog')


def verify(connection, document):
    if connection.execute('SELECT rolsuper AND rolcanlogin FROM pg_roles WHERE rolname=session_user').fetchone() != (True,):
        raise ConfigurationError('An authenticated PostgreSQL superuser with LOGIN is required')
    fingerprint, structure = structural_identity(document)
    row = connection.execute(render('SELECT structural_hash,structural_mapping FROM {provisioning_registry}', document)).fetchone()
    baseline = connection.execute(render('SELECT checksum FROM {foundation_migration} WHERE version=%s', document), (BASELINE_VERSION,)).fetchone()
    if row != (fingerprint, structure) or baseline != (baseline_checksum(document),):
        raise ConfigurationError('Registered installation or baseline differs; administrator replacement refused')


def evidence(connection, document, target, action):
    """Administrative evidence contains role names only, never credentials or SQL."""
    event = connection.execute(render('INSERT INTO {api_audit_log}(resource,target_id,action) VALUES(%s,%s,%s) RETURNING id_api_audit_log', document),
                               ('sql_master', target, action)).fetchone()[0]
    connection.execute(render('INSERT INTO {record_version}(id_api_audit_log,resource,record_id,version_number,operation) SELECT %s,%s,%s,coalesce(max(version_number),0)+1,%s FROM {record_version} WHERE resource=%s AND record_id=%s', document),
                       (event, 'sql_master', target, action, 'sql_master', target))


def quiet(connection):
    # Password verifiers must not enter server statement/error logs either.
    connection.execute("SET LOCAL log_statement='none'")
    connection.execute("SET LOCAL log_min_error_statement='panic'")
    connection.execute("SET LOCAL log_min_duration_statement=-1")
    connection.execute("SET LOCAL log_min_duration_sample=-1")
    connection.execute("SET LOCAL log_transaction_sample_rate=0")
    connection.execute("SET LOCAL log_parameter_max_length=0")
    connection.execute("SET LOCAL log_parameter_max_length_on_error=0")


def create(connection, document, target, password):
    verify(connection, document)
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
        verify(connection, document)
        if connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (target,)).fetchone():
            raise ConfigurationError('Requested SQL role already exists; no role was overwritten')
        quiet(connection)
        # libpq computes SCRAM locally: plaintext never appears in SQL text.
        verifier = connection.pgconn.encrypt_password(password.encode(), target.encode(), b'scram-sha-256').decode()
        try:
            connection.execute(sql.SQL('CREATE ROLE {} WITH LOGIN SUPERUSER CREATEDB CREATEROLE INHERIT REPLICATION BYPASSRLS PASSWORD {}').format(sql.Identifier(target), sql.Literal(verifier)))
            connection.execute(sql.SQL('GRANT ouroboros_owner TO {}').format(sql.Identifier(target)))
            connection.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET search_path TO pg_catalog, {}').format(sql.Identifier(target), sql.Identifier(document['database_name']), sql.Identifier(document['schema'])))
            evidence(connection, document, target, 'INSERT')
        finally:
            verifier = None


def retire(connection, document, previous):
    """Offer confirmed deletion, or LOGIN deactivation for the pinned initdb role."""
    role_name(previous)
    verify(connection, document)
    row = connection.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (previous,)).fetchone()
    if row is None:
        return
    if row[0] == 10:
        print('The initial PostgreSQL master is a protected system role and cannot be deleted. Its LOGIN can be disabled; ownership and data remain intact.')
        phrase, action = 'DISABLE ' + previous, 'UPDATE'
    else:
        print('Deleting the previous SQL master will not delete owned objects. Dependencies can prevent deletion; no DROP OWNED or CASCADE is performed.')
        phrase, action = 'DELETE ' + previous, 'DELETE'
    if input('Type '+phrase+' to retire the previous SQL master, or Enter to keep it: ').strip() != phrase:
        print('Previous SQL master retained. The new master is active.')
        return
    try:
        with connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            verify(connection, document)
            if connection.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (previous,)).fetchone() != row:
                raise ConfigurationError('Previous SQL role identity changed; retirement refused')
            # Never terminate other administrator sessions automatically.
            if connection.execute("SELECT 1 FROM pg_stat_activity WHERE usename=%s AND backend_type='client backend' AND pid<>pg_backend_pid()", (previous,)).fetchone():
                raise ConfigurationError('Previous SQL master has active sessions; close them before retiring it')
            if row[0] == 10:
                quiet(connection)
                connection.execute(sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(previous)))
            else:
                connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(previous)))
            evidence(connection, document, previous, action)
    except psycopg.Error:
        raise ConfigurationError('Previous SQL master has dependencies or could not be retired. The new master is active; previous role and data were preserved') from None
    print('Previous SQL master '+('LOGIN disabled. Existing object ownership preserved.' if row[0] == 10 else 'deleted. No business data deleted.'))


def ensure(root, document, operational, resources):
    """Resume a journaled handover; no role change in unattended startup."""
    root = Path(root)
    target = role_name(operational['master_user'])
    journal = read_state(root / JOURNAL)
    previous = previous_master(root, resources, target)
    if journal:
        if set(journal) != {'version', 'previous', 'target'}:
            raise ConfigurationError('Invalid administrator transition journal')
        previous = role_name(journal['previous'])
        if role_name(journal['target']) != target or previous == target:
            raise ConfigurationError('Pending SQL master transition: restore its target master_user and rerun interactively')
    if previous == target and journal is None:
        return
    if not sys.stdin.isatty():
        raise ConfigurationError('SQL master change requires an interactive terminal, current master authentication and a new password; no role was changed')
    print('PostgreSQL Master Username changed from '+previous+' to '+target+'. SaaS users and data will not be recreated.')
    password = None
    current_password = None
    try:
        if journal:
            candidate = root / PENDING if (root / PENDING).exists() else root / operational['secret_file']
            if candidate.is_symlink() or not candidate.is_file():
                raise ConfigurationError('Protected transition password is unavailable; preserve recovery state')
            protect(candidate)
            password = candidate.read_text(encoding='utf-8')
            # A committed role can be recovered without changing its password again.
            try:
                with connection(document, operational, target, password) as recovered:
                    verify(recovered, document)
            except psycopg.Error:
                password = None
        if password is None:
            current_password = read_password('Existing PostgreSQL Master Password for '+previous+': ')
            with connection(document, operational, previous, current_password) as administrator:
                verify(administrator, document)
                administrator.execute('SELECT pg_advisory_lock(%s)', (LOCK,))
                current = read_state(root / IDENTITY)
                if current and current.get('master_user') not in (previous, target):
                    raise ConfigurationError('Another administrator transition completed; reload configuration before continuing')
                pending = read_state(root / JOURNAL)
                if pending and (pending.get('previous'), pending.get('target')) != (previous, target):
                    raise ConfigurationError('Another SQL master transition is pending; preserve its recovery files')
                if administrator.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (target,)).fetchone():
                    raise ConfigurationError('Requested SQL role already exists; no credentials or privileges were overwritten')
                password = prompt_password('New PostgreSQL Master Password for '+target)
                if input('Type CREATE '+target+' to create the new SQL master: ').strip() != 'CREATE '+target:
                    raise ConfigurationError('SQL master creation cancelled; previous master and data preserved')
                atomic_write(root / PENDING, password)
                state_write(root / JOURNAL, {'previous': previous, 'target': target})
                create(administrator, document, target, password)
        with connection(document, operational, target, password) as replacement:
            verify(replacement, document)
            replacement.execute('SELECT pg_advisory_lock(%s)', (LOCK,))
            # Publish only after independent TCP authentication. Recovery journal
            # remains until the whole file/identity handover and retirement offer finish.
            atomic_write(root / operational['secret_file'], password)
            state_write(root / IDENTITY, {'master_user': target})
            print('New SQL master authenticated; protected startup credentials updated.')
            retire(replacement, document, previous)
            (root / PENDING).unlink(missing_ok=True)
            (root / JOURNAL).unlink(missing_ok=True)
    except psycopg.Error:
        raise ConfigurationError('SQL master transition failed authentication or SQL validation. No private diagnostics were logged; preserve recovery files and rerun interactively') from None
    finally:
        password = None
        current_password = None
