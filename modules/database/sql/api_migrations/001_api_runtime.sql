-- Database-v1 additive API capability migration. Render only validated identifiers.
-- No historical table, generated identity, bootstrap account or password is replaced.
CREATE FUNCTION @schema@.api_can(actor text, resource_name text, action_name text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM {api_user} WHERE id_api_user=actor AND is_active)
 AND NOT EXISTS(SELECT 1 FROM {access_rule} WHERE (id_api_user IS NULL OR id_api_user=actor)
   AND rule_kind='deny' AND resource IN (resource_name,'*') AND action=action_name)
 AND (NOT EXISTS(SELECT 1 FROM {access_rule} WHERE (id_api_user IS NULL OR id_api_user=actor) AND rule_kind='allow')
   OR EXISTS(SELECT 1 FROM {access_rule} WHERE (id_api_user IS NULL OR id_api_user=actor)
     AND rule_kind='allow' AND resource IN (resource_name,'*') AND action=action_name))
 AND (EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor)
   OR EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role_permission} rp USING(id_role)
      JOIN {permission} p USING(id_permission) WHERE ur.id_api_user=actor
      AND p.resource=resource_name AND p.action=action_name));
$$;

CREATE FUNCTION @schema@.api_credential(identifier text, kind text)
RETURNS TABLE(actor text, credential text, version bigint, password_hash text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT au.id_api_user, ac.id_api_user_credential, au.credential_version, ac.secret_hash
 FROM {api_user} au JOIN {api_user_credential} ac USING(id_api_user)
 WHERE au.is_active AND ac.revoked_at IS NULL AND ac.credential_kind=kind
 AND ((kind='human_password' AND au.username=identifier)
   OR (kind='client_credentials' AND ac.id_api_user_credential=identifier));
$$;

CREATE FUNCTION @schema@.api_credential_current(credential text, actor text, kind text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM {api_user_credential} WHERE id_api_user_credential=credential
   AND id_api_user=actor AND credential_kind=kind AND revoked_at IS NULL);
$$;

CREATE FUNCTION @schema@.api_create_account(account_name text, profile text, person_name text, grants text[], initial_hash text)
RETURNS text[] LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text := nullif(current_setting('ouroboros.actor_api_user',true),'');
 manager boolean; target text; person text; assigned_role text; individual_role text; scope text; permission_id text; credential text;
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF NOT @schema@.api_can(actor,'api_user','create') THEN RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 manager := NOT EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor)
  AND NOT EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator');
 IF profile NOT IN ('user','manager','administrator') OR (manager AND profile='administrator') THEN
  RAISE EXCEPTION 'Profile assignment denied' USING ERRCODE='42501'; END IF;
 IF manager AND NOT EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='manager') THEN
  RAISE EXCEPTION 'Account creation denied' USING ERRCODE='42501'; END IF;
 -- Every inherited permission of the requested profile must fit the creator's authority.
 IF manager AND EXISTS(SELECT 1 FROM {role} r JOIN {role_permission} rp USING(id_role)
   JOIN {permission} p USING(id_permission) WHERE r.name=profile AND NOT @schema@.api_can(actor,p.resource,p.action)) THEN
  RAISE EXCEPTION 'Profile exceeds creator authority' USING ERRCODE='42501'; END IF;
 SELECT id_role INTO assigned_role FROM {role} WHERE name=profile;
 IF assigned_role IS NULL THEN RAISE EXCEPTION 'Unknown profile' USING ERRCODE='23514'; END IF;
 INSERT INTO {api_user}(username) VALUES(account_name) RETURNING id_api_user INTO target;
 INSERT INTO {api_user_role}(id_api_user,id_role) VALUES(target,assigned_role);
 IF person_name IS NOT NULL THEN
  INSERT INTO {app_user}(personal_name) VALUES(person_name) RETURNING id_app_user INTO person;
  INSERT INTO {app_user_api}(id_app_user,id_api_user) VALUES(person,target);
 END IF;
 IF cardinality(grants)>0 THEN
  INSERT INTO {role}(name) VALUES('identity_'||target) RETURNING id_role INTO individual_role;
  INSERT INTO {api_user_role}(id_api_user,id_role) VALUES(target,individual_role);
  FOREACH scope IN ARRAY grants LOOP
   SELECT id_permission INTO permission_id FROM {permission} WHERE resource=split_part(scope,':',1) AND action=split_part(scope,':',2);
   IF permission_id IS NULL OR NOT @schema@.api_can(actor,split_part(scope,':',1),split_part(scope,':',2)) THEN
    RAISE EXCEPTION 'Permission exceeds creator authority' USING ERRCODE='42501'; END IF;
   INSERT INTO {role_permission}(id_role,id_permission) VALUES(individual_role,permission_id) ON CONFLICT DO NOTHING;
  END LOOP;
 END IF;
 INSERT INTO {api_user_credential}(id_api_user,credential_kind,secret_hash)
  VALUES(target,'client_credentials',initial_hash) RETURNING id_api_user_credential INTO credential;
 RETURN ARRAY[target,credential];
END $$;

CREATE FUNCTION @schema@.api_assign_role(target text, profile text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),''); assigned_role text;
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF actor=target OR NOT @schema@.api_can(actor,'api_user','update') OR NOT (
   EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor)
   OR EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator'))
   OR EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=target)
   OR profile NOT IN ('user','manager','administrator') THEN
   RAISE EXCEPTION 'Profile assignment denied' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM {api_user} WHERE id_api_user=target FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown identity' USING ERRCODE='23503'; END IF;
 SELECT id_role INTO assigned_role FROM {role} WHERE name=profile;
 DELETE FROM {api_user_role} WHERE id_api_user=target;
 INSERT INTO {api_user_role}(id_api_user,id_role) VALUES(target,assigned_role);
 UPDATE {api_user} SET credential_version=credential_version+1 WHERE id_api_user=target;
END $$;

CREATE FUNCTION @schema@.api_issue_client(target text, hash text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),''); result text;
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF (target<>actor AND (NOT @schema@.api_can(actor,'api_user','update') OR NOT (
   EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) OR
   EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator'))))
   OR EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=target) THEN
   RAISE EXCEPTION 'Credential issuance denied' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM {api_user} WHERE id_api_user=actor AND is_active) THEN
   RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 INSERT INTO {api_user_credential}(id_api_user,credential_kind,secret_hash)
  VALUES(target,'client_credentials',hash) RETURNING id_api_user_credential INTO result;
 RETURN result;
END $$;

CREATE FUNCTION @schema@.api_set_active(target text, active boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),'');
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF target=actor OR NOT @schema@.api_can(actor,'api_user','update') OR NOT (
  EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) OR
  EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator'))
  OR EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=target) THEN
  RAISE EXCEPTION 'Identity administration denied' USING ERRCODE='42501'; END IF;
 UPDATE {api_user} SET is_active=active,credential_version=credential_version+1 WHERE id_api_user=target;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown identity' USING ERRCODE='23503'; END IF;
END $$;

CREATE FUNCTION @schema@.api_revoke_client(credential text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),''); target text;
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 SELECT id_api_user INTO target FROM {api_user_credential} WHERE id_api_user_credential=credential AND credential_kind='client_credentials' FOR UPDATE;
 IF target IS NULL OR (target<>actor AND (NOT @schema@.api_can(actor,'api_user','update') OR NOT (
   EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) OR
   EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator')))) THEN
  RAISE EXCEPTION 'Credential revocation denied' USING ERRCODE='42501'; END IF;
 UPDATE {api_user_credential} SET revoked_at=clock_timestamp() WHERE id_api_user_credential=credential AND revoked_at IS NULL;
 UPDATE {api_user} SET credential_version=credential_version+1 WHERE id_api_user=target;
END $$;

CREATE FUNCTION @schema@.api_set_setting(setting_name text, value numeric, low numeric, high numeric)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),'');
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF NOT @schema@.api_can(actor,'operator_setting','update') OR NOT (
   EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor)
   OR EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator')) THEN
  RAISE EXCEPTION 'Setting change denied' USING ERRCODE='42501'; END IF;
 IF setting_name NOT IN ('request_bytes','batch_items','page_size','token_ttl_seconds') OR NOT (low<=value AND value<=high) THEN
  RAISE EXCEPTION 'Invalid setting range' USING ERRCODE='23514'; END IF;
 INSERT INTO {operator_setting}(name,minimum_value,maximum_value,current_value) VALUES(setting_name,low,high,value)
 ON CONFLICT(name) DO UPDATE SET minimum_value=excluded.minimum_value, maximum_value=excluded.maximum_value,current_value=excluded.current_value;
END $$;

CREATE FUNCTION @schema@.api_add_rule(target text, rule text, resource_name text, action_name text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),''); result text;
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF NOT @schema@.api_can(actor,'access_rule','create') OR NOT (
  EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) OR
  EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator')) THEN
  RAISE EXCEPTION 'Rule management denied' USING ERRCODE='42501'; END IF;
 IF resource_name='installation_plan' THEN RAISE EXCEPTION 'Reserved plan rule' USING ERRCODE='42501'; END IF;
 INSERT INTO {access_rule}(id_api_user,rule_kind,resource,action) VALUES(target,rule,resource_name,action_name)
 RETURNING id_access_rule INTO result;
 RETURN result;
END $$;

CREATE FUNCTION @schema@.api_remove_rule(rule_id text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),'');
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF NOT @schema@.api_can(actor,'access_rule','delete') OR NOT (
  EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) OR
  EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator')) THEN
  RAISE EXCEPTION 'Rule management denied' USING ERRCODE='42501'; END IF;
 DELETE FROM {access_rule} WHERE id_access_rule=rule_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown rule' USING ERRCODE='23503'; END IF;
END $$;

CREATE FUNCTION @schema@.api_set_permissions(target text, grants text[])
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor text:=nullif(current_setting('ouroboros.actor_api_user',true),''); individual_role text; scope text; permission_id text;
BEGIN
 PERFORM pg_advisory_xact_lock(719230818);
 IF actor=target OR NOT @schema@.api_can(actor,'permission_assignment','update') OR NOT (
  EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=actor) OR
  EXISTS(SELECT 1 FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=actor AND r.name='administrator'))
  OR EXISTS(SELECT 1 FROM {super_administrator} WHERE id_api_user=target) THEN
  RAISE EXCEPTION 'Permission assignment denied' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM {api_user} WHERE id_api_user=target FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown identity' USING ERRCODE='23503'; END IF;
 INSERT INTO {role}(name) VALUES('identity_'||target) ON CONFLICT(name) DO NOTHING;
 SELECT id_role INTO individual_role FROM {role} WHERE name='identity_'||target;
 INSERT INTO {api_user_role}(id_api_user,id_role) VALUES(target,individual_role) ON CONFLICT DO NOTHING;
 DELETE FROM {role_permission} WHERE id_role=individual_role;
 FOREACH scope IN ARRAY grants LOOP
  SELECT id_permission INTO permission_id FROM {permission} WHERE resource=split_part(scope,':',1) AND action=split_part(scope,':',2);
  IF permission_id IS NULL OR NOT @schema@.api_can(actor,split_part(scope,':',1),split_part(scope,':',2)) THEN
   RAISE EXCEPTION 'Permission exceeds administrator authority' USING ERRCODE='42501'; END IF;
  INSERT INTO {role_permission}(id_role,id_permission) VALUES(individual_role,permission_id) ON CONFLICT DO NOTHING;
 END LOOP;
 UPDATE {api_user} SET credential_version=credential_version+1 WHERE id_api_user=target;
END $$;

-- Remove the broad identity/authorization write capabilities inherited from the baseline.
DO $$
DECLARE profile text; resource_name text; action_name text; role_id text; permission_id text;
 personal boolean;
BEGIN
 FOREACH profile IN ARRAY ARRAY['user','manager','administrator'] LOOP
  INSERT INTO {role}(name) VALUES(profile) ON CONFLICT(name) DO NOTHING;
  SELECT id_role INTO role_id FROM {role} WHERE name=profile;
  FOREACH resource_name IN ARRAY ARRAY['test','work','platform','work_availability','work_classification',
   'work_title_alias','work_external_reference','user_work','user_platform','watch_list_entry','watch_history',
   'tag','tag_category','tag_relationship','tag_category_relationship','work_tag','platform_plan',
   'platform_promotion','platform_subscription','subscription_charge','subscription_reminder','work_submission',
   'api_user','permission_assignment','access_rule','operator_setting','api_audit_log','record_version'] LOOP
   personal := resource_name IN ('user_work','user_platform','watch_list_entry','watch_history','tag',
    'tag_category','tag_relationship','tag_category_relationship','work_tag','platform_subscription',
    'subscription_charge','subscription_reminder','work_submission');
   FOREACH action_name IN ARRAY ARRAY['create','read','update','delete'] LOOP
    INSERT INTO {permission}(resource,action) VALUES(resource_name,action_name) ON CONFLICT(resource,action) DO NOTHING;
    SELECT id_permission INTO permission_id FROM {permission} WHERE resource=resource_name AND action=action_name;
    IF profile='administrator' OR (personal AND action_name='read')
     OR (profile='manager' AND resource_name='api_user' AND action_name='create') THEN
     INSERT INTO {role_permission}(id_role,id_permission) VALUES(role_id,permission_id) ON CONFLICT DO NOTHING;
    END IF;
   END LOOP;
  END LOOP;
 END LOOP;
END $$;

REVOKE INSERT, UPDATE, DELETE ON {api_user}, {app_user}, {app_user_api}, {app_user_external_reference},
 {role}, {permission}, {api_user_role}, {role_permission}, {access_rule} FROM ouroboros_runtime;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA @schema@ FROM PUBLIC;
GRANT EXECUTE ON FUNCTION @schema@.api_can(text,text,text), @schema@.api_credential(text,text),
 @schema@.api_credential_current(text,text,text), @schema@.api_create_account(text,text,text,text[],text),
 @schema@.api_assign_role(text,text), @schema@.api_issue_client(text,text), @schema@.api_revoke_client(text),
 @schema@.api_set_setting(text,numeric,numeric,numeric), @schema@.api_add_rule(text,text,text,text),
 @schema@.api_set_active(text,boolean), @schema@.api_remove_rule(text),
 @schema@.api_set_permissions(text,text[]) TO ouroboros_runtime;
