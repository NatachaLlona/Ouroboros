SELECT id, username, password_hash, is_active, scopes, role, credential_version FROM public.api_users WHERE username = %s;
