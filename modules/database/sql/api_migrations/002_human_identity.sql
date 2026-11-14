-- Both human login names resolve to one active person and one human credential.
-- Display names and integration secrets never authenticate a human implicitly.
CREATE OR REPLACE FUNCTION @schema@.api_credential(identifier text, kind text)
RETURNS TABLE(actor text, credential text, version bigint, password_hash text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 WITH matched_people AS (
   SELECT p.id_app_user FROM {app_user} p
     WHERE kind='human_password' AND p.is_active AND p.username=identifier
   UNION
   SELECT l.id_app_user FROM {api_user} a JOIN {app_user_api} l USING(id_api_user)
     JOIN {app_user} p USING(id_app_user)
     WHERE kind='human_password' AND a.username=identifier AND a.is_active
       AND l.valid_until IS NULL AND p.is_active
 ), human_candidates AS (
   SELECT DISTINCT a.id_api_user AS actor,c.id_api_user_credential AS credential,
          a.credential_version AS version,c.secret_hash AS password_hash
     FROM matched_people p JOIN {app_user_api} l USING(id_app_user)
     JOIN {api_user} a USING(id_api_user) JOIN {api_user_credential} c USING(id_api_user)
     WHERE (SELECT count(*) FROM matched_people)=1 AND l.valid_until IS NULL
       AND a.is_active AND c.credential_kind='human_password' AND c.revoked_at IS NULL
       AND (SELECT count(*) FROM {app_user_api} current_link
            JOIN {app_user} current_person USING(id_app_user)
            WHERE current_link.id_api_user=a.id_api_user AND current_link.valid_until IS NULL
              AND current_person.is_active)=1
 )
 SELECT * FROM human_candidates WHERE (SELECT count(*) FROM human_candidates)=1
 UNION ALL
 SELECT a.id_api_user,c.id_api_user_credential,a.credential_version,c.secret_hash
 FROM {api_user} a JOIN {api_user_credential} c USING(id_api_user)
 WHERE kind='client_credentials' AND a.is_active AND c.revoked_at IS NULL
   AND c.credential_kind='client_credentials' AND c.id_api_user_credential=identifier;
$$;
REVOKE ALL ON FUNCTION @schema@.api_credential(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION @schema@.api_credential(text,text) TO ouroboros_runtime;
