"""Coordinate startup with safe stage diagnostics and independent cleanup."""
import json
import logging

from app.config import ConfigurationError, PROJECT_ROOT, load_config
from app.credentials import prompt_credentials, write_secret
from app.database import Database, DatabaseError, check_docker, connect, start_postgres, ensure_database
from app.api_credentials import configure_api_credentials, load_signing_secret
from app.auth import AuthService
from app.api_users import APIUserStore
from app.api_users import UserManagementError
from app.main import create_app, run_api
from app.logger import ApplicationLogger
from app.migrate import migrate
from app.log_safety import error_details
from app.cleanup import cleanup_actions, ResourceCleanupError
from app.infrastructure import require_infrastructure


def report_diagnostic(logger, fallback, message, detail, level="ERROR"):
    """Do not let a broken logger mask the primary failure or interrupt cleanup."""
    if logger is not None:
        try:
            logger.log({"level": level, "message": message, "context": detail})
            return
        except BaseException:
            pass
    try:
        fallback.log(getattr(logging, level), "%s | %s", message,
                     json.dumps(detail, ensure_ascii=False))
    except BaseException:
        pass


def main(root=PROJECT_ROOT):
    """Prepare owned infrastructure and serve until graceful shutdown.

    Args:
        root: Workspace owning configuration, migrations and protected secrets.

    Returns:
        Process exit code: 0 on success, 130 on startup cancellation, otherwise 1.

    Migrations and first-administrator recovery occur only after successful
    database master authentication. Cleanup attempts every owned resource.
    """
    fallback = logging.Logger("ouroboros.bootstrap", logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s ouroboros.bootstrap: %(message)s"))
    fallback.addHandler(handler)
    logger = database = auth = application = migration_connection = None
    password = None
    stage = "configuration"
    exit_code = 0
    try:
        config = load_config(root)
        from app.errors import load_error_codes
        load_error_codes()
        stage = "logger_initialization"
        logger = ApplicationLogger(config["logging"], root=root)
        logger.log({"message": "Ouroboros preparation started"})
        stage = "infrastructure_identity"
        project = require_infrastructure(config, root)
        logger.log({"message": "Configuration loaded and validated"})
        stage = "docker_check"
        logger.log({"message": "Checking Docker CLI, Compose, and Engine"})
        check_docker()
        logger.log({"message": "Docker CLI, Compose, and Engine verified"})
        stage = "master_credentials"
        password = prompt_credentials(config, root)
        stage = "postgres_secret"
        secret_path = write_secret(password, root)
        stage = "postgres_startup"
        start_postgres(config["database"], secret_path, root=root, project=project)
        logger.log({"message": "PostgreSQL started or reused and healthcheck passed"})
        stage = "database_selection"
        ensure_database(config["database"], password)
        stage = "migrations"
        migration_connection = connect(config["database"], password)
        logger.log({"message": "Database connection validated"})
        migrate(migration_connection, root=root)
        logger.log({"message": "Database migrations completed"})
        stage = "migration_connection_cleanup"
        failures = cleanup_actions([("migration_connection", migration_connection.close)])
        if failures:
            raise ResourceCleanupError(failures)
        migration_connection = None
        stage = "api_user_setup"
        database = Database(config["database"], password)
        users = APIUserStore(database)
        configure_api_credentials(config, users, root)
        stage = "signing_key_and_authentication"
        auth = AuthService(config["auth"], load_signing_secret(root), users)
        stage = "application_creation"
        application = create_app(config, database, auth, logger)
        logger.log({"message": "Ouroboros preparation completed"})
        stage = "api_server"
        run_api(application, config)
    except (ConfigurationError, DatabaseError, ResourceCleanupError, UserManagementError) as error:
        # These application-owned exception classes contain intentionally safe messages.
        detail = {"stage": stage, **error_details(error)}
        if isinstance(error, ResourceCleanupError):
            detail["cleanup_failures"] = error.failures
        report_diagnostic(logger, fallback, str(error), detail)
        exit_code = 1
    except KeyboardInterrupt:
        serving = stage == "api_server"
        report_diagnostic(logger, fallback,
                          "Application stopped by user" if serving else "Startup cancelled by user",
                          {"stage": stage}, "INFO")
        exit_code = 0 if serving else 130
    except EOFError:
        report_diagnostic(logger, fallback, "Startup input ended before initialization completed",
                          {"stage": stage}, "WARNING")
        exit_code = 1
    except (Exception, SystemExit) as error:
        report_diagnostic(logger, fallback,
                          "Ouroboros startup failed; inspect the safe stage diagnostics in the log",
                          {"stage": stage, **error_details(error)})
        exit_code = 1
    finally:
        password = None
        def report_cleanup(detail):
            destination = None if detail["resource"] in ("logger", "bootstrap_handler") else logger
            report_diagnostic(destination, fallback, "Resource cleanup failed",
                              {"stage": "cleanup", **detail})
        failures = cleanup_actions([
            ("migration_connection", migration_connection.close if migration_connection is not None else None),
            ("database", database.close if database is not None else None),
            ("authentication", auth.close if auth is not None else None),
            ("logger", logger.close if logger is not None else None),
            ("bootstrap_handler", handler.close),
        ], report_cleanup)
        if failures and exit_code == 0:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
