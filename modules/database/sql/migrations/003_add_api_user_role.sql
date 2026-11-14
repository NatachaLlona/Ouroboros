ALTER TABLE public.api_users
    ADD COLUMN role TEXT NOT NULL DEFAULT 'standard'
    CONSTRAINT api_users_role_check CHECK (role IN ('administrator', 'standard'));
