-- Preserve historical unknown access information as an empty set and NULL URL.
ALTER TABLE public.platforms
    ADD COLUMN platform_access_types TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN platform_url TEXT;

ALTER TABLE public.platforms
    ADD CONSTRAINT platforms_access_types_allowed CHECK (
        platform_access_types <@ ARRAY['application', 'website', 'link']::TEXT[]
        AND array_position(platform_access_types, NULL) IS NULL
        AND cardinality(platform_access_types) =
            (CASE WHEN 'application' = ANY(platform_access_types) THEN 1 ELSE 0 END
             + CASE WHEN 'website' = ANY(platform_access_types) THEN 1 ELSE 0 END
             + CASE WHEN 'link' = ANY(platform_access_types) THEN 1 ELSE 0 END)
        AND (cardinality(platform_access_types) = 0 OR array_ndims(platform_access_types) = 1)),
    ADD CONSTRAINT platforms_url_http CHECK (
        platform_url IS NULL OR (length(platform_url) <= 2083 AND platform_url ~* '^https?://[^[:space:]/?#]+'));
