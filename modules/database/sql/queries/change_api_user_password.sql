UPDATE public.api_users
SET password_hash = %s, credential_version = credential_version + 1
WHERE id = %s;
