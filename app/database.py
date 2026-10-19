"""Database connection and container lifecycle without destructive operations."""
import os
import json
import subprocess
from contextlib import contextmanager
from threading import BoundedSemaphore
from pathlib import Path

from app.config import PROJECT_ROOT


class DatabaseError(RuntimeError):
    """A safe-to-display database preparation failure."""


def run_command(arguments, timeout, env=None):
    try:
        return subprocess.run(arguments, shell=False, capture_output=True,
                              timeout=timeout, env=env, check=True)
    except FileNotFoundError:
        raise DatabaseError("Docker CLI is unavailable; install Docker Desktop and add Docker to PATH") from None
    except subprocess.TimeoutExpired:
        raise DatabaseError("Docker operation timed out; check Docker Desktop and retry") from None
    except (subprocess.CalledProcessError, OSError):
        # Docker output may contain configuration or authentication details.
        raise DatabaseError("Docker operation failed; check Docker Desktop, image availability, and port conflicts") from None


def check_docker(timeout=15):
    run_command(["docker", "--version"], timeout)
    try:
        run_command(["docker", "compose", "version"], timeout)
    except DatabaseError:
        raise DatabaseError("Docker Compose is unavailable; install or update Docker Desktop") from None
    try:
        run_command(["docker", "info", "--format", "{{.ServerVersion}}"], timeout)
    except DatabaseError:
        raise DatabaseError("Docker Engine is unavailable; open Docker Desktop, wait until the Engine is ready, and retry") from None


def compose_environment(database, secret_path):
    env = os.environ.copy()
    # Do not forward inherited database passwords to subprocesses.
    for key in ("PGPASSWORD", "POSTGRES_PASSWORD"):
        env.pop(key, None)
    env.update(FOUNDATION_DB_NAME=database["name"], FOUNDATION_DB_USER=database["user"],
               FOUNDATION_DB_PORT=str(database["port"]),
               FOUNDATION_DB_SECRET_FILE=str(Path(secret_path).resolve()))
    return env


def compose_command(root=PROJECT_ROOT, project=None):
    if project is None:
        from app.config import load_config
        from app.infrastructure import require_infrastructure
        project = require_infrastructure(load_config(root), root)
    return ["docker", "compose", "--project-name", project, "--project-directory", str(root),
            "--file", str(Path(root) / "compose.yaml")]


def start_postgres(database, secret_path, root=PROJECT_ROOT, project=None):
    timeout = database["startup_timeout"]
    command = compose_command(root, project)
    env = compose_environment(database, secret_path)
    project = command[command.index("--project-name") + 1]
    from app.infrastructure import receipt_matches, record_ownership
    owned = receipt_matches(root, project)
    existing = run_command(command + ["ps", "--all", "--quiet", "postgres"], 15, env).stdout.decode().strip()
    if existing:
        result = run_command(["docker", "inspect", existing], 15, env)
        try:
            container = json.loads(result.stdout)[0]
            owner = container["Config"].get("Labels", {}).get("com.docker.compose.project.working_dir")
            if not owner or Path(owner).resolve() != Path(root).resolve():
                raise DatabaseError("Compose identity is owned by another or unknown workspace; choose a unique infrastructure.project_name. Existing resources were not changed")
            settings = container["Config"]["Env"]
            settings = dict(item.split("=", 1) for item in settings if "=" in item)
        except (ValueError, KeyError, IndexError, TypeError):
            raise DatabaseError("Unable to verify existing PostgreSQL container settings") from None
        # Retain original initialization values on container recreation. Selecting
        # a database or role never modifies roles or passwords in an existing volume.
        initialization = {**database, "name": settings.get("POSTGRES_DB", database["name"]),
                          "user": settings.get("POSTGRES_USER", database["user"])}
        env = compose_environment(initialization, secret_path)
    else:
        volume = run_command(["docker", "volume", "ls", "--filter", f"name=^{project}_postgres_data$", "--format", "{{.Name}}"], 15, env).stdout.decode().strip()
        if volume and not owned:
            raise DatabaseError("An existing data volume has no matching workspace ownership receipt. Restore the original project metadata; automatic adoption is disabled")
    run_command(command + ["up", "--detach", "--wait", "--wait-timeout", str(timeout), "postgres"],
                timeout + 15, env)
    record_ownership(root, project)



def connect(database, password):
    try:
        import psycopg
    except ImportError:
        raise DatabaseError("PostgreSQL driver is unavailable; run python -m pip install -r requirements.txt") from None
    connection = None
    try:
        connection = psycopg.connect(host="127.0.0.1", port=database["port"],
                                    dbname=database["name"], user=database["user"],
                                    password=password, connect_timeout=database["connect_timeout"],
                                    options=f"-c statement_timeout={database['statement_timeout'] * 1000}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        connection.commit()
        return connection
    except psycopg.Error:
        if connection is not None:
            connection.close()
        raise DatabaseError("Database connection failed; verify the configured database, master user, password, and port. Existing volumes retain their original credentials; no data was deleted or credentials changed") from None


class Database:
    """One short-lived connection per request; no shared transactions or idle pool."""
    def __init__(self, config, password):
        self.config = dict(config)
        self.password = password
        self._slots = BoundedSemaphore(config.get("max_connections", 8))

    @contextmanager
    def connection(self):
        if self.password is None:
            raise DatabaseError("Database connection provider is closed")
        from app.logger import log_event
        log_event("DEBUG", "Waiting for database connection capacity", component="database")
        if not self._slots.acquire(timeout=self.config.get("connection_acquire_timeout", 5)):
            raise DatabaseError("Database connection capacity is temporarily exhausted")
        try:
            log_event("DEBUG", "Opening database connection", component="database")
            with connect(self.config, self.password) as connection:
                yield connection
            log_event("DEBUG", "Database transaction completed and connection closed", component="database")
        finally:
            self._slots.release()

    def close(self):
        self.password = None


def ensure_database(database, password):
    """Authenticate the master first; create only a missing database, never a role."""
    import psycopg
    from psycopg import sql
    try:
        with connect({**database, "name": "postgres"}, password) as maintenance:
            maintenance.autocommit = True
            with maintenance.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database["name"],))
                if cursor.fetchone() is None:
                    try:
                        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database["name"])))
                    except psycopg.errors.DuplicateDatabase:
                        pass
    except psycopg.errors.InsufficientPrivilege:
        raise DatabaseError("Master credentials lack permission to create the selected database; use a role with CREATEDB or have an administrator create it. Existing databases were preserved") from None
    except psycopg.Error:
        raise DatabaseError("Unable to prepare the selected database; verify master access to the postgres maintenance database and database creation permissions. Existing databases were preserved") from None
