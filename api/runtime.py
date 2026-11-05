"""Container startup and interactive bootstrap using existing migration/auth rules."""
import hmac
import os
import sys
from pathlib import Path
from api.app.config import load_config, PROJECT_ROOT
from api.app.credentials import prompt_credentials
from api.app.database import Database, DatabaseError, connect, ensure_database
from api.app.api_credentials import configure_api_credentials, load_signing_secret
from api.app.api_users import APIUserStore
from api.app.auth import AuthService
from api.app.migrate import migrate
from api.app.main import create_app, run_api
from api.app.logger import ApplicationLogger
from api.app.cleanup import cleanup_actions, ResourceCleanupError


def database_settings(config):
    return {**config['database'], 'host': os.environ.get('OUROBOROS_DB_HOST', 'postgres'), 'port': 5432}


def migrate_with_cleanup(settings, password):
    connection = connect(settings, password)
    primary = None
    try:
        migrate(connection)
    except BaseException as error:
        primary = error
    failures = cleanup_actions([('migration_connection', connection.close)])
    if primary is not None:
        raise primary
    if failures:
        raise ResourceCleanupError(failures)


def bootstrap():
    config = load_config()
    logger = ApplicationLogger(config['logging'])
    logger.log({'message': 'Ouroboros preparation started'})
    logger.log({'message': 'Configuration loaded and validated'})
    password = None
    try:
        password = prompt_credentials(config)
        settings = database_settings(config)
        ensure_database(settings, password)
        migrate_with_cleanup(settings, password)
        logger.log({'message': 'Database migrations completed'})
        database = Database(settings, password)
        try:
            configure_api_credentials(config, APIUserStore(database))
            load_signing_secret()
        finally:
            database.close()
        # Runtime reuses the original protected secret, never writes a second password copy.
        stored = Path('/run/secrets/postgres_password').read_text(encoding='utf-8')
        if not hmac.compare_digest(password, stored):
            raise DatabaseError('Authenticated password differs from the existing runtime secret; explicit credential reconciliation is required. No secret was replaced')
        print('Database authentication, immutable migration history and API accounts verified.')
    finally:
        password = None
        already_failing = sys.exc_info()[0] is not None
        failures = cleanup_actions([('bootstrap_logger', logger.close)])
        if failures and not already_failing:
            raise ResourceCleanupError(failures)


def serve():
    config = load_config()
    config['database'] = database_settings(config)
    config['host'], config['port'] = '0.0.0.0', 8000
    password = runtime_password()
    database = Database(config['database'], password)
    auth = logger = None
    primary = None
    try:
        auth = AuthService(config['auth'], load_signing_secret(), APIUserStore(database))
        logger = ApplicationLogger(config['logging'])
        application = create_app(config, database, auth, logger)
        logger.log({'message': 'Ouroboros preparation completed'})
        run_api(application, config)
    except BaseException as error:
        primary = error
    finally:
        def report_cleanup(detail):
            if logger:
                logger.log({'level': 'ERROR', 'message': 'Resource cleanup failed', 'context': detail})
        failures = cleanup_actions([('database', database.close),
            ('authentication', auth.close if auth else None), ('logger', logger.close if logger else None)], report_cleanup)
    if primary is not None:
        raise primary
    if failures:
        raise ResourceCleanupError(failures)


def runtime_password():
    return Path('/run/secrets/postgres_password').read_text(encoding='utf-8')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        bootstrap() if '--bootstrap' in argv else serve()
        return 0
    except KeyboardInterrupt:
        print('Base/API stopped by user; persistent resources remain available.')
        return 130 if '--bootstrap' in argv else 0
    except DatabaseError as error:
        print('Base/API initialization failed: '+str(error), file=sys.stderr)
        return 1
    except ValueError:
        print('Base/API configuration or migration integrity validation failed; restore valid configuration/original migration bytes. No history was bypassed.', file=sys.stderr)
        return 1
    except Exception:
        print('Base/API initialization failed; inspect configuration and service health. Private exception details were suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
