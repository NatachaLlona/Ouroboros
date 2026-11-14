"""Inspect the live registered contract and apply only additive API migrations."""
import hashlib
from pathlib import Path
from psycopg import sql
from database.model import render
from database.provision import BASELINE_VERSION, baseline_checksum
from database.settings import ConfigurationError, mapping, structural_identity
from api.service.resources import PERSONAL, SPECS

VERSION = 'api-v1/001'
MIGRATION = Path(__file__).resolve().parents[3]/'modules/database/sql/api_migrations/001_api_runtime.sql'
MIGRATIONS = ((VERSION,MIGRATION),('api-v1/002',MIGRATION.with_name('002_human_identity.sql')))
LOGIN = 'ouroboros_api_login'


def inspect_contract(connection, document, require_api=False):
    fingerprint,structure = structural_identity(document)
    row = connection.execute(render('SELECT structural_hash,structural_mapping FROM {provisioning_registry}',document)).fetchone()
    if row is None or row[0] != fingerprint or row[1] != structure:
        raise ConfigurationError('Registered structural contract differs from provisioning.jsonc')
    registry = dict(connection.execute(render('SELECT version,checksum FROM {foundation_migration}',document)).fetchall())
    if registry.get(BASELINE_VERSION) != baseline_checksum(document):
        raise ConfigurationError('Applied Database baseline checksum mismatch')
    if require_api:
        for version,source in MIGRATIONS:
            if registry.get(version) != hashlib.sha256(source.read_bytes()).hexdigest():
                raise ConfigurationError('API migration missing or checksum mismatch; run start.py --api-migrate')
    for resource in SPECS:
        physical = mapping(document)[resource]
        columns = {row[0] for row in connection.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',(document['schema'],physical))}
        expected = {'id_'+physical,'sequence_'+physical,'prefix_'+physical,'created_at'}
        for field in SPECS[resource]:
            expected.add(render(field,document))
        if resource in PERSONAL:
            expected.add('id_app_user')
        if not expected <= columns:
            raise ConfigurationError('Live schema does not satisfy the API resource contract: '+resource)
        triggers={row[0] for row in connection.execute('SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s AND t.tgenabled IN (\'O\',\'A\')',(document['schema'],physical))}
        if not {'mutation_audit','protect_metadata'}<=triggers:
            raise ConfigurationError('Mandatory database triggers are missing or disabled: '+resource)
    role = connection.execute("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='ouroboros_runtime'").fetchone()
    if role != (False,False,False,False):
        raise ConfigurationError('Unsafe or missing runtime capability role')
    if require_api and connection.execute('SELECT current_user').fetchone()[0]==LOGIN:
        privileges=connection.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,pg_has_role(current_user,'ouroboros_owner','MEMBER') FROM pg_roles WHERE rolname=current_user").fetchone()
        if any(privileges):
            raise ConfigurationError('Unsafe API SQL login privileges')
        credential='"'+document['schema']+'"."api_user_credential"'
        if connection.execute('SELECT has_table_privilege(current_user,%s,\'SELECT\')',(credential,)).fetchone()[0]:
            raise ConfigurationError('API SQL login must not have direct credential table access')
    return registry


def migrate(connection, document, runtime_password):
    changed = False
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(719230820)')
        registry = inspect_contract(connection,document)
        for version,path in MIGRATIONS:
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if version in registry:
                if registry[version] != checksum:
                    raise ConfigurationError('Applied API migration checksum mismatch: '+version)
                continue
            if version == VERSION:
                if connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(LOGIN,)).fetchone():
                    raise ConfigurationError('API SQL login already exists without a registered migration')
                connection.execute(sql.SQL('CREATE ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(sql.Identifier(LOGIN),sql.Literal(runtime_password)))
                connection.execute(sql.SQL('GRANT ouroboros_runtime TO {}').format(sql.Identifier(LOGIN)))
                connection.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET search_path TO pg_catalog, {}').format(sql.Identifier(LOGIN),sql.Identifier(document['database_name']),sql.Identifier(document['schema'])))
            connection.execute('SET LOCAL ROLE ouroboros_owner')
            source = path.read_text(encoding='utf-8').replace('@schema@','"'+document['schema']+'"')
            connection.execute(render(source,document))
            connection.execute(render('INSERT INTO {foundation_migration}(version,checksum) VALUES(%s,%s)',document),(version,checksum))
            changed = True
    return changed
