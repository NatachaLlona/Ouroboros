-- Ouroboros catalogue phase one. No catalogue records are inserted.
-- Keep Foundation migrations 001-004 and their checksums unchanged.
CREATE FUNCTION public.protect_catalogue_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Generated IDs cannot be assigned; guard their mutable source columns too.
    IF (to_jsonb(NEW) -> ('sequence_' || TG_TABLE_NAME)) IS DISTINCT FROM
       (to_jsonb(OLD) -> ('sequence_' || TG_TABLE_NAME)) OR
       (to_jsonb(NEW) -> ('prefix_' || TG_TABLE_NAME)) IS DISTINCT FROM
       (to_jsonb(OLD) -> ('prefix_' || TG_TABLE_NAME)) OR
       (to_jsonb(NEW) -> ('fantasy_name_' || TG_TABLE_NAME)) IS DISTINCT FROM
       (to_jsonb(OLD) -> ('fantasy_name_' || TG_TABLE_NAME)) THEN
        RAISE EXCEPTION 'Catalogue identity and fixed metadata are immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TABLE public.works (
    sequence_works BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_works > 0),
    prefix_works TEXT NOT NULL DEFAULT 'WK' CHECK (prefix_works = 'WK'),
    fantasy_name_works TEXT NOT NULL DEFAULT 'Obras' CHECK (fantasy_name_works = 'Obras'),
    id_works TEXT GENERATED ALWAYS AS
        (prefix_works || lpad(sequence_works::text, greatest(7, length(sequence_works::text)), '0')) STORED PRIMARY KEY,
    title TEXT NOT NULL,
    title_language TEXT NOT NULL,
    synopsis TEXT
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.works
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.platforms (
    sequence_platforms BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_platforms > 0),
    prefix_platforms TEXT NOT NULL DEFAULT 'PL' CHECK (prefix_platforms = 'PL'),
    fantasy_name_platforms TEXT NOT NULL DEFAULT 'Plataformas' CHECK (fantasy_name_platforms = 'Plataformas'),
    id_platforms TEXT GENERATED ALWAYS AS
        (prefix_platforms || lpad(sequence_platforms::text, greatest(7, length(sequence_platforms::text)), '0')) STORED PRIMARY KEY,
    platform_name TEXT NOT NULL,
    platform_is_paid BOOLEAN NOT NULL,
    platform_is_episodes BOOLEAN NOT NULL,
    platform_is_duration_time BOOLEAN NOT NULL,
    price_amount NUMERIC CHECK (price_amount >= 0 AND price_amount < 'Infinity'::numeric),
    price_currency TEXT
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.platforms
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.work_availabilities (
    sequence_work_availabilities BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_work_availabilities > 0),
    prefix_work_availabilities TEXT NOT NULL DEFAULT 'AV' CHECK (prefix_work_availabilities = 'AV'),
    fantasy_name_work_availabilities TEXT NOT NULL DEFAULT 'Disponibilidade de obras por plataformas' CHECK (fantasy_name_work_availabilities = 'Disponibilidade de obras por plataformas'),
    id_work_availabilities TEXT GENERATED ALWAYS AS
        (prefix_work_availabilities || lpad(sequence_work_availabilities::text, greatest(7, length(sequence_work_availabilities::text)), '0')) STORED PRIMARY KEY,
    id_works TEXT NOT NULL REFERENCES public.works ON DELETE RESTRICT,
    id_platforms TEXT NOT NULL REFERENCES public.platforms ON DELETE RESTRICT,
    duration_minutes NUMERIC CHECK (duration_minutes > 0 AND duration_minutes < 'Infinity'::numeric),
    episode_quantity BIGINT CHECK (episode_quantity > 0),
    publisher_profile TEXT,
    url TEXT,
    UNIQUE (id_works, id_work_availabilities)
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.work_availabilities
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.tags (
    sequence_tags BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_tags > 0),
    prefix_tags TEXT NOT NULL DEFAULT 'TG' CHECK (prefix_tags = 'TG'),
    fantasy_name_tags TEXT NOT NULL DEFAULT 'Tags' CHECK (fantasy_name_tags = 'Tags'),
    id_tags TEXT GENERATED ALWAYS AS
        (prefix_tags || lpad(sequence_tags::text, greatest(7, length(sequence_tags::text)), '0')) STORED PRIMARY KEY,
    tag_name TEXT NOT NULL CHECK (tag_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'),
    display_name_tags TEXT NOT NULL,
    description_tags TEXT
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.tags
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.tag_categories (
    sequence_tag_categories BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_tag_categories > 0),
    prefix_tag_categories TEXT NOT NULL DEFAULT 'TC' CHECK (prefix_tag_categories = 'TC'),
    fantasy_name_tag_categories TEXT NOT NULL DEFAULT 'Categorias de tags' CHECK (fantasy_name_tag_categories = 'Categorias de tags'),
    id_tag_categories TEXT GENERATED ALWAYS AS
        (prefix_tag_categories || lpad(sequence_tag_categories::text, greatest(7, length(sequence_tag_categories::text)), '0')) STORED PRIMARY KEY,
    tag_category_name TEXT NOT NULL CHECK (tag_category_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'),
    display_name_tag_categories TEXT NOT NULL,
    description_tag_categories TEXT
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.tag_categories
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.tag_category_relationships (
    sequence_tag_category_relationships BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_tag_category_relationships > 0),
    prefix_tag_category_relationships TEXT NOT NULL DEFAULT 'CR' CHECK (prefix_tag_category_relationships = 'CR'),
    fantasy_name_tag_category_relationships TEXT NOT NULL DEFAULT 'Vínculos entre tags e categorias' CHECK (fantasy_name_tag_category_relationships = 'Vínculos entre tags e categorias'),
    id_tag_category_relationships TEXT GENERATED ALWAYS AS
        (prefix_tag_category_relationships || lpad(sequence_tag_category_relationships::text, greatest(7, length(sequence_tag_category_relationships::text)), '0')) STORED PRIMARY KEY,
    id_tags TEXT NOT NULL REFERENCES public.tags ON DELETE RESTRICT,
    id_tag_categories TEXT NOT NULL REFERENCES public.tag_categories ON DELETE RESTRICT,
    UNIQUE (id_tags, id_tag_categories)
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.tag_category_relationships
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.tag_relationships (
    sequence_tag_relationships BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_tag_relationships > 0),
    prefix_tag_relationships TEXT NOT NULL DEFAULT 'TR' CHECK (prefix_tag_relationships = 'TR'),
    fantasy_name_tag_relationships TEXT NOT NULL DEFAULT 'Relacionamentos entre tags' CHECK (fantasy_name_tag_relationships = 'Relacionamentos entre tags'),
    id_tag_relationships TEXT GENERATED ALWAYS AS
        (prefix_tag_relationships || lpad(sequence_tag_relationships::text, greatest(7, length(sequence_tag_relationships::text)), '0')) STORED PRIMARY KEY,
    id_tags_source TEXT NOT NULL REFERENCES public.tags ON DELETE RESTRICT,
    id_tags_target TEXT NOT NULL REFERENCES public.tags ON DELETE RESTRICT
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.tag_relationships
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.work_classifications (
    sequence_work_classifications BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_work_classifications > 0),
    prefix_work_classifications TEXT NOT NULL DEFAULT 'WC' CHECK (prefix_work_classifications = 'WC'),
    fantasy_name_work_classifications TEXT NOT NULL DEFAULT 'Classificações de obras' CHECK (fantasy_name_work_classifications = 'Classificações de obras'),
    id_work_classifications TEXT GENERATED ALWAYS AS
        (prefix_work_classifications || lpad(sequence_work_classifications::text, greatest(7, length(sequence_work_classifications::text)), '0')) STORED PRIMARY KEY,
    work_classification_name TEXT NOT NULL CHECK (work_classification_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'),
    display_name_work_classifications TEXT NOT NULL,
    description_work_classifications TEXT
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.work_classifications
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.watchlist_entries (
    sequence_watchlist_entries BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_watchlist_entries > 0),
    prefix_watchlist_entries TEXT NOT NULL DEFAULT 'WS' CHECK (prefix_watchlist_entries = 'WS'),
    fantasy_name_watchlist_entries TEXT NOT NULL DEFAULT 'To Be Watched' CHECK (fantasy_name_watchlist_entries = 'To Be Watched'),
    id_watchlist_entries TEXT GENERATED ALWAYS AS
        (prefix_watchlist_entries || lpad(sequence_watchlist_entries::text, greatest(7, length(sequence_watchlist_entries::text)), '0')) STORED PRIMARY KEY,
    id_works TEXT NOT NULL REFERENCES public.works ON DELETE RESTRICT,
    id_work_availabilities TEXT,
    id_work_classifications_predicted TEXT REFERENCES public.work_classifications ON DELETE RESTRICT,
    observations TEXT,
    added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_works, id_work_availabilities) REFERENCES public.work_availabilities (id_works, id_work_availabilities) ON DELETE RESTRICT,
    UNIQUE (id_works, id_watchlist_entries)
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.watchlist_entries
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.watch_history (
    sequence_watch_history BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_watch_history > 0),
    prefix_watch_history TEXT NOT NULL DEFAULT 'WH' CHECK (prefix_watch_history = 'WH'),
    fantasy_name_watch_history TEXT NOT NULL DEFAULT 'Watched' CHECK (fantasy_name_watch_history = 'Watched'),
    id_watch_history TEXT GENERATED ALWAYS AS
        (prefix_watch_history || lpad(sequence_watch_history::text, greatest(7, length(sequence_watch_history::text)), '0')) STORED PRIMARY KEY,
    id_works TEXT NOT NULL REFERENCES public.works ON DELETE RESTRICT,
    id_work_availabilities TEXT,
    id_work_classifications TEXT REFERENCES public.work_classifications ON DELETE RESTRICT,
    observations TEXT,
    watched_at TIMESTAMPTZ,
    FOREIGN KEY (id_works, id_work_availabilities) REFERENCES public.work_availabilities (id_works, id_work_availabilities) ON DELETE RESTRICT,
    UNIQUE (id_works, id_watch_history)
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.watch_history
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

CREATE TABLE public.work_tags (
    sequence_work_tags BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_work_tags > 0),
    prefix_work_tags TEXT NOT NULL DEFAULT 'WT' CHECK (prefix_work_tags = 'WT'),
    fantasy_name_work_tags TEXT NOT NULL DEFAULT 'Vínculos entre obras e tags' CHECK (fantasy_name_work_tags = 'Vínculos entre obras e tags'),
    id_work_tags TEXT GENERATED ALWAYS AS
        (prefix_work_tags || lpad(sequence_work_tags::text, greatest(7, length(sequence_work_tags::text)), '0')) STORED PRIMARY KEY,
    id_works TEXT NOT NULL REFERENCES public.works ON DELETE RESTRICT,
    id_tags TEXT REFERENCES public.tags ON DELETE RESTRICT,
    id_tag_relationships TEXT REFERENCES public.tag_relationships ON DELETE RESTRICT,
    id_watchlist_entries TEXT,
    id_watch_history TEXT,
    CHECK ((id_tags IS NOT NULL)::integer + (id_tag_relationships IS NOT NULL)::integer = 1),
    CHECK (id_watchlist_entries IS NULL OR id_watch_history IS NULL),
    FOREIGN KEY (id_works, id_watchlist_entries) REFERENCES public.watchlist_entries (id_works, id_watchlist_entries) ON DELETE RESTRICT,
    FOREIGN KEY (id_works, id_watch_history) REFERENCES public.watch_history (id_works, id_watch_history) ON DELETE RESTRICT
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.work_tags
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();

-- Composite UNIQUE indexes above also cover their leading work/tag lookups.
CREATE INDEX ON public.work_availabilities (id_platforms);
CREATE INDEX ON public.tag_category_relationships (id_tag_categories);
CREATE INDEX ON public.tag_relationships (id_tags_source);
CREATE INDEX ON public.tag_relationships (id_tags_target);
CREATE INDEX ON public.watchlist_entries (id_work_availabilities);
CREATE INDEX ON public.watchlist_entries (id_work_classifications_predicted);
CREATE INDEX ON public.watch_history (id_work_availabilities);
CREATE INDEX ON public.watch_history (id_work_classifications);
CREATE INDEX ON public.work_tags (id_works);
CREATE INDEX ON public.work_tags (id_tags);
CREATE INDEX ON public.work_tags (id_tag_relationships);
CREATE INDEX ON public.work_tags (id_watchlist_entries);
CREATE INDEX ON public.work_tags (id_watch_history);
