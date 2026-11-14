"""Database-only launcher. No API, frontend or assistance imports or processes."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from database.settings import (ConfigurationError, conflicts, initialize, read_jsonc,
                               repair_prefix, validate_operational, validate_provisioning)

ROOT = Path(__file__).resolve().parents[2]
PROJECT = 'ouroboros'


def docker(arguments, env=None, timeout=30):
    try:
        result = subprocess.run(['docker', *arguments], env=env, capture_output=True, timeout=timeout)
        if result.returncode:
            raise ConfigurationError('Docker operation failed; check Docker availability, ownership and configured port (private output suppressed)')
        return result.stdout.decode('utf-8').strip()
    except (OSError, subprocess.TimeoutExpired):
        raise ConfigurationError('Docker is unavailable or the operation timed out') from None


def compose(root):
    return ['compose', '--project-name', PROJECT, '--project-directory', str(root), '--file', str(root/'compose.basic.yaml')]


def environment(root, document, operational):
    env = {key: value for key, value in os.environ.items() if key not in ('PGPASSWORD','POSTGRES_PASSWORD','POSTGRES_PASSWORD_FILE')}
    env.update(DATABASE_NAME=document['database_name'], DATABASE_MASTER=operational['master_user'],
               DATABASE_WORKSPACE=str(root),
               DATABASE_ADDRESS=('['+operational['published_address']+']' if ':' in operational['published_address'] else operational['published_address']),
               DATABASE_PORT=str(operational['published_port']),
               DATABASE_SECRET_FILE=str(root/operational['secret_file']))
    for field, name in (('interval_seconds','INTERVAL'),('timeout_seconds','TIMEOUT'),('retries','RETRIES'),('start_period_seconds','START_PERIOD')):
        env['DATABASE_HEALTH_'+name] = str(operational['healthcheck'][field])
    return env


def owned_resources(root):
    ids = docker(['ps','-aq','--filter','label=com.docker.compose.project='+PROJECT]).splitlines()
    resources = json.loads(docker(['inspect', *ids])) if ids else []
    for resource in resources:
        labels = resource['Config'].get('Labels', {})
        if (labels.get('com.docker.compose.service') not in ('postgresql','api')
                or Path(labels.get('com.docker.compose.project.working_dir','')).resolve() != root
                or Path(labels.get('com.docker.compose.project.config_files','')).resolve() != root/'compose.basic.yaml'):
            raise ConfigurationError('Database Docker project belongs to another workspace; no resource was changed')
    resources = [resource for resource in resources if resource['Config']['Labels']['com.docker.compose.service']=='postgresql']
    volume_ids = docker(['volume','ls','-q','--filter','name=^'+PROJECT+'_installation_v1$']).splitlines()
    if volume_ids:
        volume = json.loads(docker(['volume','inspect',*volume_ids]))[0]
        labels = volume.get('Labels') or {}
        if (labels.get('com.docker.compose.project') != PROJECT
                or labels.get('com.docker.compose.volume') != 'installation_v1'
                or labels.get('org.ouroboros.workspace') != str(root)
                or labels.get('org.ouroboros.baseline') != 'database-v1'):
            raise ConfigurationError('New-installation volume has unconfirmed ownership')
    return resources, bool(volume_ids)


def prepare(root, allow_repair=False, can_repair=False):
    document = initialize(root/'provisioning.jsonc', root/'provisioning.example.jsonc')
    operational = validate_operational(initialize(root/'modules/database/config.jsonc',root/'modules/database/config.example.jsonc'))
    validate_provisioning(document, allow_conflicts=True)
    while conflicts(document):
        print('Duplicate prefixes: '+'; '.join(', '.join(group) for group in conflicts(document)))
        if not (allow_repair and can_repair and sys.stdin.isatty()):
            raise ConfigurationError('Prefix conflict; no structure changed. Correct the unprovisioned configuration')
        table = input('Logical table to correct (confirmed AU/US/QA/FM tables are fixed): ').strip()
        if table not in {table for group in conflicts(document) for table in group}:
            raise ConfigurationError('Choose a table listed in the conflict')
        repair_prefix(root/'provisioning.jsonc',table,input('New unique uppercase prefix: ').strip())
        document = read_jsonc(root/'provisioning.jsonc')
        validate_provisioning(document, allow_conflicts=True)
    return validate_provisioning(document), operational


def connect(root, document, operational):
    import psycopg
    # This dedicated, protected new-installation secret is never the historical secret.
    password = (root/operational['secret_file']).read_text(encoding='utf-8')
    try:
        return psycopg.connect(host=operational['published_address'],port=operational['published_port'],
            dbname=document['database_name'],user=operational['master_user'],password=password,
            connect_timeout=10,autocommit=True, options='-c timezone=UTC -c search_path=pg_catalog')
    finally:
        password = None


def main(root=ROOT, argv=None, with_api=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-only', action='store_true', help='Explicit alias for the default database-only startup')
    parser.add_argument('--check', action='store_true', help='Validate configuration without Docker changes or enrollment')
    args = parser.parse_args(argv)
    root = Path(root).resolve()
    try:
        # Validate both configurations before any PostgreSQL or Docker mutation.
        document, operational = prepare(root, allow_repair=False) if args.check else prepare_initial(root)
        if args.check:
            print('Database JSONC configuration validated. No services or PostgreSQL data changed.')
            return 0
        import psycopg
        import argon2
        from database.secrets import prompt_password, sql_secret
        from database.provision import apply_baseline, bootstrap, has_operator
        env = environment(root, document, operational)
        resources, _ = owned_resources(root)
        own_running = any(resource['State']['Running'] for resource in resources)
        for resource in resources:
            initial = dict(value.split('=',1) for value in resource['Config']['Env'] if '=' in value)
            if initial.get('POSTGRES_DB') != document['database_name']:
                raise ConfigurationError('Database name differs from the existing installation; restore provisioning.jsonc')
        with socket.socket(socket.AF_INET6 if ':' in operational['published_address'] else socket.AF_INET) as probe:
            occupied = probe.connect_ex((operational['published_address'],operational['published_port'])) == 0
        if occupied and not own_running:
            raise ConfigurationError('Port 6669 is occupied. Identify and deliberately stop the previous installation; startup never stops it or chooses another port')
        sql_secret(root, operational['secret_file'])
        # Refuse structural/checksum changes before Compose can recreate an existing service.
        if own_running:
            with connect(root,document,operational) as connection:
                apply_baseline(connection,document,operational['master_user'])
        command = compose(root)
        docker(command+['config','--quiet'],env)
        timeout = operational['startup_timeout_seconds']
        docker(command+['up','--detach','--wait','--wait-timeout',str(timeout),'postgresql'],env,timeout+30)
        with connect(root,document,operational) as connection:
            applied = apply_baseline(connection,document,operational['master_user'])
            if not has_operator(connection,document):
                if not sys.stdin.isatty():
                    raise ConfigurationError('Baseline ready; run again in an interactive terminal to enroll the installation operator')
                app_username = input('Super administrator App User username: ').strip()
                person = input('Super administrator App User display name: ').strip()
                username = input('Linked super administrator API User username: ').strip()
                if not app_username or len(app_username)>128 or not app_username.isprintable():
                    raise ConfigurationError('App User username must contain 1-128 printable characters')
                if not person or len(person)>256 or not username or len(username)>128:
                    raise ConfigurationError('App User display name and API User username must be nonempty and bounded')
                password = prompt_password('New super administrator App Password')
                try:
                    if password == (root/operational['secret_file']).read_text(encoding='utf-8'):
                        raise ConfigurationError('App Password and PostgreSQL Master Password must be different')
                    from database.upgrades import apply as apply_upgrades
                    from database.model import render
                    with connection.transaction():
                        bootstrap(connection,document,person,username,password)
                        apply_upgrades(connection,document)
                        connection.execute(render('UPDATE {app_user} p SET username=%s FROM {super_administrator} s WHERE p.id_app_user=s.id_app_user',document),(app_username,))
                finally:
                    password = None
            from database.upgrades import apply as apply_upgrades
            apply_upgrades(connection,document)
            if with_api:
                # Fresh enrollment prepares the API capability in the trusted host path.
                # The API container only receives the restricted login secret.
                from api.service.launcher import protected_file
                from api.service.migrations import migrate
                runtime_secret=protected_file(root,'api_sql_password')
                migrate(connection,document,runtime_secret.read_text(encoding='utf-8'))
        print('Database ready; '+('baseline applied' if applied else 'registered baseline reused')+'. No API, frontend or assistance started.')
        print(f"SQL administration: {operational['published_address']}:{operational['published_port']} | database={document['database_name']} | schema={document['schema']} | PostgreSQL Master Username={operational['master_user']}")
        return 0
    except KeyboardInterrupt:
        print('Startup cancelled; persistent data preserved.',file=sys.stderr)
        return 130
    except ConfigurationError as error:
        print(str(error),file=sys.stderr)
        return 1
    except ImportError:
        print('Install the independent database dependencies: python -m pip install -r modules/database/requirements.txt',file=sys.stderr)
        return 1
    except Exception:
        print('Database startup failed; check configuration, protected SQL secret and Docker health. Private diagnostics suppressed.',file=sys.stderr)
        return 1


def prepare_initial(root):
    # A volume already allocated by this track is treated conservatively as provisioned.
    # Configuration validation precedes this read-only Docker ownership inspection.
    try:
        return prepare(root)
    except ConfigurationError as error:
        if not str(error).startswith('Prefix conflict;'):
            raise
        _, existing_volume = owned_resources(root)
        return prepare(root, allow_repair=True, can_repair=not existing_volume)
