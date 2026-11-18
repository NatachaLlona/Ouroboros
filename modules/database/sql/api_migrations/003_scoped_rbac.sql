-- Additive API RBAC: custom roles, independent section/action grants and safe delegation.
-- Existing identifiers, credentials, memberships, triggers and permission rows are preserved.
ALTER TABLE {role} ADD COLUMN is_system boolean NOT NULL DEFAULT false;
ALTER TABLE {api_user} ADD COLUMN deleted_at timestamptz;
UPDATE {role} SET is_system=true
 WHERE name IN ('user','manager','administrator') OR left(name,9)='identity_';

CREATE FUNCTION @schema@.api_section(resource_name text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
 SELECT CASE
 WHEN resource_name='api_user' THEN 'identity'
 WHEN resource_name='role' THEN 'roles'
 WHEN resource_name IN ('permission_assignment','access_rule','permission') THEN 'authorization'
 WHEN resource_name IN ('test','work','platform','work_availability','work_classification','work_title_alias','work_external_reference','platform_plan','platform_promotion') THEN 'catalogue'
 WHEN resource_name IN ('user_work','user_platform','watch_list_entry','watch_history','tag','tag_category','tag_relationship','tag_category_relationship','work_tag','work_submission') THEN 'personal'
 WHEN resource_name IN ('platform_subscription','subscription_charge','subscription_reminder') THEN 'subscriptions'
 WHEN resource_name='operator_setting' THEN 'settings'
 WHEN resource_name IN ('api_audit_log','record_version') THEN 'audit'
 ELSE resource_name END;
$$;

CREATE FUNCTION @schema@.api_rule_allows(actor text, resource_name text, action_name text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT NOT EXISTS(SELECT 1 FROM {access_rule} WHERE (id_api_user IS NULL OR id_api_user=actor)
  AND rule_kind='deny' AND resource IN (resource_name,@schema@.api_section(resource_name),'*') AND action=action_name)
 AND (NOT EXISTS(SELECT 1 FROM {access_rule} WHERE (id_api_user IS NULL OR id_api_user=actor) AND rule_kind='allow')
 OR EXISTS(SELECT 1 FROM {access_rule} WHERE (id_api_user IS NULL OR id_api_user=actor)
  AND rule_kind='allow' AND resource IN (resource_name,@schema@.api_section(resource_name),'*') AND action=action_name));
$$;

CREATE OR REPLACE FUNCTION @schema@.api_can(actor text, resource_name text, action_name text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM {api_user} WHERE id_api_user=actor AND is_active AND deleted_at IS NULL)
 AND @schema@.api_rule_allows(actor,resource_name,action_name)
 -- A section grant cannot bypass a deny/narrow allow list on one of its resources.
 AND NOT EXISTS(SELECT 1 FROM {permission} p WHERE p.resource<>resource_name
  AND @schema@.api_section(p.resource)=resource_name AND p.action=action_name
  AND NOT @schema@.api_rule_allows(actor,p.resource,action_name))
 AND (EXISTS(SELECT 1 FROM {super_administrator} s JOIN {app_user_api} l USING(id_app_user_api)
   JOIN {app_user} p ON p.id_app_user=s.id_app_user WHERE s.id_api_user=actor AND l.valid_until IS NULL AND p.is_active)
 OR EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role_permission} rp USING(id_role)
   JOIN {permission} p USING(id_permission) WHERE ur.id_api_user=actor
   AND p.resource IN (resource_name,@schema@.api_section(resource_name)) AND p.action=action_name));
$$;

CREATE FUNCTION @schema@.api_require_rbac(resource_name text, action_name text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),'');
 scopes jsonb:=coalesce(nullif(current_setting('ouroboros.actor_scopes',true),''),'[]')::jsonb;
BEGIN
 IF NOT @schema@.api_can(actor,resource_name,action_name)
 OR NOT (scopes ? (resource_name||':'||action_name) OR scopes ? (@schema@.api_section(resource_name)||':'||action_name)) THEN
  RAISE EXCEPTION 'Permission denied' USING ERRCODE='42501';
 END IF;
END $$;

CREATE FUNCTION @schema@.api_delegable(grants text[])
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE code text;
BEGIN
 IF cardinality(grants)>512 OR cardinality(grants)<>(SELECT count(DISTINCT v) FROM unnest(grants) v) THEN
  RAISE EXCEPTION 'Invalid permission list' USING ERRCODE='23514'; END IF;
 FOREACH code IN ARRAY grants LOOP
  IF NOT EXISTS(SELECT 1 FROM {permission} WHERE resource=split_part(code,':',1) AND action=split_part(code,':',2))
   OR code !~ '^[a-z_]+:(create|read|update|delete)$' THEN
   RAISE EXCEPTION 'Unknown permission' USING ERRCODE='23514'; END IF;
  PERFORM @schema@.api_require_rbac(split_part(code,':',1),split_part(code,':',2));
 END LOOP;
END $$;

CREATE FUNCTION @schema@.api_rbac(operation text, target text, body jsonb)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),'');
 selected_role text; individual_role text; result text; person text; role_name text;
 grants text[]; previous_grants text[]; desired_name text; desired_description text; code text;
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF jsonb_typeof(body)<>'object' THEN RAISE EXCEPTION 'Invalid request' USING ERRCODE='23514'; END IF;
 IF operation IN ('role_create','role_patch','role_delete','role_permissions') THEN
  PERFORM @schema@.api_require_rbac('roles',CASE operation WHEN 'role_create' THEN 'create' WHEN 'role_delete' THEN 'delete' ELSE 'update' END);
  IF operation<>'role_create' THEN
   SELECT name INTO role_name FROM {role} WHERE id_role=target AND NOT is_system AND left(name,9)<>'identity_' FOR UPDATE;
   IF role_name IS NULL THEN RAISE EXCEPTION 'Protected or unknown role' USING ERRCODE='42501'; END IF;
   SELECT coalesce(array_agg(p.resource||':'||p.action),ARRAY[]::text[]) INTO previous_grants
    FROM {role_permission} rp JOIN {permission} p USING(id_permission) WHERE rp.id_role=target;
   PERFORM @schema@.api_delegable(previous_grants);
  END IF;
  IF operation IN ('role_create','role_permissions') THEN
   IF jsonb_typeof(body->'permissions')<>'array' THEN RAISE EXCEPTION 'Invalid permissions' USING ERRCODE='23514'; END IF;
   SELECT coalesce(array_agg(v),ARRAY[]::text[]) INTO grants FROM jsonb_array_elements_text(body->'permissions') v;
   PERFORM @schema@.api_delegable(grants);
  END IF;
  IF operation IN ('role_create','role_patch') THEN
   desired_name:=body->>'name'; desired_description:=body->>'description';
   IF (operation='role_create' OR body ? 'name') AND (desired_name IS NULL OR length(desired_name) NOT BETWEEN 1 AND 80
    OR desired_name<>btrim(desired_name) OR desired_name ~ '[[:cntrl:]]' OR desired_name IN ('user','manager','administrator','super_administrator','master') OR left(desired_name,9)='identity_') THEN
    RAISE EXCEPTION 'Invalid role name' USING ERRCODE='23514'; END IF;
   IF body ? 'description' AND (desired_description IS NULL OR length(desired_description)>200) THEN
    RAISE EXCEPTION 'Invalid description' USING ERRCODE='23514'; END IF;
  END IF;
  IF operation='role_create' THEN
   INSERT INTO {role}(name,description) VALUES(desired_name,coalesce(desired_description,'')) RETURNING id_role INTO target;
  ELSIF operation='role_patch' THEN
   UPDATE {role} SET name=coalesce(desired_name,name),description=coalesce(desired_description,description) WHERE id_role=target;
  ELSIF operation='role_delete' THEN
   IF EXISTS(SELECT 1 FROM {api_user_role} WHERE id_role=target) THEN RAISE EXCEPTION 'Role is referenced' USING ERRCODE='23503'; END IF;
   DELETE FROM {role_permission} WHERE id_role=target;
   DELETE FROM {role} WHERE id_role=target;
  END IF;
  IF operation IN ('role_create','role_permissions') THEN
   DELETE FROM {role_permission} WHERE id_role=target;
   INSERT INTO {role_permission}(id_role,id_permission) SELECT target,id_permission FROM {permission} WHERE resource||':'||action=ANY(grants);
   UPDATE {api_user} SET credential_version=credential_version+1 WHERE id_api_user IN (SELECT id_api_user FROM {api_user_role} WHERE id_role=target);
  END IF;
  RETURN target;
 END IF;

 IF operation='account_create' THEN
  PERFORM @schema@.api_require_rbac('api_user','create');
  selected_role:=body->>'role_identifier';
  PERFORM 1 FROM {role} WHERE id_role=selected_role AND name NOT IN ('master','super_administrator') AND left(name,9)<>'identity_' FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown role' USING ERRCODE='23503'; END IF;
  SELECT coalesce(array_agg(p.resource||':'||p.action),ARRAY[]::text[]) INTO grants
   FROM {role_permission} rp JOIN {permission} p USING(id_permission) WHERE rp.id_role=selected_role;
  PERFORM @schema@.api_delegable(grants);
  INSERT INTO {api_user}(username) VALUES(body->>'username') RETURNING id_api_user INTO target;
  INSERT INTO {api_user_role}(id_api_user,id_role) VALUES(target,selected_role);
  IF body->>'app_user_name' IS NOT NULL THEN
   INSERT INTO {app_user}(personal_name) VALUES(body->>'app_user_name') RETURNING id_app_user INTO person;
   INSERT INTO {app_user_api}(id_app_user,id_api_user) VALUES(person,target);
  END IF;
  INSERT INTO {api_user_credential}(id_api_user,credential_kind,secret_hash) VALUES(target,'client_credentials',body->>'initial_hash') RETURNING id_api_user_credential INTO result;
  RETURN target||':'||result;
 END IF;

 IF operation IN ('account_role','account_permissions','permission_add','permission_delete','account_active','account_delete','client_issue','client_revoke') THEN
  PERFORM @schema@.api_require_rbac(CASE WHEN operation IN ('account_permissions','permission_add','permission_delete') THEN 'permission_assignment' ELSE 'api_user' END,
   CASE WHEN operation IN ('account_delete','client_revoke','permission_delete') THEN 'delete' WHEN operation='permission_add' THEN 'create' ELSE 'update' END);
  IF (target=actor AND operation NOT IN ('client_issue','client_revoke')) OR EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=target) THEN
   RAISE EXCEPTION 'Protected identity' USING ERRCODE='42501'; END IF;
  PERFORM 1 FROM {api_user} WHERE id_api_user=target AND deleted_at IS NULL FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown identity' USING ERRCODE='23503'; END IF;
  SELECT coalesce(array_agg(DISTINCT p.resource||':'||p.action),ARRAY[]::text[]) INTO previous_grants
   FROM {api_user_role} ur JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE ur.id_api_user=target;
  PERFORM @schema@.api_delegable(previous_grants);
  IF operation='account_role' THEN
   selected_role:=body->>'role_identifier';
   PERFORM 1 FROM {role} WHERE id_role=selected_role AND name NOT IN ('master','super_administrator') AND left(name,9)<>'identity_' FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Unknown role' USING ERRCODE='23503'; END IF;
   SELECT coalesce(array_agg(p.resource||':'||p.action),ARRAY[]::text[]) INTO grants
    FROM {role_permission} rp JOIN {permission} p USING(id_permission) WHERE rp.id_role=selected_role;
   PERFORM @schema@.api_delegable(grants);
   DELETE FROM {api_user_role} WHERE id_api_user=target AND id_role IN (SELECT id_role FROM {role} WHERE left(name,9)<>'identity_');
   INSERT INTO {api_user_role}(id_api_user,id_role) VALUES(target,selected_role);
  ELSIF operation IN ('account_permissions','permission_add') THEN
   SELECT coalesce(array_agg(v),ARRAY[]::text[]) INTO grants FROM jsonb_array_elements_text(body->'permissions') v;
   PERFORM @schema@.api_delegable(grants);
   INSERT INTO {role}(name,is_system) VALUES('identity_'||target,true) ON CONFLICT(name) DO NOTHING;
   SELECT id_role INTO individual_role FROM {role} WHERE name='identity_'||target;
   INSERT INTO {api_user_role}(id_api_user,id_role) VALUES(target,individual_role) ON CONFLICT DO NOTHING;
   IF operation='account_permissions' THEN DELETE FROM {role_permission} WHERE id_role=individual_role; END IF;
   INSERT INTO {role_permission}(id_role,id_permission) SELECT individual_role,id_permission FROM {permission} WHERE resource||':'||action=ANY(grants) ON CONFLICT DO NOTHING;
   IF operation='permission_add' THEN
    SELECT rp.id_role_permission INTO result FROM {role_permission} rp JOIN {permission} p USING(id_permission)
     WHERE rp.id_role=individual_role AND p.resource||':'||p.action=grants[1];
   END IF;
  ELSIF operation='permission_delete' THEN
   DELETE FROM {role_permission} rp USING {role} r
    WHERE rp.id_role=r.id_role AND r.name='identity_'||target AND rp.id_role_permission=body->>'permission_identifier';
   IF NOT FOUND THEN RAISE EXCEPTION 'Unknown grant' USING ERRCODE='23503'; END IF;
  ELSIF operation='account_active' THEN
   UPDATE {api_user} SET is_active=(body->>'is_active')::boolean WHERE id_api_user=target;
  ELSIF operation='account_delete' THEN
   UPDATE {api_user} SET is_active=false,deleted_at=CURRENT_TIMESTAMP WHERE id_api_user=target;
  ELSIF operation='client_issue' THEN
   INSERT INTO {api_user_credential}(id_api_user,credential_kind,secret_hash) VALUES(target,'client_credentials',body->>'initial_hash') RETURNING id_api_user_credential INTO result;
  ELSIF operation='client_revoke' THEN
   UPDATE {api_user_credential} SET revoked_at=CURRENT_TIMESTAMP WHERE id_api_user=target AND id_api_user_credential=body->>'credential' AND credential_kind='client_credentials';
  END IF;
  UPDATE {api_user} SET credential_version=credential_version+1 WHERE id_api_user=target;
  RETURN coalesce(result,target);
 END IF;
 RAISE EXCEPTION 'Unknown RBAC operation' USING ERRCODE='23514';
END $$;

-- Legacy profile payloads keep their historical ceilings, but cannot launder a
-- narrowly scoped token into a broader account or credential.
ALTER FUNCTION @schema@.api_create_account(text,text,text,text[],text) RENAME TO api_create_account_v1;
REVOKE ALL ON FUNCTION @schema@.api_create_account_v1(text,text,text,text[],text) FROM PUBLIC,ouroboros_runtime;
CREATE FUNCTION @schema@.api_create_account(account_name text, profile text, person_name text, grants text[], initial_hash text)
RETURNS text[] LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE inherited text[];
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 PERFORM @schema@.api_require_rbac('api_user','create');
 SELECT coalesce(array_agg(p.resource||':'||p.action),ARRAY[]::text[]) INTO inherited
  FROM {role} r JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE r.name=profile;
 PERFORM @schema@.api_delegable(inherited);
 PERFORM @schema@.api_delegable(grants);
 RETURN @schema@.api_create_account_v1(account_name,profile,person_name,grants,initial_hash);
END $$;

ALTER FUNCTION @schema@.api_assign_role(text,text) RENAME TO api_assign_role_v1;
REVOKE ALL ON FUNCTION @schema@.api_assign_role_v1(text,text) FROM PUBLIC,ouroboros_runtime;
CREATE FUNCTION @schema@.api_assign_role(target text, profile text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE grants text[];
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 PERFORM @schema@.api_require_rbac('api_user','update');
 SELECT coalesce(array_agg(DISTINCT p.resource||':'||p.action),ARRAY[]::text[]) INTO grants
  FROM {api_user_role} ur JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE ur.id_api_user=target;
 PERFORM @schema@.api_delegable(grants);
 SELECT coalesce(array_agg(p.resource||':'||p.action),ARRAY[]::text[]) INTO grants
  FROM {role} r JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE r.name=profile;
 PERFORM @schema@.api_delegable(grants);
 PERFORM @schema@.api_assign_role_v1(target,profile);
END $$;

CREATE OR REPLACE FUNCTION @schema@.api_set_setting(setting_name text, value numeric, low numeric, high numeric)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 PERFORM @schema@.api_require_rbac('operator_setting','update');
 IF setting_name NOT IN ('request_bytes','batch_items','page_size','token_ttl_seconds') OR NOT (low<=value AND value<=high)
  OR value<>trunc(value) OR low<>trunc(low) OR high<>trunc(high) THEN
  RAISE EXCEPTION 'Invalid setting range' USING ERRCODE='23514'; END IF;
 INSERT INTO {operator_setting}(name,minimum_value,maximum_value,current_value) VALUES(setting_name,low,high,value)
 ON CONFLICT(name) DO UPDATE SET minimum_value=excluded.minimum_value,maximum_value=excluded.maximum_value,current_value=excluded.current_value;
END $$;

CREATE OR REPLACE FUNCTION @schema@.api_add_rule(target text, rule text, resource_name text, action_name text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),''); result text; target_grants text[];
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 PERFORM @schema@.api_require_rbac('access_rule','create');
 IF target IS NULL OR resource_name='*' THEN
  IF NOT EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) THEN
   RAISE EXCEPTION 'Global rules require reserved authority' USING ERRCODE='42501'; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=target) THEN
   RAISE EXCEPTION 'Protected identity' USING ERRCODE='42501'; END IF;
  SELECT coalesce(array_agg(DISTINCT p.resource||':'||p.action),ARRAY[]::text[]) INTO target_grants
   FROM {api_user_role} ur JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE ur.id_api_user=target;
  PERFORM @schema@.api_delegable(target_grants);
  PERFORM @schema@.api_delegable(ARRAY[resource_name||':'||action_name]);
 END IF;
 IF resource_name='installation_plan' THEN RAISE EXCEPTION 'Protected plan' USING ERRCODE='42501'; END IF;
 INSERT INTO {access_rule}(id_api_user,rule_kind,resource,action) VALUES(target,rule,resource_name,action_name) RETURNING id_access_rule INTO result;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION @schema@.api_remove_rule(rule_id text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),''); target text; resource_name text; action_name text; target_grants text[];
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 PERFORM @schema@.api_require_rbac('access_rule','delete');
 SELECT id_api_user,resource,action INTO target,resource_name,action_name FROM {access_rule} WHERE id_access_rule=rule_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown rule' USING ERRCODE='23503'; END IF;
 IF target IS NULL OR resource_name='*' THEN
  IF NOT EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) THEN
   RAISE EXCEPTION 'Global rules require reserved authority' USING ERRCODE='42501'; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=target) THEN
   RAISE EXCEPTION 'Protected identity' USING ERRCODE='42501'; END IF;
  SELECT coalesce(array_agg(DISTINCT p.resource||':'||p.action),ARRAY[]::text[]) INTO target_grants
   FROM {api_user_role} ur JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE ur.id_api_user=target;
  PERFORM @schema@.api_delegable(target_grants);
  PERFORM @schema@.api_delegable(ARRAY[resource_name||':'||action_name]);
 END IF;
 DELETE FROM {access_rule} WHERE id_access_rule=rule_id;
END $$;

DO $$ DECLARE section_name text; action_name text;
BEGIN
 FOREACH section_name IN ARRAY ARRAY['identity','roles','authorization','catalogue','personal','subscriptions','settings','audit'] LOOP
  FOREACH action_name IN ARRAY ARRAY['read','create','update','delete'] LOOP
   INSERT INTO {permission}(resource,action) VALUES(section_name,action_name) ON CONFLICT(resource,action) DO NOTHING;
   INSERT INTO {role_permission}(id_role,id_permission)
    SELECT r.id_role,p.id_permission FROM {role} r CROSS JOIN {permission} p
    WHERE r.name='administrator' AND p.resource=section_name AND p.action=action_name ON CONFLICT DO NOTHING;
  END LOOP;
 END LOOP;
END $$;

REVOKE ALL ON FUNCTION @schema@.api_section(text), @schema@.api_rule_allows(text,text,text),
 @schema@.api_require_rbac(text,text), @schema@.api_delegable(text[]), @schema@.api_rbac(text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION @schema@.api_rbac(text,text,jsonb) TO ouroboros_runtime;
REVOKE ALL ON FUNCTION @schema@.api_create_account(text,text,text,text[],text), @schema@.api_assign_role(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION @schema@.api_create_account(text,text,text,text[],text), @schema@.api_assign_role(text,text) TO ouroboros_runtime;
REVOKE ALL ON FUNCTION @schema@.api_set_active(text,boolean), @schema@.api_set_permissions(text,text[]),
 @schema@.api_issue_client(text,text), @schema@.api_revoke_client(text) FROM ouroboros_runtime;
