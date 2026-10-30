-- Preserve unknown historical dates; new rows use the shared server context.
ALTER TABLE public.test ADD COLUMN created_at TIMESTAMPTZ,
    ADD COLUMN created_at_timezone TEXT;
ALTER TABLE public.test ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN created_at_timezone SET DEFAULT public.catalogue_default_timezone();
CREATE TRIGGER test_creation_metadata BEFORE INSERT OR UPDATE ON public.test
    FOR EACH ROW EXECUTE FUNCTION public.catalogue_timestamp_defaults();
