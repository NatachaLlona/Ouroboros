WITH filtered AS MATERIALIZED (
    SELECT id, value FROM public.test
    WHERE (%s::bigint IS NULL OR id = %s::bigint)
      AND (%s::text IS NULL OR value ILIKE %s::text)
), page_items AS (
    SELECT id, value FROM filtered ORDER BY id LIMIT %s OFFSET %s
)
SELECT (SELECT count(*) FROM filtered), p.id, p.value
FROM (SELECT 1) AS anchor LEFT JOIN page_items p ON TRUE
ORDER BY p.id;
