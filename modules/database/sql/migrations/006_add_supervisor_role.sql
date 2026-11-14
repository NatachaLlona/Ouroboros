-- Extend the fixed role set without replacing accounts or credentials.
ALTER TABLE public.api_users DROP CONSTRAINT api_users_role_check;
ALTER TABLE public.api_users ADD CONSTRAINT api_users_role_check
    CHECK (role IN ('standard', 'supervisor', 'administrator'));
