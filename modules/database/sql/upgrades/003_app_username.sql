-- Add an explicit human login without changing existing credentials or memberships.
ALTER TABLE {app_user} ADD COLUMN username TEXT;
ALTER TABLE {app_user} ADD CONSTRAINT app_username_valid
 CHECK (username IS NULL OR (username=btrim(username) AND length(username) BETWEEN 1 AND 128
                            AND username !~ '[[:cntrl:]]'));
ALTER TABLE {app_user} ADD CONSTRAINT app_username_unique UNIQUE(username);

-- Earlier enrollment labelled personal_name as the App name. Preserve that input
-- as a login only for an unambiguous existing human credential holder.
WITH candidates AS (
 SELECT DISTINCT p.id_app_user,p.personal_name
 FROM {app_user} p JOIN {app_user_api} l USING(id_app_user)
 JOIN {api_user} a USING(id_api_user)
 JOIN {api_user_credential} c USING(id_api_user)
 WHERE p.is_active AND a.is_active AND l.valid_until IS NULL
   AND c.credential_kind='human_password' AND c.revoked_at IS NULL
   AND p.personal_name=btrim(p.personal_name) AND length(p.personal_name) BETWEEN 1 AND 128
   AND p.personal_name !~ '[[:cntrl:]]'
)
UPDATE {app_user} p SET username=c.personal_name FROM candidates c
WHERE p.id_app_user=c.id_app_user AND p.username IS NULL
 AND (SELECT count(*) FROM candidates other WHERE other.personal_name=c.personal_name)=1
 AND NOT EXISTS(SELECT 1 FROM {api_user} a JOIN {app_user_api} l USING(id_api_user)
                WHERE a.username=c.personal_name AND a.is_active AND l.valid_until IS NULL
                  AND l.id_app_user<>c.id_app_user);
