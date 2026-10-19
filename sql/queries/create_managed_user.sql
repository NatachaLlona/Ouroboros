INSERT INTO public.api_users (username, password_hash, scopes, role)
VALUES (%s, %s, %s, %s)
ON CONFLICT (username) DO NOTHING
RETURNING id, username, role, is_active, created_at;
