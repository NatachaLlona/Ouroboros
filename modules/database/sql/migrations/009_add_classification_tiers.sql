-- Inspect once, without changing identity, names, descriptions or references.
-- The stored column comment makes any rank fallback observable after startup.
ALTER TABLE public.work_classifications ADD COLUMN tier BIGINT;

DO $$
DECLARE records bigint; first_sequence bigint; last_sequence bigint; strategy text;
BEGIN
    SELECT count(*), min(sequence_work_classifications), max(sequence_work_classifications)
      INTO records, first_sequence, last_sequence FROM public.work_classifications;
    IF records = 0 OR (first_sequence = 1 AND last_sequence = records) THEN
        strategy := 'preserved_sequence';
        UPDATE public.work_classifications SET tier = sequence_work_classifications;
    ELSE
        strategy := 'contiguous_sequence_rank';
        WITH ordered AS (
            SELECT id_work_classifications,
                   row_number() OVER (ORDER BY sequence_work_classifications, id_work_classifications) AS position
              FROM public.work_classifications
        )
        UPDATE public.work_classifications AS target SET tier = ordered.position
          FROM ordered WHERE target.id_work_classifications = ordered.id_work_classifications;
    END IF;
    EXECUTE format('COMMENT ON COLUMN public.work_classifications.tier IS %L',
        format('Migration009 one-time backfill: %s; inspected_count=%s; inspected_sequence_min=%s; inspected_sequence_max=%s. Tier is independent of sequence after this migration.',
            strategy, records, first_sequence, last_sequence));
    RAISE NOTICE 'Classification tier backfill: strategy=%, inspected_count=%, sequence_min=%, sequence_max=%',
        strategy, records, first_sequence, last_sequence;
END;
$$;

ALTER TABLE public.work_classifications ALTER COLUMN tier SET NOT NULL,
    ADD CONSTRAINT work_classifications_tier_positive CHECK (tier > 0),
    ADD CONSTRAINT work_classifications_tier_unique UNIQUE (tier) DEFERRABLE INITIALLY IMMEDIATE;

-- Trusted direct inserts also append; API validation rejects explicit null.
-- API writes acquire membership, actor and list locks before reaching this trigger.
CREATE FUNCTION public.classification_append_tier() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(719230819);
    IF NEW.tier IS NULL THEN
        SELECT coalesce(max(tier), 0) + 1 INTO NEW.tier FROM public.work_classifications;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER classification_tier_default BEFORE INSERT ON public.work_classifications
    FOR EACH ROW EXECUTE FUNCTION public.classification_append_tier();
