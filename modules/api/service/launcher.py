"""Host orchestration for Database + API; privileged setup is terminal-only."""
import os
from pathlib import Path
import secrets
import socket
import sys
import psycopg
from database import runtime as database_runtime
from database.secrets import protect, read_password
from database.settings import ConfigurationError
from api.service.config import load
from api.service import tls
from api.service.migrations import LOGIN, inspect_contract, migrate


def protected_file(root,name):
    directory=root/'.secrets'
    path=directory/name
    if directory.is_symlink() or path.is_symlink():
        raise ConfigurationError('Secret paths must not be symbolic links')
    directory.mkdir(mode=0o700,exist_ok=True)
    protect(directory,True)
    if not path.exists():
        with path.open('x',encoding='utf-8') as output:
            if os.name!='nt':
                os.fchmod(output.fileno(),0o600)
            output.write(secrets.token_urlsafe(64))
    protect(path)
    return path


def administrative_setup(root,document,operational,inspect_only=False):
    if not sys.stdin.isatty():
        raise ConfigurationError('API setup requires an interactive terminal with the existing PostgreSQL Master Password')
    password=read_password('Existing PostgreSQL Master Password: ')
    try:
        with psycopg.connect(host=operational['published_address'],port=operational['published_port'],
                             dbname=document['database_name'],user=operational['master_user'],password=password,
                             autocommit=True,connect_timeout=5,options='-c timezone=UTC -c search_path=pg_catalog') as connection:
            registry=inspect_contract(connection,document)
            print('Authenticated live schema and runtime privileges verified. Registered migrations: '+', '.join(sorted(registry)))
            if inspect_only:
                return
            from database.upgrades import apply as apply_upgrades
            apply_upgrades(connection,document)
            secret=protected_file(root,'api_sql_password')
            applied=migrate(connection,document,secret.read_text(encoding='utf-8'))
            print('Additive API migration '+('applied' if applied else 'verified without replay')+'. Bootstrap identity and App Password preserved.')
    finally:
        password=None


def main(root,argv):
    root=Path(root).resolve()
    try:
        settings=load(root)
        document,operational=database_runtime.prepare(root)
        if '--check' in argv:
            print('Database + API configuration validated; no services or SQL data changed.')
            return 0
        if '--api-inspect' in argv or '--api-migrate' in argv:
            administrative_setup(root,document,operational,'--api-inspect' in argv)
            return 0
        certificate,private_key=tls.files(root,settings)
        protect(private_key)
        if database_runtime.main(root,['--database-only'],with_api=True):
            return 1
        # The runtime path never opens the PostgreSQL master secret or uses its SQL role.
        sql_secret=root/'.secrets/api_sql_password'
        if not sql_secret.exists():
            raise ConfigurationError('Restricted SQL login is not prepared; run start.py --api-migrate with existing interactive master credentials')
        protect(sql_secret)
        with psycopg.connect(host=operational['published_address'],port=operational['published_port'],
                             dbname=document['database_name'],user=LOGIN,password=sql_secret.read_text(encoding='utf-8'),connect_timeout=5) as connection:
            inspect_contract(connection,document,require_api=True)
        signing=protected_file(root,'api_token_signing_key')
        env=database_runtime.environment(root,document,operational)
        env.pop('OPENAI_API_KEY',None)
        env.update(API_DATABASE_NAME=document['database_name'],API_SQL_SECRET=str(sql_secret),
                   API_SIGNING_SECRET=str(signing),API_HOST_PORT=str(settings['port']),
                   API_STARTUP_TIMEOUT=str(settings['startup_timeout_seconds']))
        env.update(API_TLS_CERTIFICATE=str(certificate),API_TLS_PRIVATE_KEY=str(private_key))
        command=database_runtime.compose(root)+['--profile','api']
        existing=database_runtime.docker(command+['ps','--quiet','api'],env)
        if existing:
            # Existing container identity must be this exact workspace and Compose file.
            import json
            for resource in json.loads(database_runtime.docker(['inspect',*existing.splitlines()])):
                labels=resource['Config'].get('Labels',{})
                compose_files=labels.get('com.docker.compose.project.config_files','').split(',')
                if (Path(labels.get('com.docker.compose.project.working_dir','')).resolve()!=root
                    or labels.get('com.docker.compose.service')!='api'
                    or [Path(path).resolve() for path in compose_files]!=[root/'compose.basic.yaml']):
                    raise ConfigurationError('API Docker project belongs to another workspace')
        else:
            with socket.socket() as probe:
                if probe.connect_ex((settings['host'],settings['port']))==0:
                    raise ConfigurationError('Approved API port 6969 is occupied; identify its owner. No alternate port or automatic stop is allowed')
        database_runtime.docker(command+['build','api'],env,600)
        database_runtime.docker(command+['up','--detach','--force-recreate','--wait','--wait-timeout',str(settings['startup_timeout_seconds']),'api'],env,settings['startup_timeout_seconds']+30)
        print('Database + API ready. Swagger: '+tls.origin(settings)+'/docs')
        return 0
    except KeyboardInterrupt:
        print('API startup cancelled; existing data preserved.',file=sys.stderr)
        return 130
    except ConfigurationError as error:
        print(str(error),file=sys.stderr)
        return 1
    except psycopg.Error as error:
        state=error.sqlstate or 'unavailable'
        messages={'28P01':'PostgreSQL rejected the PostgreSQL Master Password or API runtime SQL credential',
                  '3D000':'Configured database does not exist',
                  '42P01':'A required registered table is missing from the configured schema',
                  '42703':'A required column is missing from the live schema',
                  '42501':'The SQL account lacks a required inspection or migration privilege'}
        reason=messages.get(state,'PostgreSQL connection or contract inspection failed')
        # Classify libpq connection failures without emitting their private message.
        private_message=str(error).lower()
        for fragment,safe_reason in (
            ('password authentication failed','PostgreSQL Master Username ouroboros_master requires its PostgreSQL Master Password'),
            ('no password supplied','PostgreSQL requires a nonempty PostgreSQL Master Password'),
            ('connection refused','PostgreSQL refused the configured TCP connection'),
            ('timeout expired','The PostgreSQL TCP connection timed out'),
            ('no pg_hba.conf entry','PostgreSQL host authentication does not allow this connection'),
            ('could not translate host','The configured PostgreSQL hostname could not be resolved')):
            if fragment in private_message:
                reason=safe_reason
                break
        print(reason+
              f' (category={type(error).__name__}, SQLSTATE={state}). No credential or SQL values were logged.',file=sys.stderr)
        return 1
    except Exception as error:
        print(f'API startup failed (category={type(error).__name__}); check module configuration and Docker health. Private diagnostics suppressed.',file=sys.stderr)
        return 1
