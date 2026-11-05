ALTER TABLE public.api_users
    ADD COLUMN credential_version BIGINT NOT NULL DEFAULT 1
    CONSTRAINT api_users_credential_version_check CHECK (credential_version >= 1);
