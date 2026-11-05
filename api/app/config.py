"""Load and validate project-local JSON configuration."""
import json
import logging
import os
from pathlib import Path

from shared.paths import PROJECT_ROOT, ConfigurationError
from shared.configfiles import ensure_object, read_object, write_object
LEVELS = {name: getattr(logging, name) for name in
          ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")}
FIELDS = {"datetime", "level", "component", "class_name", "source", "line",
          "interaction_id", "message", "context", "category", "method", "path", "method_path"}

def validate_logging(config):
    if not isinstance(config, dict):
        raise ConfigurationError("logging must be a JSON object")
    if not isinstance(config.get("level"), str) or config["level"] not in ("INFO", "DEBUG"):
        raise ConfigurationError("logging.level must be INFO or DEBUG")
    for field in ("format", "directory"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ConfigurationError(f"logging.{field} must be a non-empty string")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in config["format"]):
        raise ConfigurationError("logging.format must contain a single line without control characters")
    try:
        formatter = logging.Formatter(config["format"], validate=True)
        formatter.format(logging.makeLogRecord({field: 1 if field == "line" else "example"
                                                for field in FIELDS}))
    except (ValueError, KeyError, TypeError) as error:
        raise ConfigurationError("logging.format must use valid %(field)s placeholders") from error
    config.setdefault("body_max_chars", 2048)
    if type(config["body_max_chars"]) is not int or not 64 <= config["body_max_chars"] <= 65536:
        raise ConfigurationError("logging.body_max_chars must be an integer between 64 and 65536")
    return config


def load_config(root=PROJECT_ROOT):
    root = Path(root).resolve()
    path = Path(os.environ.get('OUROBOROS_API_CONFIG', root / 'api/config.json'))
    example = root / 'api/config.example.json'
    config = ensure_object(path, example if example.is_file() else PROJECT_ROOT / 'api/config.example.json')
    database_path = Path(os.environ.get('OUROBOROS_DATABASE_CONFIG', root / 'database/config.json'))
    database_example = root / 'database/config.example.json'
    shared_database = ensure_object(database_path, database_example if database_example.is_file() else PROJECT_ROOT / 'database/config.example.json')
    runtime = read_object(root / 'config.json') if (root / 'config.json').is_file() else {}
    config.setdefault('host', os.environ.get('OUROBOROS_PUBLIC_HOST', runtime.get('public_host', 'localhost')))
    config.setdefault('port', int(os.environ.get('OUROBOROS_PUBLIC_PORT', runtime.get('public_port', 6969))))
    connection = config.get('database', {})
    if not isinstance(connection, dict):
        raise ConfigurationError('database must be an object')
    config['database'] = {**connection, **shared_database}
    host = config.get("host")
    if host is None or isinstance(host, str) and not host.strip():
        config["host"] = "localhost"
    elif not isinstance(host, str):
        raise ConfigurationError("host must be a string or null")
    else:
        config["host"] = host.strip()
    config.setdefault("port", 6969)
    port = config.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ConfigurationError("port must be an integer between 1 and 65535")
    database = config.get("database")
    if not isinstance(database, dict):
        raise ConfigurationError("database must be a JSON object")
    for field in ("name", "user"):
        database.setdefault(field, "")
        if not isinstance(database.get(field), str):
            raise ConfigurationError(f"database.{field} must be a string (an empty string is allowed)")
    for field, default, maximum in (("port", 6669, 65535), ("startup_timeout", 120, 3600),
                                    ("connect_timeout", 10, 300), ("statement_timeout", 30, 3600)):
        database.setdefault(field, default)
        if type(database[field]) is not int or not 1 <= database[field] <= maximum:
            raise ConfigurationError(f"database.{field} must be an integer between 1 and {maximum}")
    for field, default, maximum in (("max_connections", 8, 32), ("connection_acquire_timeout", 5, 300)):
        database.setdefault(field, default)
        if type(database[field]) is not int or not 1 <= database[field] <= maximum:
            raise ConfigurationError(f"database.{field} must be an integer between 1 and {maximum}")
    if database["port"] == port:
        raise ConfigurationError("database.port must differ from the application port")
    for field in ("name", "user"):
        value = database[field]
        if value.strip():
            import re
            if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
                raise ConfigurationError(f"database.{field} must contain 1-63 lowercase letters, digits, or underscores and must not start with a digit")
    auth = config.setdefault("auth", {})
    if not isinstance(auth, dict):
        raise ConfigurationError("auth must be a JSON object")
    for field, default in (("issuer", "ouroboros"), ("audience", "ouroboros-api")):
        auth.setdefault(field, default)
        if not isinstance(auth[field], str) or not auth[field].strip() or any(not char.isprintable() for char in auth[field]):
            raise ConfigurationError(f"auth.{field} must be a nonblank printable string")
    # Read old fields only to permit one-way, transactional migration on startup.
    if "username" in auth or "password_hash" in auth:
        username, password_hash = auth.get("username", ""), auth.get("password_hash", "")
        if not isinstance(username, str) or not isinstance(password_hash, str) or bool(username) != bool(password_hash):
            raise ConfigurationError("Legacy auth.username and auth.password_hash must both be configured or both be empty")
        if username and (not username.strip() or any(not char.isprintable() for char in username)):
            raise ConfigurationError("Legacy auth.username must be printable and nonblank")
        if password_hash:
            from api.app.api_users import validate_hash
            try:
                validate_hash(password_hash)
            except Exception:
                raise ConfigurationError("Legacy auth.password_hash must be a valid Argon2id hash") from None
    preferences = config.setdefault("api_users", {})
    if not isinstance(preferences, dict):
        raise ConfigurationError("api_users must be a JSON object")
    if any(key != "last_api_username" for key in preferences):
        raise ConfigurationError("api_users supports only last_api_username; accounts belong in the database")
    preferences.setdefault("last_api_username", "")
    if not isinstance(preferences["last_api_username"], str) or any(not char.isprintable() for char in preferences["last_api_username"]):
        raise ConfigurationError("api_users.last_api_username must be a printable string")
    auth.setdefault("token_ttl_seconds", 1800)
    if type(auth["token_ttl_seconds"]) is not int or not 1 <= auth["token_ttl_seconds"] <= 86400:
        raise ConfigurationError("auth.token_ttl_seconds must be an integer between 1 and 86400")
    infrastructure = config.setdefault("infrastructure", {"project_name": "", "workspace": ""})
    if not isinstance(infrastructure, dict):
        raise ConfigurationError("infrastructure must be a JSON object")
    for field in ("project_name", "workspace"):
        infrastructure.setdefault(field, "")
        if not isinstance(infrastructure[field], str):
            raise ConfigurationError(f"infrastructure.{field} must be a string")
    from shared.datetimes import zone_name
    for field in ('application_timezone', 'default_display_timezone'):
        config.setdefault(field, 'Europe/Lisbon')
        try:
            zone_name(config[field])
        except (ValueError, TypeError):
            raise ConfigurationError(field + ' must be a valid IANA timezone') from None
    audit = config.setdefault('audit', {})
    if not isinstance(audit, dict):
        raise ConfigurationError('audit must be an object')
    for field in ('request_body_max_bytes', 'response_body_max_bytes', 'mutation_max_bytes', 'query_max_bytes'):
        audit.setdefault(field, 8192)
        if type(audit[field]) is not int or not 256 <= audit[field] <= 1048576:
            raise ConfigurationError('audit capture limits must be integers from 256 to 1048576 bytes')
    api = config.setdefault('api', {})
    if not isinstance(api, dict):
        raise ConfigurationError('api must be an object')
    for field, default, minimum, maximum in (
            ('max_batch_size', 300, 1, 10000),
            ('max_creation_body_bytes', 4194304, 1024, 67108864)):
        api.setdefault(field, default)
        if type(api[field]) is not int or not minimum <= api[field] <= maximum:
            raise ConfigurationError(f'api.{field} must be an integer between {minimum} and {maximum}')
    validate_logging(config.get("logging"))
    from api.app.browser_sessions import browser_settings
    browser_settings(config)
    return config


def save_config(config, root=PROJECT_ROOT):
    """Persist each preference only in its owning module's canonical config.json."""
    if config.get('auth', {}).get('password_hash'):
        raise ConfigurationError('Migrate legacy API credentials before saving configuration; no hash copy was written')
    root = Path(root)
    path = Path(os.environ.get('OUROBOROS_API_CONFIG', root / 'api/config.json'))
    database_path = Path(os.environ.get('OUROBOROS_DATABASE_CONFIG', root / 'database/config.json'))
    database_keys = ('name', 'user', 'port', 'startup_timeout')
    database = read_object(database_path) if database_path.exists() else {}
    database.update({key: config['database'][key] for key in database_keys if key in config['database']})
    api = {key: value for key, value in config.items() if key not in ('host', 'port', 'infrastructure', 'transcription')}
    api['database'] = {key: value for key, value in config['database'].items() if key not in database_keys}
    write_object(database_path, database)
    write_object(path, api)
