-- Historical creation dates/source zones are deliberately not backfilled.
CREATE FUNCTION public.catalogue_default_timezone() RETURNS text LANGUAGE sql STABLE AS $$
    SELECT coalesce(nullif(current_setting('ouroboros.application_timezone', true), ''), 'Europe/Lisbon');
$$;

CREATE FUNCTION public.catalogue_timestamp_defaults() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.created_at := coalesce(NEW.created_at, CURRENT_TIMESTAMP);
        NEW.created_at_timezone := coalesce(NEW.created_at_timezone, public.catalogue_default_timezone());
    ELSIF NEW.created_at IS DISTINCT FROM OLD.created_at OR
          NEW.created_at_timezone IS DISTINCT FROM OLD.created_at_timezone THEN
        RAISE EXCEPTION 'Creation metadata is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DO $$
DECLARE resource text;
BEGIN
    FOREACH resource IN ARRAY ARRAY['works','platforms','work_availabilities','tags','tag_categories',
        'tag_category_relationships','tag_relationships','work_tags','work_classifications','watchlist_entries','watch_history']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN created_at TIMESTAMPTZ, ADD COLUMN created_at_timezone TEXT', resource);
        -- Add defaults only after nullable columns exist, so prior rows remain NULL.
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN created_at_timezone SET DEFAULT public.catalogue_default_timezone()', resource);
        EXECUTE format('CREATE TRIGGER catalogue_timestamps BEFORE INSERT OR UPDATE ON public.%I
            FOR EACH ROW EXECUTE FUNCTION public.catalogue_timestamp_defaults()', resource);
    END LOOP;
END;
$$;

ALTER TABLE public.watchlist_entries ADD COLUMN added_at_timezone TEXT;
ALTER TABLE public.watchlist_entries ALTER COLUMN added_at_timezone SET DEFAULT public.catalogue_default_timezone();
ALTER TABLE public.watch_history ADD COLUMN watched_at_offset TEXT,
    ADD COLUMN watched_at_timezone TEXT,
    ADD CONSTRAINT watch_history_source_context CHECK (
        (watched_at IS NOT NULL OR (watched_at_offset IS NULL AND watched_at_timezone IS NULL))
        AND (watched_at_offset IS NULL OR watched_at_offset ~ '^[+-][0-9]{2}:[0-9]{2}(:[0-9]{2})?$')
    );
