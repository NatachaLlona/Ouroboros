"""Transactional new-installation baseline and resumable operator enrollment."""
import hashlib
from pathlib import Path

from database.model import MODEL, ORDER, PROTECTED, baseline_sql, render
from database.settings import ConfigurationError, mapping, structural_identity

OWNER = 'ouroboros_owner'
RUNTIME = 'ouroboros_runtime'
BASELINE_VERSION = 'database-v1/001'


def baseline_checksum(document):
    digest = hashlib.sha256()
    for filename in ('model.py', 'provision.py'):
        digest.update(Path(__file__).with_name(filename).read_bytes())
    digest.update(baseline_sql(document).encode())
    return digest.hexdigest()


def functions_sql(document):
    s = '"'+document['schema']+'"'
    text = f"""
CREATE FUNCTION {s}.protect_metadata() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND (
    to_jsonb(NEW)->('sequence_' || TG_TABLE_NAME) IS DISTINCT FROM to_jsonb(OLD)->('sequence_' || TG_TABLE_NAME)
    OR NEW.created_at IS DISTINCT FROM OLD.created_at
    OR NEW.created_at_timezone IS DISTINCT FROM OLD.created_at_timezone) THEN
    RAISE EXCEPTION 'Identity and creation metadata are immutable' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION {s}.reject_change() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN RAISE EXCEPTION 'Protected installation evidence is immutable' USING ERRCODE = '42501'; END $$;
CREATE FUNCTION {s}.capture_mutation() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE event_id text; target text; actor text; person text; version bigint;
BEGIN
  target := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END ->> ('id_' || TG_TABLE_NAME);
  actor := nullif(current_setting('ouroboros.actor_api_user', true), '');
  person := nullif(current_setting('ouroboros.actor_app_user', true), '');
  IF actor IS NOT NULL THEN
    PERFORM 1 FROM {{api_user}} WHERE id_api_user = actor AND is_active FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Active actor required' USING ERRCODE = '42501'; END IF;
  END IF;
  IF person IS NOT NULL THEN
    PERFORM 1 FROM {{app_user_api}} l JOIN {{app_user}} p USING (id_app_user)
      WHERE l.id_api_user = actor AND l.id_app_user = person AND l.valid_until IS NULL AND p.is_active FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Current actor membership required' USING ERRCODE = '42501'; END IF;
  END IF;
  -- Deliberately omit entire request/row bodies, including all credential material.
  INSERT INTO {{api_audit_log}}(id_api_user, id_app_user, resource, target_id, action)
    VALUES (actor, person, TG_TABLE_NAME, target, TG_OP) RETURNING id_api_audit_log INTO event_id;
  PERFORM pg_advisory_xact_lock(hashtextextended(TG_TABLE_NAME || ':' || target, 0));
  SELECT coalesce(max(version_number), 0) + 1 INTO version FROM {{record_version}}
    WHERE resource = TG_TABLE_NAME AND record_id = target;
  INSERT INTO {{record_version}}(id_api_audit_log, resource, record_id, version_number, operation)
    VALUES (event_id, TG_TABLE_NAME, target, version, TG_OP);
  IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE FUNCTION {s}.check_tag_ownership() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE candidate text; candidate_owner text; candidate_visibility text; row_data jsonb := to_jsonb(NEW);
BEGIN
  FOREACH candidate IN ARRAY ARRAY[row_data->>'id_tag', row_data->>'id_source_tag', row_data->>'id_target_tag'] LOOP
    IF candidate IS NULL OR (TG_TABLE_NAME = '{mapping(document)['tag']}' AND candidate = row_data->>'id_tag') THEN CONTINUE; END IF;
    SELECT id_app_user, visibility INTO candidate_owner, candidate_visibility FROM {{tag}} WHERE id_tag = candidate FOR SHARE;
    IF candidate_owner IS DISTINCT FROM NEW.id_app_user AND candidate_visibility IS DISTINCT FROM 'shared' THEN
      RAISE EXCEPTION 'Tag ownership conflict' USING ERRCODE = '23514';
    END IF;
    -- Shared tags can be used by people; private relationship graphs cannot cross owners.
    IF TG_TABLE_NAME IN ('{mapping(document)['tag_relationship']}', '{mapping(document)['tag_category_relationship']}')
      AND candidate_owner IS NOT NULL AND candidate_owner IS DISTINCT FROM NEW.id_app_user THEN
      RAISE EXCEPTION 'Relationship ownership conflict' USING ERRCODE = '23514';
    END IF;
  END LOOP;
  IF row_data ? 'id_tag_category' THEN
    SELECT id_app_user INTO candidate_owner FROM {{tag_category}} WHERE id_tag_category = row_data->>'id_tag_category' FOR SHARE;
    IF candidate_owner IS NOT NULL AND candidate_owner IS DISTINCT FROM NEW.id_app_user THEN
      RAISE EXCEPTION 'Category ownership conflict' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION {s}.protect_owner() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF NEW.id_app_user IS DISTINCT FROM OLD.id_app_user THEN
    RAISE EXCEPTION 'Personal ownership is immutable' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION {s}.protect_membership_history() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Identity membership history must be retained' USING ERRCODE = '42501';
  END IF;
  IF NEW.id_api_user IS DISTINCT FROM OLD.id_api_user OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
    OR (OLD.valid_until IS NOT NULL AND NEW.valid_until IS DISTINCT FROM OLD.valid_until) THEN
    RAISE EXCEPTION 'Historical identity membership is immutable' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION {s}.append_classification() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(719230819);
  IF NEW.tier IS NULL THEN SELECT coalesce(max(tier), 0)+1 INTO NEW.tier FROM {{work_classification}}; END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION {s}.change_plan(selected_plan text) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE actor text; result text;
BEGIN
  PERFORM pg_advisory_xact_lock(719230818);
  actor := nullif(current_setting('ouroboros.actor_api_user', true), '');
  PERFORM 1 FROM {{super_administrator}} sa JOIN {{api_user}} au USING (id_api_user)
    JOIN {{app_user}} ap USING (id_app_user)
    JOIN {{app_user_api}} l ON l.id_app_user_api = sa.id_app_user_api
    WHERE sa.id_api_user = actor AND au.is_active AND ap.is_active AND l.valid_until IS NULL
    FOR UPDATE OF sa, au, ap, l;
  IF NOT FOUND THEN RAISE EXCEPTION 'Only the installation super administrator can change plans' USING ERRCODE = '42501'; END IF;
  PERFORM 1 FROM {{plan}} WHERE id_plan = selected_plan FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown plan' USING ERRCODE = '23503'; END IF;
  IF (SELECT count(*) FROM {{plan_module}} pm JOIN {{module}} m USING (id_module)
        WHERE pm.id_plan = selected_plan AND m.name IN ('database','api_integration')) <> 2 THEN
    RAISE EXCEPTION 'Database and API Integration must be bundled' USING ERRCODE = '23514';
  END IF;
  UPDATE {{installation_plan}} SET effective_until = clock_timestamp() WHERE effective_until IS NULL;
  INSERT INTO {{installation_plan}}(id_plan, changed_by) VALUES (selected_plan, actor) RETURNING id_installation_plan INTO result;
  RETURN result;
END $$;
"""
    return render(text, document)


def apply_baseline(connection, document, master_user):
    """No legacy upgrade: an existing unregistered schema is rejected atomically."""
    from psycopg import sql
    from psycopg.types.json import Jsonb
    names = mapping(document)
    schema = document['schema']
    fingerprint, structural = structural_identity(document)
    checksum = baseline_checksum(document)
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(719230820)')
        registered_schema = connection.execute("SELECT schemaname FROM pg_tables WHERE tablename='provisioning_registry' AND schemaname NOT IN ('pg_catalog','information_schema')").fetchone()
        if registered_schema and registered_schema[0] != schema:
            raise ConfigurationError('Structural provisioning differs from the registered installation; restore provisioning.jsonc')
        exists = connection.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone()
        if exists:
            try:
                row = connection.execute(sql.SQL('SELECT structural_hash, structural_mapping FROM {}.{}').format(
                    sql.Identifier(schema), sql.Identifier(names['provisioning_registry']))).fetchone()
            except Exception:
                raise ConfigurationError('Existing schema has no compatible provisioning registry; use a new installation') from None
            if row is None or row[0] != fingerprint or row[1] != structural:
                raise ConfigurationError('Structural provisioning differs from the registered installation; restore provisioning.jsonc')
            migration = connection.execute(sql.SQL('SELECT checksum FROM {}.{} WHERE version=%s').format(
                sql.Identifier(schema), sql.Identifier(names['foundation_migration'])), (BASELINE_VERSION,)).fetchone()
            if migration is None or migration[0] != checksum:
                raise ConfigurationError('New-installation baseline checksum differs; do not rewrite applied baseline files')
            return False
        if connection.execute("SELECT 1 FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') LIMIT 1").fetchone():
            raise ConfigurationError('Baseline requires an empty database; historical databases are never upgraded by this track')
        for role in (OWNER, RUNTIME):
            if not connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT').format(sql.Identifier(role)))
            else:
                raise ConfigurationError('Protected SQL roles already exist in an unregistered cluster')
        connection.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(OWNER), sql.Identifier(master_user)))
        connection.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        connection.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(document['database_name'])))
        connection.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(document['database_name']), sql.Identifier(RUNTIME)))
        connection.execute(sql.SQL("ALTER DATABASE {} SET timezone TO 'UTC'").format(sql.Identifier(document['database_name'])))
        # SET values are SQL literals, never interpolated operator input.
        connection.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET search_path TO pg_catalog, {}').format(
            sql.Identifier(master_user), sql.Identifier(document['database_name']), sql.Identifier(schema)))
        connection.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET search_path TO pg_catalog, {}').format(
            sql.Identifier(RUNTIME), sql.Identifier(document['database_name']), sql.Identifier(schema)))
        connection.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(schema), sql.Identifier(OWNER)))
        connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(OWNER)))
        connection.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA {} REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC').format(sql.Identifier(schema)))
        connection.execute(baseline_sql(document))
        connection.execute(functions_sql(document))
        for table in ORDER:
            qualified = sql.SQL('{}.{}').format(sql.Identifier(schema), sql.Identifier(names[table]))
            connection.execute(sql.SQL('CREATE TRIGGER protect_metadata BEFORE UPDATE ON {} FOR EACH ROW EXECUTE FUNCTION {}.protect_metadata()').format(qualified, sql.Identifier(schema)))
            if table not in ('api_audit_log', 'record_version', 'foundation_migration', 'provisioning_registry'):
                connection.execute(sql.SQL('CREATE TRIGGER mutation_audit AFTER INSERT OR UPDATE OR DELETE ON {} FOR EACH ROW EXECUTE FUNCTION {}.capture_mutation()').format(qualified, sql.Identifier(schema)))
            if table in ('tag', 'tag_category_relationship', 'tag_relationship', 'work_tag'):
                connection.execute(sql.SQL('CREATE TRIGGER tag_ownership BEFORE INSERT OR UPDATE ON {} FOR EACH ROW EXECUTE FUNCTION {}.check_tag_ownership()').format(qualified, sql.Identifier(schema)))
            if 'id_app_user' in MODEL[table] and table not in ('api_audit_log',):
                connection.execute(sql.SQL('CREATE TRIGGER owner_immutable BEFORE UPDATE ON {} FOR EACH ROW EXECUTE FUNCTION {}.protect_owner()').format(qualified, sql.Identifier(schema)))
        for table in ('api_audit_log', 'record_version', 'foundation_migration', 'provisioning_registry', 'super_administrator', 'subscription_charge'):
            connection.execute(sql.SQL('CREATE TRIGGER immutable_evidence BEFORE UPDATE OR DELETE ON {}.{} FOR EACH ROW EXECUTE FUNCTION {}.reject_change()').format(sql.Identifier(schema), sql.Identifier(names[table]), sql.Identifier(schema)))
        connection.execute(render('CREATE UNIQUE INDEX current_person_api ON {app_user_api}(id_app_user, id_api_user) WHERE valid_until IS NULL', document))
        connection.execute(render(f'CREATE TRIGGER membership_history BEFORE UPDATE OR DELETE ON {{app_user_api}} FOR EACH ROW EXECUTE FUNCTION "{schema}".protect_membership_history()', document))
        connection.execute(render('CREATE UNIQUE INDEX one_current_plan ON {installation_plan}((true)) WHERE effective_until IS NULL', document))
        connection.execute(render('CREATE UNIQUE INDEX one_current_human_credential ON {api_user_credential}(id_api_user) WHERE revoked_at IS NULL AND credential_kind = \'human_password\'', document))
        connection.execute(render(f'CREATE TRIGGER tier_append BEFORE INSERT ON {{work_classification}} FOR EACH ROW EXECUTE FUNCTION "{schema}".append_classification()', document))
        connection.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(RUNTIME)))
        for table in ORDER:
            qualified = sql.SQL('{}.{}').format(sql.Identifier(schema), sql.Identifier(names[table]))
            # Credential hashes and reserved installation state have no general runtime grants.
            if table not in ('api_user_credential',):
                connection.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(qualified, sql.Identifier(RUNTIME)))
            if table not in PROTECTED and table != 'api_user_credential':
                connection.execute(sql.SQL('GRANT INSERT, UPDATE, DELETE ON {} TO {}').format(qualified, sql.Identifier(RUNTIME)))
        connection.execute(sql.SQL('GRANT USAGE ON ALL SEQUENCES IN SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(RUNTIME)))
        connection.execute(sql.SQL('GRANT EXECUTE ON FUNCTION {}.change_plan(text) TO {}').format(sql.Identifier(schema), sql.Identifier(RUNTIME)))
        connection.execute(render('INSERT INTO {provisioning_registry}(structural_hash, structural_mapping) VALUES (%s,%s)', document), (fingerprint, Jsonb(structural)))
        connection.execute(render('INSERT INTO {foundation_migration}(version, checksum) VALUES (%s,%s)', document), (BASELINE_VERSION, checksum))
        return True


def has_operator(connection, document):
    return connection.execute(render('SELECT id_super_administrator FROM {super_administrator}', document)).fetchone() is not None


def bootstrap(connection, document, personal_name, username, password):
    """The only enrollment path, protected by a transaction lock and SQL singleton."""
    from argon2 import PasswordHasher
    from database.secrets import validate_password
    from psycopg import sql
    validate_password(password)
    if not personal_name.strip() or not username.strip() or len(username) > 128 or len(personal_name) > 256:
        raise ConfigurationError('Operator name and API username must be nonempty and bounded')
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(719230820)')
        if has_operator(connection, document):
            return False
        connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(OWNER)))
        def insert(text, parameters=()):
            return connection.execute(render(text, document), parameters).fetchone()[0]
        person = insert('INSERT INTO {app_user}(personal_name) VALUES (%s) RETURNING id_app_user', (personal_name,))
        actor = insert('INSERT INTO {api_user}(username) VALUES (%s) RETURNING id_api_user', (username,))
        connection.execute("SELECT set_config('ouroboros.actor_api_user', %s, true)", (actor,))
        connection.execute(render("INSERT INTO {api_user_credential}(id_api_user, credential_kind, secret_hash) VALUES (%s,'human_password',%s)", document), (actor, PasswordHasher().hash(password)))
        link = insert('INSERT INTO {app_user_api}(id_app_user, id_api_user) VALUES (%s,%s) RETURNING id_app_user_api', (person, actor))
        connection.execute("SELECT set_config('ouroboros.actor_app_user', %s, true)", (person,))
        connection.execute(render('INSERT INTO {super_administrator}(id_app_user,id_api_user,id_app_user_api) VALUES (%s,%s,%s)', document), (person, actor, link))
        plan = insert("INSERT INTO {plan}(plan_number,name) VALUES (1,'Plan 1') RETURNING id_plan")
        for name in ('database','api_integration','frontend','assistance'):
            module = insert('INSERT INTO {module}(name,is_mandatory) VALUES (%s,%s) RETURNING id_module', (name, name in ('database','api_integration')))
            if name in ('database','api_integration'):
                connection.execute(render('INSERT INTO {plan_module}(id_plan,id_module) VALUES (%s,%s)', document), (plan,module))
        connection.execute(render('INSERT INTO {installation_plan}(id_plan,changed_by) VALUES (%s,%s)', document), (plan,actor))
        return True
