INSERT INTO public.api_users (username, password_hash, scopes, role)
VALUES (%s, %s, %s, %s)
ON CONFLICT (username) DO NOTHING
RETURNING id, username, password_hash, is_active, scopes, role, credential_version;
