"""Standard-library-only launcher for the four containerized modules."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from app.config import ConfigurationError
from app.database import DatabaseError

ROOT = Path(__file__).resolve().parents[1]


class StartupError(RuntimeError):
    pass


def read_document(path):
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(document, dict):
            raise ValueError
        return document
    except (OSError, ValueError, TypeError):
        raise StartupError('Invalid or missing JSON configuration: '+str(path)) from None


def initialize(path, document):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as output:
            json.dump(document, output, ensure_ascii=False, indent=2)
            output.write('\n')
    return read_document(path)


def prepare(root):
    """Adopt existing non-secret settings once; never overwrite local module files."""
    legacy_path = root/'.app.config'
    if not legacy_path.exists():
        legacy_path = root/'modules/base/config/.config.json'
    legacy = read_document(legacy_path if legacy_path.exists() else root/'modules/base/config.example.json')
    base = dict(legacy)
    base.pop('transcription', None)
    if base.get('auth', {}).get('password_hash'):
        raise StartupError('Legacy credentials require authenticated migration before modularization; original configuration was preserved')
    previous_base = root/'modules/base/.config.json'
    base = initialize(root/'modules/base/config/.config.json', read_document(previous_base) if previous_base.exists() else base)
    database = initialize(root/'modules/database/.config.json', {key: base['database'][key] for key in ('name', 'user', 'port')})
    ai_path = root/'.ai.config'
    ai = initialize(root/'modules/assistance/.config.json', read_document(ai_path if ai_path.exists() else root/'.ai.config.example'))
    initialize(root/'modules/frontend/.config.json', read_document(root/'frontend/public/runtime-config.json'))
    settings = initialize(root/'.orchestration.json', {
        'project_name': base['infrastructure']['project_name'],
        'public_host': '127.0.0.1' if base['host'] in ('localhost', '127.0.0.1') else base['host'],
        'public_port': base['port'], 'startup_timeout_seconds': 180,
        'api_upstream': 'api:8000', 'assistance_url': 'http://assistance:8000', 'database_host': 'postgres',
        'model_cache_directory': ai['transcription']['cache_directory']})
    from app.infrastructure import require_infrastructure
    project = require_infrastructure(base, root)
    if settings['project_name'] != project:
        raise StartupError('Infrastructure identities differ; automatic adoption is disabled')
    if (settings['public_port'] != legacy['port'] or database['port'] != legacy['database']['port']
            or type(settings['public_port']) is not int or not 1 <= settings['public_port'] <= 65535):
        raise StartupError('Published ports must match the approved existing configuration; no alternatives are selected')
    if type(settings['startup_timeout_seconds']) is not int or not 10 <= settings['startup_timeout_seconds'] <= 3600:
        raise StartupError('Invalid orchestration startup timeout')
    if not (root/'.env').is_file():
        (root/'.env').touch(mode=0o600, exist_ok=True)
    from app.credentials import write_secret
    import secrets
    write_secret(secrets.token_urlsafe(64), root, 'assistance_service_key')
    return base, database, settings


def environment(root, database, settings):
    env = os.environ.copy()
    for name in ('PGPASSWORD', 'POSTGRES_PASSWORD', 'OPENAI_API_KEY'):
        env.pop(name, None)
    cache = Path(settings['model_cache_directory'])
    cache = (cache if cache.is_absolute() else root/cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    env.update(OUROBOROS_DB_NAME=database['name'], OUROBOROS_DB_USER=database['user'],
        OUROBOROS_DB_PORT=str(database['port']), OUROBOROS_DB_SECRET_FILE=str(root/'.secrets/postgres_password'),
        OUROBOROS_PUBLIC_HOST=settings['public_host'], OUROBOROS_PUBLIC_PORT=str(settings['public_port']),
        OUROBOROS_API_UPSTREAM=settings.get('api_upstream','api:8000'),
        OUROBOROS_ASSISTANCE_URL=settings.get('assistance_url','http://assistance:8000'),
        OUROBOROS_DB_HOST=settings.get('database_host','postgres'),
        OUROBOROS_MODEL_CACHE=str(cache))
    return env


def run(command, env, timeout=None, interactive=False):
    try:
        result = subprocess.run(command, env=env, timeout=timeout, check=False, capture_output=not interactive)
    except (OSError, subprocess.TimeoutExpired):
        raise StartupError('Docker operation unavailable or timed out') from None
    if result.returncode:
        raise StartupError('Docker operation failed: '+command[-1]+'. Inspect service health; private diagnostic output was suppressed')
    return result


def main(root=ROOT, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--api-only', action='store_true')
    args = parser.parse_args(argv)
    root = Path(root).resolve()
    try:
        base, database, settings = prepare(root)
        from app.database import compose_command, check_docker, start_postgres
        from app.credentials import prompt_credentials, write_secret
        env = environment(root, database, settings)
        command = compose_command(root, settings['project_name'])
        check_docker()
        run(command+['config', '--quiet'], env, 30)
        if args.check:
            print('Four-module configuration and Compose validated. No services or data changed.')
            return 0
        run(command+['build', 'api']+([] if args.api_only else ['frontend']), env, 3600, True)
        assistance_built = True
        if not args.api_only:
            try:
                run(command+['build', 'assistance'], env, 3600, True)
            except StartupError:
                assistance_built = False
                print('Assistance image preparation failed; required services remain independent. An existing assistance image may be reused.', file=sys.stderr)
        if args.build_only:
            return 0 if assistance_built else 1
        secret = root/'.secrets/postgres_password'
        if not secret.exists():
            password = prompt_credentials(base, root)
            try:
                write_secret(password, root)
            finally:
                password = None
        start_postgres({**base['database'], **database}, secret, root, settings['project_name'])
        print('Authenticate in the interactive container bootstrap; credentials never enter command arguments or environment variables.')
        run(command+['run', '--rm', '--no-deps', 'api', 'python', '-m', 'modules.base.runtime', '--bootstrap'], env, interactive=True)
        existing = run(command+['ps', '--quiet', 'api' if args.api_only else 'frontend'], env, 15).stdout.strip()
        if not existing:
            with socket.socket() as probe:
                if probe.connect_ex((settings['public_host'], settings['public_port'])) == 0:
                    raise StartupError('Approved public port is occupied. Identify its owner explicitly; no process was terminated')
        timeout = str(settings['startup_timeout_seconds'])
        if args.api_only:
            override = root/'.tmp/api-only.compose.json'
            override.parent.mkdir(exist_ok=True)
            override.write_text(json.dumps({'services': {'api': {'ports': [f"{settings['public_host']}:{settings['public_port']}:8000"]}}}), encoding='utf-8')
            run(command+['--file', str(override), 'up', '--detach', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', timeout, 'api'], env, int(timeout)+30)
        else:
            run(command+['up', '--detach', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', timeout, 'api'], env, int(timeout)+30)
            try:
                run(command+['up', '--detach', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', timeout, 'assistance'], env, int(timeout)+30)
            except StartupError:
                print('Assistance unavailable; catalogue, API and frontend startup continue.', file=sys.stderr)
            run(command+['up', '--detach', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', timeout, 'frontend'], env, int(timeout)+30)
        print(f"Ouroboros preparation completed: http://localhost:{settings['public_port']}/ | Swagger: /docs")
        return 0
    except KeyboardInterrupt:
        print('Startup cancelled; containers and persistent data preserved.', file=sys.stderr)
        return 130
    except Exception as error:
        print(str(error) if isinstance(error, (StartupError, ConfigurationError, DatabaseError)) else 'Startup failed; verify module configuration, Docker and infrastructure ownership.', file=sys.stderr)
        return 1
