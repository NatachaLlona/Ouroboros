SELECT password_hash, is_active, credential_version
FROM public.api_users WHERE id = %s FOR UPDATE;
